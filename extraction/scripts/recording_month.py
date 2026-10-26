"""Song x month listens and distinct listeners, so the dashboard can show which
track drives an emerging artist's growth. Reads the raw parts written by
load_listenbrainz.py (which already keeps recording_mbid) and drops the bot
users flagged by clean_dataset.py.

Run after clean_dataset.py:
    python scripts/recording_month.py --data-dir ~/dso576_data
Writes <data-dir>/clean/recording_month.parquet:
    month (YYYYMM), recording_mbid, artist_mbid (first credited artist), listens, listeners
Self-check: python scripts/recording_month.py --test
"""
import argparse, os, tempfile

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

SQL = """
COPY (
  SELECT year(listened_at) * 100 + month(listened_at) AS month,
         recording_mbid,
         any_value(artist_credit_mbids[1]) AS artist_mbid,
         count(*) AS listens,
         count(DISTINCT user_id) AS listeners
  FROM read_parquet('{listens}')
  WHERE recording_mbid IS NOT NULL
    AND user_id NOT IN (SELECT user_id FROM read_parquet('{users}') WHERE excluded_bot)
  GROUP BY ALL
) TO '{out}' (FORMAT parquet)
"""


def build(listens_glob, users_path, out_path):
    duckdb.sql(SQL.format(listens=listens_glob, users=users_path, out=out_path))


def test():
    d = tempfile.mkdtemp()
    ts = pa.array([1780272000, 1780272100, 1780272200, 1780272300], pa.timestamp("s"))  # all June 2026
    pq.write_table(pa.table({
        "user_id": [1, 1, 2, 9], "listened_at": ts,
        "artist_credit_mbids": [["a"], ["a"], ["a", "b"], ["a"]],
        "recording_mbid": ["r", "r", "r", "r"]}), f"{d}/part-0001.parquet")
    pq.write_table(pa.table({"user_id": [1, 2, 9], "excluded_bot": [False, False, True]}), f"{d}/users.parquet")
    build(f"{d}/part-*.parquet", f"{d}/users.parquet", f"{d}/out.parquet")
    row = pq.read_table(f"{d}/out.parquet").to_pylist()[0]
    assert row == {"month": 202606, "recording_mbid": "r", "artist_mbid": "a", "listens": 3, "listeners": 2}, row
    print("ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="~/dso576_data")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.test:
        test()
    else:
        d = os.path.expanduser(a.data_dir)
        build(f"{d}/listens/part-*.parquet", f"{d}/clean/users_flagged.parquet", f"{d}/clean/recording_month.parquet")
        print(f"wrote {d}/clean/recording_month.parquet")
