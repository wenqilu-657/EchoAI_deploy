"""Backend analysis for the Emerging Artist Discovery dashboard.

Every public function returns a pandas DataFrame (or a dict) computed from the
canonical tables built by extraction/ (definitions: DATA_DECISIONS.md).
Nothing is printed or plotted here; the dashboard (Phase 3) only calls these.

Data folder: $DSO576_DATA, default ~/dso576_data/clean
Self-check against the real data: python backend/analysis.py
"""
import os
import threading
import time
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path(os.environ.get("DSO576_DATA", "~/dso576_data/clean")).expanduser()
MONTHS = (202603, 202604, 202605, 202606, 202607, 202608)
BASELINE_MONTHS, RECENT_MONTHS = MONTHS[:3], MONTHS[3:]
DEFAULTS = dict(min_release="2023-01-01", min_baseline=5, size_pct=0.90, growth_pct=0.90)  # D7, D8


def _col(m):
    return f"listeners_{m // 100}_{m % 100:02d}"


_LOCK = threading.Lock()


def _con():
    with _LOCK:
        return _con_once()


@lru_cache(maxsize=1)
def _con_once():
    con = duckdb.connect()
    for t in ("artists_clean", "artist_month_clean", "user_artist_clean", "recording_month", "users_flagged"):
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{DATA_DIR / t}.parquet')")
    b = " + ".join(_col(m) for m in BASELINE_MONTHS)
    r = " + ".join(_col(m) for m in RECENT_MONTHS)
    # D7: baseline/recent = average monthly distinct listeners; growth = (recent - baseline) / baseline
    con.execute(f"""
        CREATE VIEW artist_metrics AS
        SELECT artist_id, artist_mbid, name, artist_type, country, top_genres,
               CAST(first_release_date AS DATE) AS first_release_date,
               ({b}) / 3.0 AS baseline,
               ({r}) / 3.0 AS recent,
               (({r}) - ({b})) / NULLIF({b}, 0) AS growth
        FROM artists_clean""")
    return con


def _df(sql, params=()):
    # One cursor per call: DuckDB connections are not thread-safe, and the API serves requests in parallel.
    return _con().cursor().execute(sql, list(params)).df()


@lru_cache(maxsize=32)
def thresholds(min_baseline=5, size_pct=0.90, growth_pct=0.90):
    """D8 cutoffs, computed over all artists with baseline >= min_baseline.
    Returns {'recent_cutoff': listeners/month, 'growth_cutoff': proportion, 'n_scored': artists}."""
    row = _con().cursor().execute("""
        SELECT quantile_cont(recent, ?), quantile_cont(growth, ?), count(*)
        FROM artist_metrics WHERE baseline >= ?""", [size_pct, growth_pct, min_baseline]).fetchone()
    return {"recent_cutoff": row[0], "growth_cutoff": row[1], "n_scored": row[2]}


def shortlist(min_release=DEFAULTS["min_release"], min_baseline=5, size_pct=0.90, growth_pct=0.90,
              genre=None, country=None):
    """Emerging artists (D8), fastest-growing first.
    genre: one genre from genre_options() or None for all; country: ISO code or None for all.
    Percentiles are computed before the genre/country filters, so filtering never moves the cutoffs."""
    t = thresholds(min_baseline, size_pct, growth_pct)
    sql = """SELECT artist_id, artist_mbid, name, artist_type, country, top_genres, first_release_date,
                    baseline, recent, growth
             FROM artist_metrics
             WHERE baseline >= ? AND recent <= ? AND growth >= ? AND first_release_date >= CAST(? AS DATE)"""
    params = [min_baseline, t["recent_cutoff"], t["growth_cutoff"], min_release]
    if genre:
        sql += " AND list_contains(string_split(top_genres, '; '), ?)"
        params.append(genre)
    if country:
        sql += " AND country = ?"
        params.append(country)
    return _df(sql + " ORDER BY growth DESC, recent DESC", params)


def artist_profile(artist_id):
    """One artist's metadata and metrics (one-row DataFrame)."""
    return _df("SELECT * FROM artist_metrics WHERE artist_id = ?", [artist_id])


def artist_trend(artist_id):
    """Monthly distinct listeners and listens, Mar-Aug 2026; months with no listens are 0."""
    return _df(f"""
        SELECT m.month, coalesce(am.listeners, 0) AS listeners, coalesce(am.listens, 0) AS listens
        FROM (SELECT unnest({list(MONTHS)}) AS month) m
        LEFT JOIN artist_month_clean am ON am.month = m.month AND am.artist_id = ?
        ORDER BY m.month""", [artist_id])


def fans_also_play(artist_id, n=10):
    """D9 taste community: established artists (recent above the default size cutoff) ranked by
    the share of this artist's listeners who also listen to them."""
    cutoff = thresholds()["recent_cutoff"]
    return _df("""
        WITH fans AS (SELECT user_id FROM user_artist_clean WHERE artist_id = ?)
        SELECT a.artist_id, a.name, a.top_genres, a.recent,
               count(*) AS shared_listeners,
               count(*) / (SELECT count(*) FROM fans) AS share_of_fans
        FROM user_artist_clean ua
        JOIN fans USING (user_id)
        JOIN artist_metrics a ON a.artist_id = ua.artist_id
        WHERE ua.artist_id <> ? AND a.recent > ?
        GROUP BY ALL
        ORDER BY shared_listeners DESC, a.name
        LIMIT ?""", [artist_id, artist_id, cutoff, n])


@lru_cache(maxsize=256)
def top_tracks(artist_id, n=5):
    """Tracks driving the artist, ranked by recent average monthly listeners.
    Track titles are not in the data; `url` opens the recording on MusicBrainz.
    ponytail: scans recording_month (1.2 GB) per call, ~seconds; pre-partition by artist if too slow."""
    rec = ", ".join(str(m) for m in RECENT_MONTHS)
    return _df(f"""
        SELECT recording_mbid,
               'https://musicbrainz.org/recording/' || recording_mbid AS url,
               sum(listeners) FILTER (WHERE month IN ({rec})) / 3.0 AS recent,
               sum(listeners) FILTER (WHERE month NOT IN ({rec})) / 3.0 AS baseline,
               sum(listens) AS listens
        FROM recording_month
        WHERE artist_mbid = (SELECT artist_mbid FROM artists_clean WHERE artist_id = ?)
        GROUP BY recording_mbid
        ORDER BY recent DESC NULLS LAST, listens DESC
        LIMIT ?""", [artist_id, n]).fillna({"recent": 0, "baseline": 0})


@lru_cache(maxsize=1)
def genre_options(top=40):
    """Most common genres among scored artists (baseline >= 5), for the genre filter."""
    return _df("""
        SELECT g AS genre, count(*) AS artists
        FROM (SELECT unnest(string_split(top_genres, '; ')) AS g FROM artist_metrics
              WHERE baseline >= 5 AND top_genres IS NOT NULL)
        GROUP BY g ORDER BY artists DESC, g LIMIT ?""", [top])


@lru_cache(maxsize=1)
def country_options():
    """Countries present among scored artists, for the country filter."""
    return _df("""SELECT country, count(*) AS artists FROM artist_metrics
                  WHERE baseline >= 5 AND country IS NOT NULL
                  GROUP BY country ORDER BY artists DESC, country""")


def data_summary():
    """Headline facts quoted in BUILD_SPEC.md / DATA_DECISIONS.md, computed from the data (dict)."""
    c = _con().cursor()
    one = lambda q: c.execute(q).fetchone()
    users, bots, bot_listens, all_listens = one("""
        SELECT count(*), count(*) FILTER (WHERE excluded_bot),
               sum(listens_total) FILTER (WHERE excluded_bot), sum(listens_total) FROM users_flagged""")
    s = shortlist()
    return {
        "artists": one("SELECT count(*) FROM artists_clean")[0],
        "artists_scored (baseline >= 5)": thresholds()["n_scored"],
        "artist_credited_listens_clean": int(one("SELECT sum(listens) FROM artist_month_clean")[0]),
        "users": users,
        "users_excluded_as_bots": bots,
        "share_of_listens_from_bots": round(bot_listens / all_listens, 3),
        "shortlist_default": len(s),
        "shortlist_share_without_genre": round(float(s.top_genres.isna().mean()), 3),
    }


def _check():
    """Runs every function on the real data and asserts it matches DATA_DECISIONS.md."""
    t0 = time.time()
    t = thresholds()
    assert abs(t["recent_cutoff"] - 87.33) < 0.01 and abs(t["growth_cutoff"] - 0.2807) < 0.0001, t
    s = shortlist()
    assert len(s) == 1131, len(s)
    assert (s.baseline >= 5).all() and (s.recent <= t["recent_cutoff"]).all()
    assert (s.growth >= t["growth_cutoff"]).all()
    assert (pd.to_datetime(s.first_release_date) >= "2023-01-01").all()
    assert s.growth.is_monotonic_decreasing

    a = s.iloc[0]
    raw = _df("SELECT * FROM artists_clean WHERE artist_id = ?", [int(a.artist_id)]).iloc[0]
    base = sum(raw[_col(m)] for m in BASELINE_MONTHS) / 3
    rec = sum(raw[_col(m)] for m in RECENT_MONTHS) / 3
    assert abs(a.growth - (rec - base) / base) < 1e-9

    tr = artist_trend(int(a.artist_id))
    assert list(tr.month) == list(MONTHS)
    assert list(tr.listeners) == [raw[_col(m)] for m in MONTHS]

    g = genre_options().genre.iloc[0]
    sg = shortlist(genre=g)
    assert len(sg) <= len(s) and sg.top_genres.str.split("; ").apply(lambda x: g in x).all()
    c = country_options().country.iloc[0]
    assert (shortlist(country=c).country == c).all()

    f = fans_also_play(int(a.artist_id))
    assert len(f) <= 10 and (f.artist_id != a.artist_id).all()
    assert f.share_of_fans.between(0, 1).all() and (f.recent > t["recent_cutoff"]).all()

    tt = top_tracks(int(a.artist_id))
    assert len(tt) <= 5 and tt.recent.is_monotonic_decreasing
    assert len(artist_profile(int(a.artist_id))) == 1
    for k, v in data_summary().items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    print(f"ok: {len(s)} shortlisted, top = {a['name']} (+{a.growth:.0%}), "
          f"{len(f)} fans-also-play, {len(tt)} tracks, {time.time() - t0:.1f}s")


if __name__ == "__main__":
    _check()
