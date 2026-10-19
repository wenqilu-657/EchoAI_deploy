"""Download raw ListenBrainz listens once and keep them UNCHANGED (data/raw/).
Run: python scripts/fetch_listens.py [user] [start YYYY-MM-DD] [end YYYY-MM-DD]
Writes data/raw/listens_<user>_<start>_<end>.jsonl + a manifest with the download date and sha256.
data/ is gitignored, so the raw file is never committed."""
import hashlib, json, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
import requests

user = sys.argv[1] if len(sys.argv) > 1 else "rob"
start = sys.argv[2] if len(sys.argv) > 2 else "2026-06-01"
end = sys.argv[3] if len(sys.argv) > 3 else "2026-08-31"
ts = lambda d: int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())
start_ts, end_ts = ts(start), ts(end) + 86400  # end date inclusive

out = Path("data/raw"); out.mkdir(parents=True, exist_ok=True)
path = out / f"listens_{user}_{start}_{end}.jsonl"
cursor, n = end_ts, 0
with path.open("w") as f:
    while True:
        for attempt in range(6):  # retry slow/failed API calls with backoff
            try:
                r = requests.get(f"https://api.listenbrainz.org/1/user/{user}/listens",
                                 params={"count": 500, "max_ts": cursor},
                                 headers={"User-Agent": "dso576-student-project/0.1"}, timeout=90)
                r.raise_for_status()
                break
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
                if attempt == 5:
                    raise
                wait = 5 * 2 ** attempt
                print(f"retry {attempt + 1}/5 after {type(e).__name__}; waiting {wait}s", flush=True)
                time.sleep(wait)
        batch = r.json()["payload"]["listens"]
        if not batch:
            break
        for l in batch:  # raw record, no cleaning
            if start_ts <= l["listened_at"] < end_ts:
                f.write(json.dumps(l, ensure_ascii=False) + "\n"); n += 1
        oldest = min(l["listened_at"] for l in batch)
        if oldest < start_ts:
            break
        cursor = oldest
        print(f"{n} listens so far (back to {datetime.fromtimestamp(oldest, timezone.utc):%Y-%m-%d})", flush=True)
        time.sleep(0.5)

sha = hashlib.sha256(path.read_bytes()).hexdigest()
(out / "MANIFEST.txt").write_text(
    f"source: https://api.listenbrainz.org/1/user/{user}/listens\n"
    f"downloaded: {date.today()}\nwindow: {start} to {end} (UTC)\n"
    f"file: {path.name}\nrows: {n}\nsha256: {sha}\n")
print(f"{n} listens -> {path}\nsha256 {sha}")
