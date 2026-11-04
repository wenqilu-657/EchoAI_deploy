"""Backend analysis for the Emerging Artist Discovery dashboard (v2.0 - Hybrid Curation Suite).

Every public function returns a pandas DataFrame (or a dict) computed from the
canonical tables built by extraction/ (definitions: DATA_DECISIONS.md & BUILD_SPEC.md v2.0).
Nothing is printed or plotted here; the API and dashboard only call these.

Data folder resolution:
1. $DSO576_DATA environment variable
2. ~/dso576_data/clean
3. Project root: data/clean
"""
import os
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd


def _resolve_data_dir() -> Path:
    if "DSO576_DATA" in os.environ:
        d = Path(os.environ["DSO576_DATA"]).expanduser()
        if (d / "artists_clean.parquet").exists():
            return d
    home_d = Path("~/dso576_data/clean").expanduser()
    if (home_d / "artists_clean.parquet").exists():
        return home_d
    repo_d = Path(__file__).resolve().parent.parent / "data" / "clean"
    if (repo_d / "artists_clean.parquet").exists():
        return repo_d
    return home_d


DATA_DIR = _resolve_data_dir()
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
        parquet_path = DATA_DIR / f"{t}.parquet"
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{parquet_path}')")
    
    b = " + ".join(_col(m) for m in BASELINE_MONTHS)
    r = " + ".join(_col(m) for m in RECENT_MONTHS)

    # Precompute established benchmark artists for taste communities
    con.execute(f"""
        CREATE VIEW established_artists AS
        SELECT artist_id, name, top_genres, country,
               ({r}) / 3.0 AS recent
        FROM artists_clean
        WHERE ({r}) / 3.0 > 87.33
    """)

    # Precompute top soundalike match for each artist
    con.execute("""
        CREATE VIEW artist_soundalikes AS
        WITH fans_count AS (
            SELECT artist_id, count(distinct user_id) as total_fans
            FROM user_artist_clean
            GROUP BY artist_id
        ),
        overlap AS (
            SELECT ua1.artist_id AS target_id, ua2.artist_id AS est_id, e.name AS est_name,
                   count(distinct ua1.user_id) AS shared,
                   count(distinct ua1.user_id)::double / NULLIF(fc.total_fans, 0) AS share,
                   ROW_NUMBER() OVER (PARTITION BY ua1.artist_id ORDER BY count(distinct ua1.user_id) DESC, e.recent DESC) as rn
            FROM user_artist_clean ua1
            JOIN user_artist_clean ua2 ON ua1.user_id = ua2.user_id AND ua1.artist_id <> ua2.artist_id
            JOIN established_artists e ON e.artist_id = ua2.artist_id
            LEFT JOIN fans_count fc ON fc.artist_id = ua1.artist_id
            GROUP BY ua1.artist_id, ua2.artist_id, e.name, e.recent, fc.total_fans
        )
        SELECT target_id, est_id, est_name, shared, share FROM overlap WHERE rn = 1
    """)

    # Precompute engagement & retention telemetry:
    # 1. Stickiness ratio = total scrobbles / distinct listeners
    # 2. Audience retention = average months active across window
    # 3. Track dependency = top track recent listeners / artist recent listeners
    con.execute("""
        CREATE VIEW artist_engagement AS
        WITH listens_agg AS (
            SELECT artist_id, sum(listens) as total_listens, sum(listeners) as sum_listeners,
                   sum(listens)::double / NULLIF(sum(listeners), 0) as stickiness
            FROM artist_month_clean
            GROUP BY artist_id
        ),
        users_agg AS (
            SELECT artist_id, avg(months_active) as retention_months
            FROM user_artist_clean
            GROUP BY artist_id
        ),
        tracks_agg AS (
            SELECT artist_mbid, max(listeners)/3.0 as top_track_recent
            FROM recording_month
            WHERE month IN (202606, 202607, 202608)
            GROUP BY artist_mbid
        )
        SELECT a.artist_id,
               round(coalesce(la.stickiness, 1.0), 2) as stickiness,
               round(coalesce(ua.retention_months, 1.0), 1) as retention_months,
               round(coalesce(ta.top_track_recent, 0.0), 1) as top_track_recent
        FROM artists_clean a
        LEFT JOIN listens_agg la ON la.artist_id = a.artist_id
        LEFT JOIN users_agg ua ON ua.artist_id = a.artist_id
        LEFT JOIN tracks_agg ta ON ta.artist_mbid = a.artist_mbid
    """)

    # Master metrics view
    con.execute(f"""
        CREATE VIEW artist_metrics AS
        SELECT a.artist_id, a.artist_mbid, a.name, a.artist_type, a.country, a.top_genres,
               CAST(a.first_release_date AS DATE) AS first_release_date,
               ({b}) / 3.0 AS baseline,
               ({r}) / 3.0 AS recent,
               (({r}) - ({b})) AS net_listeners,
               (({r}) - ({b})) / NULLIF({b}, 0) AS growth,
               round((({r}) - ({b})) / NULLIF({b}, 0) * 100.0 * (1.0 + (({r}) - ({b})) / 50.0), 0) AS momentum_score,
               a.listeners_2026_03, a.listeners_2026_04, a.listeners_2026_05,
               a.listeners_2026_06, a.listeners_2026_07, a.listeners_2026_08,
               s.est_id AS soundalike_id,
               s.est_name AS soundalike_name,
               coalesce(s.share, 0.0) AS soundalike_share,
               eg.stickiness,
               eg.retention_months,
               round(least(1.0, coalesce(eg.top_track_recent / NULLIF(({r}) / 3.0, 0), 0.0)), 2) as track_dependency,
               CAST(CASE WHEN CAST(a.first_release_date AS DATE) >= '2026-06-01' AND ({b}) > 0 THEN true ELSE false END AS BOOLEAN) AS listened_before_catalogued
        FROM artists_clean a
        LEFT JOIN artist_soundalikes s ON s.target_id = a.artist_id
        LEFT JOIN artist_engagement eg ON eg.artist_id = a.artist_id
    """)
    return con


def _df(sql, params=()):
    return _con().cursor().execute(sql, list(params)).df()


@lru_cache(maxsize=32)
def thresholds(min_baseline=5, size_pct=0.90, growth_pct=0.90):
    """D8 cutoffs, computed over all artists with baseline >= min_baseline.
    Returns {'recent_cutoff': listeners/month, 'growth_cutoff': proportion, 'n_scored': artists}."""
    row = _con().cursor().execute("""
        SELECT quantile_cont(recent, ?), quantile_cont(growth, ?), count(*)
        FROM artist_metrics WHERE baseline >= ?""", [size_pct, growth_pct, min_baseline]).fetchone()
    return {"recent_cutoff": float(row[0]), "growth_cutoff": float(row[1]), "n_scored": int(row[2])}


def seed_options():
    """Established benchmark acts (recent > 87.3/mo) for the Seed Artist Matchmaker."""
    return _df("""
        SELECT artist_id, name, country, top_genres, recent
        FROM established_artists
        ORDER BY recent DESC
    """)


def shortlist(min_release=DEFAULTS["min_release"], min_baseline=5, size_pct=0.90, growth_pct=0.90,
              genre: Optional[str] = None, country: Optional[str] = None, preset: Optional[str] = None,
              seed_id: Optional[int] = None, velocity: Optional[str] = None,
              size_tier: Optional[str] = None, search: Optional[str] = None,
              scope: str = "emerging", status: Optional[str] = None,
              sort_by: Optional[str] = "growth_desc"):
    """Artists from the catalog. scope='emerging' filters for the qualified shortlist (D8).
    scope='all' returns the broader artist population for exploration and benchmarking."""
    t = thresholds(min_baseline, size_pct, growth_pct)

    cols = f"""artist_id, artist_mbid, name, artist_type, country, top_genres, first_release_date,
               baseline, recent, net_listeners, growth, momentum_score,
               listeners_2026_03, listeners_2026_04, listeners_2026_05,
               listeners_2026_06, listeners_2026_07, listeners_2026_08,
               soundalike_id, soundalike_name, soundalike_share,
               stickiness, retention_months, track_dependency,
               listened_before_catalogued,
               CAST(CASE WHEN baseline >= ? AND recent <= ? AND growth >= ? AND first_release_date >= CAST(? AS DATE) THEN true ELSE false END AS BOOLEAN) AS is_emerging,
               CASE
                 WHEN baseline >= ? AND recent <= ? AND growth >= ? AND first_release_date >= CAST(? AS DATE) THEN 'emerging'
                 WHEN recent > ? THEN 'established'
                 ELSE 'candidate'
               END AS artist_status"""

    params = [
        min_baseline, t["recent_cutoff"], t["growth_cutoff"], min_release,
        min_baseline, t["recent_cutoff"], t["growth_cutoff"], min_release,
        t["recent_cutoff"]
    ]

    where_clauses = []

    # If scope is 'emerging' and user did not specify status or type a search, enforce emerging gate
    if (scope == "emerging" or status == "emerging") and not (status and status != "emerging") and not search:
        where_clauses.append("baseline >= ? AND recent <= ? AND growth >= ? AND first_release_date >= CAST(? AS DATE)")
        params.extend([min_baseline, t["recent_cutoff"], t["growth_cutoff"], min_release])

        # AUDIT-02: Preset categorization & baseline activity gate
        if preset == "steady":
            where_clauses.append("listeners_2026_03 > 0 AND listeners_2026_04 > 0 AND listeners_2026_05 > 0")
        elif preset == "debut":
            where_clauses.append("(listeners_2026_03 = 0 OR listeners_2026_04 = 0 OR listeners_2026_05 = 0)")
        else:
            where_clauses.append("""(
                (CASE WHEN listeners_2026_03 > 0 THEN 1 ELSE 0 END) +
                (CASE WHEN listeners_2026_04 > 0 THEN 1 ELSE 0 END) +
                (CASE WHEN listeners_2026_05 > 0 THEN 1 ELSE 0 END)
            ) >= 2""")

    if status == "established":
        where_clauses.append("recent > ?")
        params.append(t["recent_cutoff"])
    elif status == "candidate":
        where_clauses.append("(NOT (baseline >= ? AND recent <= ? AND growth >= ? AND first_release_date >= CAST(? AS DATE)) AND recent <= ?)")
        params.extend([min_baseline, t["recent_cutoff"], t["growth_cutoff"], min_release, t["recent_cutoff"]])

    if genre:
        where_clauses.append("list_contains(string_split(top_genres, '; '), ?)")
        params.append(genre)

    if country:
        if country == "Unknown":
            where_clauses.append("(country IS NULL OR country = '' OR country = 'Unknown')")
        else:
            where_clauses.append("country = ?")
            params.append(country)

    # Seed Artist Matchmaker (co-listening audience match)
    if seed_id:
        where_clauses.append("""artist_id IN (
            SELECT ua1.artist_id
            FROM user_artist_clean ua1
            JOIN user_artist_clean ua2 ON ua1.user_id = ua2.user_id
            WHERE ua2.artist_id = ?
        )""")
        params.append(int(seed_id))

    # Velocity Filter
    if velocity == "explosive":
        where_clauses.append("growth >= 5.0")
    elif velocity == "surging":
        where_clauses.append("growth >= 1.0 AND growth < 5.0")
    elif velocity == "steady":
        where_clauses.append("growth < 1.0")

    # Audience Size Tier Filter
    if size_tier == "micro":
        where_clauses.append("recent < 50.0")
    elif size_tier == "developing":
        where_clauses.append("recent >= 50.0 AND recent <= 300.0")
    elif size_tier == "mainstream":
        where_clauses.append("recent > 300.0")

    # Text Search Filter
    if search:
        search_term = f"%{search.strip().lower()}%"
        where_clauses.append("(lower(name) LIKE ? OR lower(coalesce(top_genres, '')) LIKE ? OR lower(coalesce(soundalike_name, '')) LIKE ?)")
        params.extend([search_term, search_term, search_term])

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    
    # Sorting
    if sort_by == "listeners_desc":
        order_sql = " ORDER BY recent DESC, growth DESC"
    elif sort_by == "listeners_asc":
        order_sql = " ORDER BY recent ASC, growth DESC"
    elif sort_by == "name_asc":
        order_sql = " ORDER BY name ASC"
    else:
        order_sql = " ORDER BY growth DESC, recent DESC"

    sql = f"SELECT {cols} FROM artist_metrics{where_sql}{order_sql}"

    return _df(sql, params)


def artist_profile(artist_id: int):
    """One artist's metadata and metrics (one-row DataFrame)."""
    return _df("SELECT * FROM artist_metrics WHERE artist_id = ?", [artist_id])


def artist_trend(artist_id: int):
    """Monthly distinct listeners and listens, Mar-Aug 2026; months with no listens are 0."""
    return _df(f"""
        SELECT m.month, coalesce(am.listeners, 0) AS listeners, coalesce(am.listens, 0) AS listens
        FROM (SELECT unnest({list(MONTHS)}) AS month) m
        LEFT JOIN artist_month_clean am ON am.month = m.month AND am.artist_id = ?
        ORDER BY m.month""", [artist_id])


def fans_also_play(artist_id: int, n: int = 10):
    """D9 taste community: established artists ranked by share of shared listeners."""
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
def top_tracks(artist_id: int, n: int = 5):
    """Tracks driving the artist, ranked by recent average monthly listeners.
    Track titles are not in the raw scrobbles; `url` opens the recording on MusicBrainz."""
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
def genre_options(top: int = 40):
    """Most common genres among scored artists (baseline >= 5), for the genre filter."""
    return _df("""
        SELECT g AS genre, count(*) AS artists
        FROM (SELECT unnest(string_split(top_genres, '; ')) AS g FROM artist_metrics
              WHERE baseline >= 5 AND top_genres IS NOT NULL)
        GROUP BY g ORDER BY artists DESC, g LIMIT ?""", [top])


@lru_cache(maxsize=1)
def country_options():
    """Countries present among scored artists, for the country filter (including 'Unknown')."""
    df = _df("""SELECT country, count(*) AS artists FROM artist_metrics
                  WHERE baseline >= 5 AND country IS NOT NULL AND country != ''
                  GROUP BY country ORDER BY artists DESC, country""")
    # AUDIT-04: explicitly add 'Unknown' if artists without country exist
    unk_count = _con().cursor().execute("""
        SELECT count(*) FROM artist_metrics WHERE baseline >= 5 AND (country IS NULL OR country = '')
    """).fetchone()[0]
    if unk_count > 0:
        unk_row = pd.DataFrame([{"country": "Unknown", "artists": int(unk_count)}])
        df = pd.concat([df, unk_row], ignore_index=True)
    return df


def data_summary():
    """Headline facts computed from the loaded tables."""
    c = _con().cursor()
    one = lambda q: c.execute(q).fetchone()
    users, bots, bot_listens, all_listens = one("""
        SELECT count(*), count(*) FILTER (WHERE excluded_bot),
               sum(listens_total) FILTER (WHERE excluded_bot), sum(listens_total) FROM users_flagged""")
    s = shortlist()
    return {
        "data_dir": str(DATA_DIR),
        "artists": one("SELECT count(*) FROM artists_clean")[0],
        "artists_scored (baseline >= 5)": thresholds()["n_scored"],
        "artist_credited_listens_clean": int(one("SELECT sum(listens) FROM artist_month_clean")[0]),
        "users": users,
        "users_excluded_as_bots": bots,
        "share_of_listens_from_bots": round(bot_listens / all_listens, 3) if all_listens else 0.0,
        "shortlist_default": len(s),
        "shortlist_share_without_genre": round(float(s.top_genres.isna().mean()), 3) if len(s) else 0.0,
    }


def _check():
    """Runs every function on the loaded data and asserts sanity."""
    t0 = time.time()
    t = thresholds()
    s = shortlist()
    assert len(s) > 0, "Shortlist must not be empty"
    assert (s.baseline >= 5).all() and (s.recent <= t["recent_cutoff"] + 1e-6).all()
    assert (s.growth >= t["growth_cutoff"] - 1e-6).all()
    assert (pd.to_datetime(s.first_release_date) >= "2023-01-01").all()
    assert s.growth.is_monotonic_decreasing

    if t["n_scored"] > 1000:
        assert abs(t["recent_cutoff"] - 87.33) < 0.01 and abs(t["growth_cutoff"] - 0.2807) < 0.0001, t

    a = s.iloc[0]
    raw = _df("SELECT * FROM artists_clean WHERE artist_id = ?", [int(a.artist_id)]).iloc[0]
    base = sum(raw[_col(m)] for m in BASELINE_MONTHS) / 3
    rec = sum(raw[_col(m)] for m in RECENT_MONTHS) / 3
    assert abs(a.growth - (rec - base) / base) < 1e-9

    tr = artist_trend(int(a.artist_id))
    assert list(tr.month) == list(MONTHS)
    assert list(tr.listeners) == [raw[_col(m)] for m in MONTHS]

    seeds = seed_options()
    assert len(seeds) > 0, "Seeds must not be empty"

    f = fans_also_play(int(a.artist_id))
    assert (f.artist_id != a.artist_id).all()
    assert f.share_of_fans.between(0, 1).all()

    tt = top_tracks(int(a.artist_id))
    assert len(tt) <= 5 and tt.recent.is_monotonic_decreasing
    assert len(artist_profile(int(a.artist_id))) == 1

    for k, v in data_summary().items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    print(f"ok: {len(s)} shortlisted, top = {a['name']} (+{a.growth:.0%}), "
          f"{len(f)} fans-also-play, {len(tt)} tracks, {time.time() - t0:.1f}s")


if __name__ == "__main__":
    _check()
