"""Build a cleaning-ready Vision B dataset from MusicBrainz and ListenBrainz.

Vision B: an editorial curation lead decides which emerging artists to add to
next month's discovery playlists and which listener segment to surface each
one to. That needs two sides joined on the MusicBrainz artist:

* who the artist is (MusicBrainz): type, gender, area and country, begin and
  end dates, release history (first and latest release), ratings, tags and
  genres;
* how listeners behave (ListenBrainz): listens per user, artist and month,
  taken from the parts written by load_listenbrainz.py.

Stages (each caches its output under --data-dir and is skipped when the output
exists; pass --rebuild STAGE to redo one):

1. musicbrainz  stream the MusicBrainz full export (core and derived dumps)
                and keep only the tables and columns needed, as Parquet. The
                tars are never written to disk. The core dump is ~7 GB of
                bzip2 and must be read from its start, so one pass takes
                30-60 minutes; tables already extracted are not fetched again.
2. listens      map each listen's artist MBIDs to MusicBrainz artist ids
                (following merge redirects), credit the listen to every
                artist on it, and aggregate to user x artist x month.
3. dataset      join the two into analysis tables.

Output under --data-dir:
    musicbrainz/<table>.parquet   extracted MusicBrainz tables (keep columns)
    dataset/artists.parquet       one row per MusicBrainz artist with >= 1
                                  listen in the window: metadata, release
                                  history, tags/genres, listen totals. This is
                                  the main table to clean.
    dataset/artist_month.parquet  listens and distinct listeners per artist
                                  and month (growth curves)
    dataset/user_artist.parquet   listens per user and artist over the window
                                  (input for behavioral listener segments)
    dataset/user_artist_month/    listens per user, artist and month
    dataset/users.parquet         per user: listens, active days, max listens
                                  in one day, distinct artists (bot checks)
    dataset/listen_coverage.csv   per month: listens, MBID coverage, days with
                                  data, and whether the month is complete

Nothing here defines "emerging", builds segments, drops incomplete months, or
removes bad rows; those are cleaning and analysis decisions. In a notebook:

    from build_dataset import load_dataset
    data = load_dataset("~/dso576_data")      # dict of pandas DataFrames
    artists = data["artists"]

Requires: pyarrow >= 20, pandas, numpy

Example:
    python scripts/build_dataset.py --data-dir ~/dso576_data
"""

import argparse
import glob
import os
import re
import shutil
import sys
import tarfile
from calendar import monthrange
from datetime import datetime
from urllib.request import urlopen

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

MB_FULLEXPORT = "https://data.metabrainz.org/pub/musicbrainz/data/fullexport/"
STAGES = ["musicbrainz", "listens", "dataset"]
TOP_TAGS = 5

# Column orders follow admin/sql/CreateTables.sql in musicbrainz-server. The
# dumps are PostgreSQL COPY text: tab-separated, no header, \N for null.
# table -> (all columns in dump order, columns to keep)
LOOKUP = ["id", "name", "parent", "child_order", "description", "gid"]
CORE_TABLES = {
    "area": (
        ["id", "gid", "name", "type", "edits_pending", "last_updated",
         "begin_date_year", "begin_date_month", "begin_date_day",
         "end_date_year", "end_date_month", "end_date_day", "ended", "comment"],
        ["id", "name", "type"],
    ),
    "area_type": (LOOKUP, ["id", "name"]),
    "artist": (
        ["id", "gid", "name", "sort_name",
         "begin_date_year", "begin_date_month", "begin_date_day",
         "end_date_year", "end_date_month", "end_date_day",
         "type", "area", "gender", "comment", "edits_pending", "last_updated",
         "ended", "begin_area", "end_area"],
        ["id", "gid", "name", "sort_name",
         "begin_date_year", "begin_date_month", "begin_date_day",
         "end_date_year", "end_date_month", "end_date_day",
         "type", "area", "gender", "comment", "ended", "begin_area"],
    ),
    "artist_credit_name": (
        ["artist_credit", "position", "artist", "name", "join_phrase"],
        ["artist_credit", "artist"],
    ),
    "artist_gid_redirect": (["gid", "new_id", "created"], ["gid", "new_id"]),
    "artist_type": (LOOKUP, ["id", "name"]),
    "gender": (LOOKUP, ["id", "name"]),
    "genre": (["id", "gid", "name", "comment", "edits_pending", "last_updated"], ["name"]),
    "iso_3166_1": (["area", "code"], ["area", "code"]),
    "l_area_area": (
        ["id", "link", "entity0", "entity1", "edits_pending", "last_updated",
         "link_order", "entity0_credit", "entity1_credit"],
        ["link", "entity0", "entity1"],
    ),
    "link": (
        ["id", "link_type", "begin_date_year", "begin_date_month", "begin_date_day",
         "end_date_year", "end_date_month", "end_date_day", "attribute_count", "created", "ended"],
        ["id", "link_type"],
    ),
    "link_type": (
        ["id", "parent", "child_order", "gid", "entity_type0", "entity_type1", "name",
         "description", "link_phrase", "reverse_link_phrase", "long_link_phrase",
         "last_updated", "is_deprecated", "has_dates", "entity0_cardinality", "entity1_cardinality"],
        ["id", "entity_type0", "entity_type1", "name"],
    ),
    "release_group": (
        ["id", "gid", "name", "artist_credit", "type", "comment", "edits_pending", "last_updated"],
        ["id", "artist_credit", "type"],
    ),
    "release_group_primary_type": (LOOKUP, ["id", "name"]),
    "release_group_secondary_type_join": (["release_group", "secondary_type", "created"], ["release_group"]),
}
DERIVED_TABLES = {
    "artist_meta": (["id", "rating", "rating_count"], ["id", "rating", "rating_count"]),
    "artist_tag": (["artist", "tag", "count", "last_updated"], ["artist", "tag", "count"]),
    "release_group_meta": (
        ["id", "release_count", "first_release_date_year", "first_release_date_month",
         "first_release_date_day", "rating", "rating_count"],
        ["id", "first_release_date_year", "first_release_date_month", "first_release_date_day"],
    ),
    "tag": (["id", "name", "ref_count"], ["id", "name"]),
}
TEXT_COLUMNS = {"gid", "name", "sort_name", "comment", "entity_type0", "entity_type1", "code"}


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def write_atomic(table, path):
    tmp = path + ".tmp"
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)


# --- Stage 1: MusicBrainz -----------------------------------------------------

def latest_export():
    with urlopen(MB_FULLEXPORT + "LATEST", timeout=60) as resp:
        return resp.read().decode().strip()


def copy_to_parquet(fileobj, columns, keep, path):
    """Convert one COPY-format table to Parquet, streaming in blocks."""
    reader = pacsv.open_csv(
        fileobj,
        read_options=pacsv.ReadOptions(column_names=columns, block_size=1 << 24),
        parse_options=pacsv.ParseOptions(
            delimiter="\t", quote_char=False, double_quote=False, escape_char=False
        ),
        convert_options=pacsv.ConvertOptions(
            include_columns=keep,
            column_types={
                c: pa.string() if c in TEXT_COLUMNS else pa.bool_() if c == "ended" else pa.int64()
                for c in keep
            },
            null_values=["\\N"],
            strings_can_be_null=True,
            true_values=["t"],
            false_values=["f"],
        ),
    )
    rows = 0
    tmp = path + ".tmp"
    with pq.ParquetWriter(tmp, reader.schema, compression="zstd") as writer:
        for batch in reader:
            # COPY escapes backslashes; MusicBrainz strips other control characters.
            arrays = [
                pc.replace_substring(col, "\\\\", "\\") if pa.types.is_string(col.type) else col
                for col in batch.columns
            ]
            writer.write_batch(pa.RecordBatch.from_arrays(arrays, schema=batch.schema))
            rows += batch.num_rows
    os.replace(tmp, path)
    return rows


def extract_dump(url, tables, mb_dir):
    """Stream a mbdump tar.bz2 once and convert the wanted members."""
    todo = {t for t in tables if not os.path.exists(os.path.join(mb_dir, f"{t}.parquet"))}
    if not todo:
        return
    log(f"streaming {url} for {len(todo)} tables: {', '.join(sorted(todo))}")
    with urlopen(url, timeout=120) as resp, tarfile.open(fileobj=resp, mode="r|bz2") as tf:
        for member in tf:
            name = member.name.removeprefix("mbdump/")
            if name not in todo:
                continue
            columns, keep = tables[name]
            rows = copy_to_parquet(tf.extractfile(member), columns, keep, os.path.join(mb_dir, f"{name}.parquet"))
            log(f"  {name}: {rows:,} rows")
            todo.discard(name)
            if not todo:
                break
    if todo:
        raise RuntimeError(f"tables not found in {url}: {sorted(todo)}")


def build_musicbrainz(mb_dir, export):
    os.makedirs(mb_dir, exist_ok=True)
    export = export or latest_export()
    base = f"{MB_FULLEXPORT}{export}/"
    # Derived first: it is small (~0.5 GB), so problems show up early.
    extract_dump(base + "mbdump-derived.tar.bz2", DERIVED_TABLES, mb_dir)
    extract_dump(base + "mbdump.tar.bz2", CORE_TABLES, mb_dir)
    version = os.path.join(mb_dir, "EXPORT")
    if not os.path.exists(version):
        with open(version, "w") as f:
            f.write(export + "\n")


def read_mb(mb_dir, table, columns=None):
    return pq.read_table(os.path.join(mb_dir, f"{table}.parquet"), columns=columns).to_pandas()


# --- Stage 2: listens ---------------------------------------------------------

def artist_lookup(mb_dir):
    """MBID -> MusicBrainz artist id, including MBIDs of merged artists."""
    artist = pq.read_table(os.path.join(mb_dir, "artist.parquet"), columns=["id", "gid"])
    redirect = pq.read_table(os.path.join(mb_dir, "artist_gid_redirect.parquet"))
    gids = pa.concat_arrays([artist["gid"].combine_chunks(), redirect["gid"].combine_chunks()])
    ids = np.concatenate([artist["id"].to_numpy(), redirect["new_id"].to_numpy()]).astype(np.int32)
    return pd.Index(gids.to_numpy(zero_copy_only=False)), ids


def part_number(path):
    return int(re.search(r"part-(\d+)\.parquet$", path).group(1))


def aggregate_part(path, lookup, ids):
    """Return (user x artist x month counts, per-month coverage) for one part."""
    t = pq.read_table(path, columns=["user_id", "listened_at", "artist_credit_mbids"])
    ts = t["listened_at"]
    month = pc.add(pc.multiply(pc.year(ts), 100), pc.month(ts)).to_numpy().astype(np.int32)
    day = pc.cast(ts, pa.date32()).to_numpy().astype("datetime64[D]").astype(np.int32)
    user = t["user_id"].to_numpy().astype(np.int32)

    credits = t["artist_credit_mbids"].combine_chunks()
    has_mbid = pc.fill_null(pc.greater(pc.list_value_length(credits), 0), False).to_numpy(zero_copy_only=False)
    flat = pc.dictionary_encode(pc.list_flatten(credits))
    row = pc.list_parent_indices(credits).to_numpy()
    codes = lookup.get_indexer(flat.dictionary.to_numpy(zero_copy_only=False))
    artist = np.where(codes >= 0, ids[codes], -1)[flat.indices.to_numpy()]

    mapped = artist >= 0
    row, artist = row[mapped], artist[mapped]
    # An artist credited twice on one listen still gets that listen once.
    key = np.unique((row.astype(np.int64) << 32) | artist.astype(np.int64))
    row, artist = (key >> 32).astype(np.int64), (key & 0xFFFFFFFF).astype(np.int32)
    has_mapped = np.zeros(t.num_rows, bool)
    has_mapped[row] = True

    pairs = pa.table({"month": month[row], "user_id": user[row], "artist_id": artist})
    counts = pairs.group_by(["month", "user_id", "artist_id"]).aggregate([("artist_id", "count")])
    counts = counts.rename_columns(["month", "user_id", "artist_id", "listens"])

    cov = pd.DataFrame({"month": month, "day": day, "has_mbid": has_mbid, "has_mapped": has_mapped})
    coverage = cov.groupby("month").agg(
        listens=("day", "size"), listens_with_mbid=("has_mbid", "sum"), listens_mapped=("has_mapped", "sum")
    )
    days = cov.groupby("month")["day"].unique()
    user_day = pa.table({"user_id": user, "day": day}).group_by(["user_id", "day"]).aggregate([("day", "count")])
    return counts, coverage, days, user_day.rename_columns(["user_id", "day", "listens"])


def finalize_month(month, partials, out_dir):
    table = pa.concat_tables(partials)
    table = table.group_by(["month", "user_id", "artist_id"]).aggregate([("listens", "sum")])
    table = table.rename_columns(["month", "user_id", "artist_id", "listens"])
    table = table.sort_by([("artist_id", "ascending"), ("user_id", "ascending")])
    write_atomic(table, os.path.join(out_dir, "user_artist_month", f"{month // 100}-{month % 100:02d}.parquet"))
    am = table.group_by(["month", "artist_id"]).aggregate([("listens", "sum"), ("user_id", "count")])
    return am.rename_columns(["month", "artist_id", "listens", "listeners"])


def build_listens(listen_dir, mb_dir, out_dir):
    files = sorted(glob.glob(os.path.join(listen_dir, "part-*.parquet")), key=part_number)
    # load_listenbrainz.py writes empty parts for those just outside the window.
    files = [f for f in files if pq.ParquetFile(f).metadata.num_rows > 0]
    if not files:
        sys.exit(f"no listen parts in {listen_dir}; run load_listenbrainz.py first")
    uam_dir = os.path.join(out_dir, "user_artist_month")
    shutil.rmtree(uam_dir, ignore_errors=True)
    os.makedirs(uam_dir)

    lookup, ids = artist_lookup(mb_dir)
    log(f"{len(lookup):,} artist MBIDs; aggregating {len(files)} listen parts")
    partials, coverage, days, artist_month, user_days = {}, [], {}, [], []
    for i, path in enumerate(files, 1):
        counts, cov, part_days, user_day = aggregate_part(path, lookup, ids)
        coverage.append(cov)
        user_days.append(user_day)
        for m, d in part_days.items():
            days.setdefault(m, set()).update(d.tolist())
        for m in pc.unique(counts["month"]).to_pylist():
            partials.setdefault(m, []).append(counts.filter(pc.equal(counts["month"], m)))
        # Parts are time-ordered, so months before this part's first month are done.
        first = min(part_days.index)
        for m in sorted(m for m in partials if m < first):
            artist_month.append(finalize_month(m, partials.pop(m), out_dir))
        if i % 10 == 0 or i == len(files):
            log(f"  {i}/{len(files)} parts")
    for m in sorted(partials):
        artist_month.append(finalize_month(m, partials.pop(m), out_dir))
    write_atomic(pa.concat_tables(artist_month), os.path.join(out_dir, "artist_month.parquet"))

    cov = pd.concat(coverage).groupby(level=0).sum()
    cov["days_with_listens"] = [len(days[m]) for m in cov.index]
    cov["days_in_month"] = [monthrange(m // 100, m % 100)[1] for m in cov.index]
    cov["complete"] = cov["days_with_listens"] == cov["days_in_month"]
    cov["share_mapped"] = (cov["listens_mapped"] / cov["listens"]).round(4)
    cov.index.name = "month"
    cov.reset_index().to_csv(os.path.join(out_dir, "listen_coverage.csv"), index=False)
    log("listen coverage by month:\n" + cov.to_string())

    # Window totals per user and artist; each user_artist_month row is one month.
    uam = pq.read_table(uam_dir, columns=["user_id", "artist_id", "month", "listens"])
    ua = uam.group_by(["user_id", "artist_id"]).aggregate(
        [("listens", "sum"), ("month", "count"), ("month", "min"), ("month", "max")]
    )
    ua = ua.rename_columns(["user_id", "artist_id", "listens", "months_active", "first_month", "last_month"])
    write_atomic(ua, os.path.join(out_dir, "user_artist.parquet"))

    # Per-user activity, including listens without an MBID, for spotting bots
    # and scrobble floods (e.g. thousands of listens in one day).
    ud = pa.concat_tables(user_days).group_by(["user_id", "day"]).aggregate([("listens", "sum")])
    users = ud.group_by("user_id").aggregate([("listens_sum", "sum"), ("day", "count"), ("listens_sum", "max")])
    users = users.rename_columns(["user_id", "listens_total", "active_days", "max_listens_per_day"])
    artists = ua.group_by("user_id").aggregate([("artist_id", "count"), ("listens", "sum")])
    users = users.join(artists.rename_columns(["user_id", "artists_total", "listens_mapped"]), "user_id", join_type="left outer")
    write_atomic(users.sort_by("user_id"), os.path.join(out_dir, "users.parquet"))
    log(f"user_artist_month: {uam.num_rows:,} rows; user_artist: {ua.num_rows:,} rows; users: {users.num_rows:,}")


# --- Stage 3: dataset ---------------------------------------------------------

def area_country(mb_dir):
    """ISO country code for each area, walking up 'part of' relationships."""
    area = read_mb(mb_dir, "area")
    lt = read_mb(mb_dir, "link_type")
    part_of = lt.loc[(lt["entity_type0"] == "area") & (lt["entity_type1"] == "area") & (lt["name"] == "part of"), "id"]
    link = read_mb(mb_dir, "link")
    laa = read_mb(mb_dir, "l_area_area")
    edges = laa[laa["link"].isin(link.loc[link["link_type"].isin(part_of), "id"])]
    parent = edges.drop_duplicates("entity1").set_index("entity1")["entity0"]  # entity0 contains entity1
    code = read_mb(mb_dir, "iso_3166_1").drop_duplicates("area").set_index("area")["code"]

    country = pd.Series(pd.NA, index=area["id"].to_numpy(), dtype="string")
    current = pd.Series(area["id"].to_numpy(), index=area["id"].to_numpy(), dtype="Int64")
    for _ in range(10):
        country = country.fillna(current.map(code).astype("string"))
        current = current.map(parent).astype("Int64")
        if current.isna().all():
            break
    return country


def parts_to_date(year, month, day):
    """MusicBrainz year/month/day columns -> dates; missing month or day becomes the 1st.

    Built from zero-padded strings: pd.to_datetime on year/month/day columns
    reads them as one YYYYMMDD number, which turns year 975 into 9750.
    Impossible dates (e.g. Feb 30) become NaT.
    """
    has = year.notna()
    text = (
        year[has].astype("int64").map("{:04d}".format)
        + "-" + month[has].fillna(1).astype("int64").map("{:02d}".format)
        + "-" + day[has].fillna(1).astype("int64").map("{:02d}".format)
    )
    date = pd.Series(pd.NaT, index=year.index, dtype="datetime64[us]")
    date[has] = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    return date


def release_history(mb_dir, artist_ids, window_start):
    acn = read_mb(mb_dir, "artist_credit_name")
    acn = acn[acn["artist"].isin(artist_ids)].drop_duplicates()
    rg = read_mb(mb_dir, "release_group")
    rg = rg[rg["artist_credit"].isin(acn["artist_credit"])]
    rg = rg.merge(read_mb(mb_dir, "release_group_meta"), on="id", how="left")
    rg["primary_type"] = rg["type"].map(read_mb(mb_dir, "release_group_primary_type").set_index("id")["name"])
    rg["has_secondary_type"] = rg["id"].isin(read_mb(mb_dir, "release_group_secondary_type_join")["release_group"])
    rg["release_date"] = parts_to_date(
        rg["first_release_date_year"], rg["first_release_date_month"], rg["first_release_date_day"]
    )
    ar = acn.merge(rg, on="artist_credit")[["artist", "id", "primary_type", "has_secondary_type", "release_date"]]
    ar = ar.drop_duplicates(["artist", "id"])
    plain = ~ar["has_secondary_type"]
    ar["is_album"] = plain & (ar["primary_type"] == "Album")
    ar["is_ep"] = plain & (ar["primary_type"] == "EP")
    ar["is_single"] = plain & (ar["primary_type"] == "Single")
    ar["in_window"] = ar["release_date"] >= window_start
    hist = ar.groupby("artist").agg(
        n_release_groups=("id", "size"),
        n_albums=("is_album", "sum"),
        n_eps=("is_ep", "sum"),
        n_singles=("is_single", "sum"),
        n_release_groups_in_window=("in_window", "sum"),
        first_release_date=("release_date", "min"),
        last_release_date=("release_date", "max"),
    )
    hist.index.name = "artist_id"
    return hist


def top_tags(mb_dir, artist_ids):
    at = read_mb(mb_dir, "artist_tag")
    at = at[at["artist"].isin(artist_ids) & (at["count"] > 0)]
    at = at.merge(read_mb(mb_dir, "tag").rename(columns={"id": "tag", "name": "tag_name"}), on="tag")
    at["is_genre"] = at["tag_name"].isin(read_mb(mb_dir, "genre")["name"])
    at = at.sort_values(["artist", "count", "tag_name"], ascending=[True, False, True])

    def joined(df):
        return df.groupby("artist").head(TOP_TAGS).groupby("artist")["tag_name"].agg("; ".join)

    tags = pd.DataFrame({"top_tags": joined(at), "top_genres": joined(at[at["is_genre"]])})
    tags.index.name = "artist_id"
    return tags


def build_dataset(mb_dir, out_dir):
    am = pq.read_table(os.path.join(out_dir, "artist_month.parquet")).to_pandas()
    ua = pq.read_table(os.path.join(out_dir, "user_artist.parquet"), columns=["artist_id"]).to_pandas()
    coverage = pd.read_csv(os.path.join(out_dir, "listen_coverage.csv"))
    first_month = int(coverage["month"].min())
    window_start = pd.Timestamp(first_month // 100, first_month % 100, 1)

    listening = am.groupby("artist_id").agg(
        listens_total=("listens", "sum"),
        months_with_listens=("month", "size"),
        first_listen_month=("month", "min"),
        last_listen_month=("month", "max"),
        peak_month_listeners=("listeners", "max"),
    )
    listening["listeners_total"] = ua.groupby("artist_id").size()
    ids = listening.index

    artist = read_mb(mb_dir, "artist")
    artist = artist[artist["id"].isin(ids)].rename(columns={"id": "artist_id", "gid": "artist_mbid", "comment": "disambiguation"})
    lookups = {
        "type": read_mb(mb_dir, "artist_type").set_index("id")["name"],
        "gender": read_mb(mb_dir, "gender").set_index("id")["name"],
    }
    for col, names in lookups.items():
        artist[col] = artist[col].map(names)
    area = read_mb(mb_dir, "area").set_index("id")
    area_type = read_mb(mb_dir, "area_type").set_index("id")["name"]
    country = area_country(mb_dir)
    artist["area_name"] = artist["area"].map(area["name"])
    artist["area_type"] = artist["area"].map(area["type"]).map(area_type)
    artist["country"] = artist["area"].map(country)
    artist["begin_area_country"] = artist["begin_area"].map(country)
    artist = artist.drop(columns=["area", "begin_area"]).rename(columns={"type": "artist_type"})

    meta = read_mb(mb_dir, "artist_meta").rename(columns={"id": "artist_id"}).set_index("artist_id")
    df = (
        artist.set_index("artist_id")
        .join(release_history(mb_dir, ids, window_start))
        .join(top_tags(mb_dir, ids))
        .join(meta)
        .join(listening)
        .reset_index()
        .sort_values("listens_total", ascending=False, ignore_index=True)
    )
    write_atomic(pa.Table.from_pandas(df, preserve_index=False), os.path.join(out_dir, "artists.parquet"))
    log(f"artists: {len(df):,} rows x {df.shape[1]} columns")
    log("missing share per column:\n" + df.isna().mean().round(3).to_string())


# --- Loading ------------------------------------------------------------------

def load_dataset(data_dir, user_level=False):
    """Load the built dataset as pandas DataFrames.

    user_level=True also loads user_artist (one row per user and artist),
    which can take several GB of memory for the full window.
    """
    out = os.path.join(os.path.expanduser(data_dir), "dataset")
    data = {
        "artists": pd.read_parquet(os.path.join(out, "artists.parquet")),
        "artist_month": pd.read_parquet(os.path.join(out, "artist_month.parquet")),
        "users": pd.read_parquet(os.path.join(out, "users.parquet")),
        "coverage": pd.read_csv(os.path.join(out, "listen_coverage.csv")),
    }
    if user_level:
        data["user_artist"] = pd.read_parquet(os.path.join(out, "user_artist.parquet"))
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="~/dso576_data", help="load_listenbrainz.py --out-dir (keep it outside the repo)")
    ap.add_argument("--mb-export", help="MusicBrainz export folder, e.g. 20260930-002222 (default: LATEST)")
    ap.add_argument("--stages", nargs="+", choices=STAGES, default=STAGES, help="stages to run")
    ap.add_argument("--rebuild", nargs="+", choices=STAGES, default=[], help="redo these stages even if cached")
    args = ap.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    mb_dir = os.path.join(data_dir, "musicbrainz")
    out_dir = os.path.join(data_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)

    # A rebuilt stage makes every later stage stale, so those rerun too.
    rebuild = False
    if "musicbrainz" in args.stages:
        if "musicbrainz" in args.rebuild:
            shutil.rmtree(mb_dir, ignore_errors=True)
            rebuild = True
        build_musicbrainz(mb_dir, args.mb_export)
    rebuild = rebuild or "listens" in args.rebuild
    if "listens" in args.stages and (rebuild or not os.path.exists(os.path.join(out_dir, "user_artist.parquet"))):
        build_listens(os.path.join(data_dir, "listens"), mb_dir, out_dir)
        rebuild = True
    rebuild = rebuild or "dataset" in args.rebuild
    if "dataset" in args.stages and (rebuild or not os.path.exists(os.path.join(out_dir, "artists.parquet"))):
        build_dataset(mb_dir, out_dir)


if __name__ == "__main__":
    sys.exit(main())
