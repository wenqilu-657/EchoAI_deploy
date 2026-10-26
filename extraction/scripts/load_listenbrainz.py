"""Load a recent window of ListenBrainz listens from the full Spark dump.

The Spark dump is a single uncompressed tar (~236 GB) of time-ordered Parquet
parts (0.parquet ... N.parquet). Each part holds roughly 1.5-2 days of listens
from all users. Rather than downloading the whole archive, this script:

1. walks the tar backward from its end with HTTP range requests to locate the
   parts that cover the requested window (cached in part_index.csv);
2. fetches only the column chunks it needs from each part;
3. keeps listens inside the window for a deterministic user sample (each
   sampled user keeps their full history in the window), and writes one small
   Parquet file per part.

Re-running resumes: parts already written are skipped.

Output (under --out-dir, which should be outside the git repo):
    part_index.csv          located parts: name, offset, size, first listened_at
    listens/part-NNNN.parquet
    manifest.csv            per part: rows read, rows kept, bytes fetched

Requires: pyarrow >= 20, numpy
(pyarrow 19 aborts with "Repetition level histogram size mismatch" on these
files' metadata.)

Example:
    python scripts/load_listenbrainz.py --out-dir ~/dso576_data --months 18
"""

import argparse
import csv
import io
import os
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.request import Request, urlopen

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

if int(pa.__version__.split(".")[0]) < 20:
    sys.exit(f"pyarrow >= 20 is required (found {pa.__version__}); run: pip install -U 'pyarrow>=20'")

DEFAULT_URL = (
    "https://data.metabrainz.org/pub/musicbrainz/listenbrainz/fullexport/"
    "listenbrainz-dump-2722-20261015-000002-full/"
    "listenbrainz-spark-dump-2722-20261015-000002-full.tar"
)
COLUMNS = ["user_id", "listened_at", "artist_credit_mbids", "recording_mbid", "artist_name"]
MAGIC = b"PAR1"
TAR_BLOCK = 512
SEARCH_WINDOW = 64 * 1024  # bytes searched before a header for the previous part's end
MERGE_GAP = 64 * 1024  # merge column-chunk ranges closer than this into one request

_log_lock = threading.Lock()


def log(msg):
    with _log_lock:
        print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# --- HTTP ---------------------------------------------------------------------

def fetch(url, start, length, tries=6):
    """Fetch bytes [start, start + length) with retries."""
    for attempt in range(tries):
        try:
            req = Request(url, headers={"Range": f"bytes={start}-{start + length - 1}"})
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
            if len(data) != length:
                raise IOError(f"short read {len(data)}/{length}")
            return data
        except Exception as exc:
            if attempt == tries - 1:
                raise
            log(f"retry at byte {start}: {exc}")
            time.sleep(2 ** attempt)


def archive_size(url):
    with urlopen(Request(url, method="HEAD"), timeout=60) as resp:
        return int(resp.headers["Content-Length"])


# --- Parquet parts inside the tar --------------------------------------------

def read_footer(url, offset, size):
    """Return (metadata, raw footer bytes) for the Parquet part at [offset, offset + size)."""
    tail = fetch(url, offset + size - 8, 8)
    if tail[4:] != MAGIC:
        raise ValueError(f"no Parquet magic at end of part at {offset}")
    meta_len = struct.unpack("<I", tail[:4])[0]
    footer = fetch(url, offset + size - 8 - meta_len, meta_len) + tail
    return pq.ParquetFile(io.BytesIO(MAGIC + footer)).metadata, footer


def chunk_range(col):
    """Byte range of one column chunk, relative to the start of the part."""
    start = min(o for o in (col.dictionary_page_offset, col.data_page_offset) if o)
    return start, start + col.total_compressed_size


def find_part_end(url, before):
    """Offset just past the last 'PAR1' located before `before` (end of the previous part)."""
    lo = max(0, before - SEARCH_WINDOW)
    i = fetch(url, lo, before - lo).rfind(MAGIC)
    if i < 0:
        raise ValueError(f"no Parquet part ends before byte {before}")
    return lo + i + len(MAGIC)


def locate_part(url, end):
    """Given the end offset of a part, return (name, offset, size)."""
    tail = fetch(url, end - 8, 8)
    meta_len = struct.unpack("<I", tail[:4])[0]
    meta_start = end - 8 - meta_len
    md = pq.ParquetFile(io.BytesIO(MAGIC + fetch(url, meta_start, meta_len) + tail)).metadata
    data_len = max(
        chunk_range(md.row_group(g).column(c))[1]
        for g in range(md.num_row_groups)
        for c in range(md.num_columns)
    )
    offset = meta_start - data_len
    header = fetch(url, offset - TAR_BLOCK, TAR_BLOCK)
    if header[257:262] != b"ustar":
        raise ValueError(f"expected a tar header at byte {offset - TAR_BLOCK}")
    name = header[0:100].rstrip(b"\0").decode().split("/")[-1]
    return name, offset, end - offset


def read_columns(url, offset, size, md, footer, columns, row_groups=None):
    """Read selected columns by fetching only their chunks into a sparse buffer."""
    row_groups = range(md.num_row_groups) if row_groups is None else row_groups
    wanted = set(columns)
    ranges = sorted(
        chunk_range(md.row_group(g).column(c))
        for g in row_groups
        for c in range(md.num_columns)
        if md.schema.column(c).path.split(".")[0] in wanted
    )
    merged = []
    for s, e in ranges:
        if merged and s - merged[-1][1] <= MERGE_GAP:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    buf = bytearray(size)
    buf[: len(MAGIC)] = MAGIC
    buf[size - len(footer):] = footer
    fetched = 0
    for s, e in merged:
        buf[s:e] = fetch(url, offset + s, e - s)
        fetched += e - s
    pf = pq.ParquetFile(pa.BufferReader(pa.py_buffer(buf)))
    table = pf.read_row_groups(list(row_groups), columns=columns)
    return table, fetched


def listened_at_bounds(url, offset, size, md, footer, row_group):
    table, _ = read_columns(url, offset, size, md, footer, ["listened_at"], [row_group])
    ts = table.column("listened_at")
    return pc.min(ts).as_py(), pc.max(ts).as_py()


# --- Window and index ---------------------------------------------------------

def month_start(d, months_back=0):
    y, m = divmod(d.year * 12 + d.month - 1 - months_back, 12)
    return datetime(y, m + 1, 1)


def build_index(url, index_path, end, months, check_every, max_parts):
    """Walk parts backward from the end until one starts before the window start.

    If `end` is None it defaults to the start of the month of the dump's last
    listen, which drops the incomplete final month. Returns (parts, start, end);
    parts are dicts ordered newest first.
    """
    parts, start = [], month_start(end, months) if end else None
    part_end = find_part_end(url, archive_size(url))
    while True:
        name, offset, size = locate_part(url, part_end)
        part = {"name": name, "offset": offset, "size": size, "first_ts": ""}
        k = len(parts)
        after_window = k > 0 and parts[-1]["first_ts"] and parts[-1]["first_ts"] >= end
        if k == 0 or k % check_every == 0 or after_window:
            md, footer = read_footer(url, offset, size)
            part["first_ts"] = listened_at_bounds(url, offset, size, md, footer, 0)[0]
            if end is None:
                end = month_start(listened_at_bounds(url, offset, size, md, footer, md.num_row_groups - 1)[1])
                start = month_start(end, months)
            log(f"indexed {k + 1} parts; {name} starts {part['first_ts']}")
        parts.append(part)
        reached = part["first_ts"] and part["first_ts"] < start
        if reached or (max_parts and len(parts) >= max_parts):
            break
        part_end = find_part_end(url, offset - TAR_BLOCK)

    with open(index_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "offset", "size", "first_ts"])
        w.writeheader()
        w.writerows(parts)
    return parts, start, end


# --- Extraction ---------------------------------------------------------------

def sample_mask(user_ids, frac, seed):
    """Deterministic per-user hash sample: the same users are kept in every part."""
    if frac >= 1:
        return None
    ids = user_ids.to_numpy().astype(np.uint64)
    with np.errstate(over="ignore"):
        h = (ids + np.uint64(seed)) * np.uint64(0x9E3779B97F4A7C15)
        h ^= h >> np.uint64(31)
    return pa.array((h >> np.uint64(11)).astype(np.float64) / 2.0**53 < frac)


def extract_part(url, part, out_dir, start, end, frac, seed):
    out_path = os.path.join(out_dir, "listens", f"part-{part['name'].split('.')[0]}.parquet")
    if os.path.exists(out_path):
        return None
    md, footer = read_footer(url, part["offset"], part["size"])
    table, fetched = read_columns(url, part["offset"], part["size"], md, footer, COLUMNS)
    rows_in = table.num_rows

    ts = table.column("listened_at")
    keep = pc.and_(
        pc.greater_equal(ts, pa.scalar(start, ts.type)),
        pc.less(ts, pa.scalar(end, ts.type)),
    )
    users = sample_mask(table.column("user_id"), frac, seed)
    if users is not None:
        keep = pc.and_(keep, users)
    table = table.filter(keep)

    tmp = out_path + ".tmp"
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, out_path)
    return {"part": part["name"], "rows_in": rows_in, "rows_kept": table.num_rows, "bytes_fetched": fetched}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, help="output directory (keep it outside the repo)")
    ap.add_argument("--url", default=DEFAULT_URL, help="Spark dump .tar URL")
    ap.add_argument("--months", type=int, default=18, help="number of complete months to load")
    ap.add_argument("--end", help="exclusive window end, YYYY-MM-DD (default: start of the dump's last month)")
    ap.add_argument("--user-frac", type=float, default=1.0, help="fraction of users to keep (hash sample)")
    ap.add_argument("--seed", type=int, default=0, help="seed for the user sample")
    ap.add_argument("--workers", type=int, default=4, help="parts downloaded in parallel")
    ap.add_argument("--check-every", type=int, default=10, help="read timestamps every N parts while indexing")
    ap.add_argument("--max-parts", type=int, help="stop after N parts (for testing)")
    args = ap.parse_args()

    out_dir = os.path.expanduser(args.out_dir)
    os.makedirs(os.path.join(out_dir, "listens"), exist_ok=True)

    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else None
    parts, start, end = build_index(
        args.url, os.path.join(out_dir, "part_index.csv"), end, args.months, args.check_every, args.max_parts
    )
    # Parts are time-ordered, so a part starting at or after `end` has no rows in the window.
    parts = [p for p in parts if not (p["first_ts"] and p["first_ts"] >= end)]
    log(f"window {start:%Y-%m-%d} to {end:%Y-%m-%d} (exclusive); {len(parts)} parts; user frac {args.user_frac}")

    manifest_path = os.path.join(out_dir, "manifest.csv")
    new_manifest = not os.path.exists(manifest_path)
    with open(manifest_path, "a", newline="") as mf, ThreadPoolExecutor(args.workers) as pool:
        w = csv.DictWriter(mf, fieldnames=["part", "rows_in", "rows_kept", "bytes_fetched"])
        if new_manifest:
            w.writeheader()
        futures = {
            pool.submit(extract_part, args.url, p, out_dir, start, end, args.user_frac, args.seed): p
            for p in parts
        }
        done = 0
        for fut in as_completed(futures):
            done += 1
            row = fut.result()
            if row is None:
                continue
            w.writerow(row)
            mf.flush()
            log(f"{done}/{len(parts)} {row['part']}: kept {row['rows_kept']:,} of {row['rows_in']:,} "
                f"rows, fetched {row['bytes_fetched'] / 1e6:.0f} MB")


if __name__ == "__main__":
    sys.exit(main())
