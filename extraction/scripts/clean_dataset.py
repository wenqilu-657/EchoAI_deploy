"""Clean the Vision B dataset (rules R1-R12).

Reads, never modifies:
    <data-dir>/listens/part-*.parquet   raw listens (load_listenbrainz.py)
    <data-dir>/musicbrainz/*.parquet    MusicBrainz tables (build_dataset.py)
    <data-dir>/dataset/artists.parquet  artist metadata joined by build_dataset.py

Listen rules are applied to the raw listens, because the built aggregates
already count duplicate listens and bot accounts:
    R1  keep listens inside the window [--start, --end)
    R2  drop exact duplicate listens (same user, time, recording, credit, name)
    R3  keep repeated (user, time) pairs with different recordings, but count them
    R4  exclude users with any UTC day above --bot-max-daily-listens listens
    R5  listens without an artist MBID count toward user activity only
    R6  MBIDs of merged artists are mapped to the surviving artist
    R7  a listen counts once for every distinct artist on its credit
Artist rules:
    R8  drop MusicBrainz special-purpose artists (Various Artists, [unknown], ...)
    R9  add a normalized name_key; keep the original name
    R10 convert types (nullable integers, dates with precision)
    R11 null and flag impossible dates (first release or begin date after the
        MusicBrainz export); flag unusual ones (announced releases, pre-1900)
    R12 keep missing profile values missing; add has_* flags; zero-fill months

Output under <data-dir>/clean/ (outside Git):
    artists_clean.parquet          one row per artist with >= 1 clean listen
    artist_month_clean.parquet     clean listens/listeners per artist and month
    user_artist_clean.parquet      clean listens per user and artist (window)
    user_artist_month_all.parquet  after R1-R3 and R5-R7 but before R4 and R8
                                   (all users; for sensitivity and record checks)
    users_flagged.parquet          per-user activity and bot flags
    cleaning_log.csv               row and listen counts before/after each rule
    listen_month_log.csv           the listen-rule counts per month
    bot_sensitivity.csv            users/listens removed at each bot threshold
    top20_by_threshold.csv         top 20 artists by listens with no bot rule,
                                   at --bot-sensitivity, and at the chosen limit

Example:
    python scripts/clean_dataset.py --data-dir ~/dso576_data
"""

import argparse
import glob
import os
import re
import sys
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_dataset import artist_lookup, log, part_number, parts_to_date, write_atomic  # noqa: E402

# MusicBrainz special-purpose artists (https://musicbrainz.org/doc/Style/Unknown_and_untitled/Special_purpose_artist).
# Matched by MBID, not name: real artists such as "[Alexandros]" have bracketed
# names, and a German producer is called "Various Artists".
SPECIAL_ARTISTS = {
    "89ad4ac3-39f7-470e-963a-56509c546377": "Various Artists",
    "125ec42a-7229-4250-afc5-e057484327fe": "[unknown]",
    "f731ccc4-e22a-43af-a747-64213329e088": "[anonymous]",
    "eec63d3c-3b81-4ad4-b1e4-7c147d4d2b61": "[no artist]",
    "33cf029c-63b0-41a0-9855-be2a3665fb3b": "[data]",
    "314e1c25-dde7-4e4d-b2f4-0a7b9f7c56dc": "[dialogue]",
    "9be7f096-97ec-4615-8957-8d40b5dcbc41": "[traditional]",
    "a0ef7e1d-44ff-4039-9435-7d5fefdeecc9": "[theatre]",
    "66ea0139-149f-4a0c-8fbf-5ea9ec4a6e49": "[Disney]",
    "90068d37-bae7-4292-be4a-704c145bd616": "[church chimes]",
    "80a8851f-444c-4539-892b-ad2a49292aa9": "[language instruction]",
    "459a4aa6-b6b7-4c89-a42b-03acddbe1f80": "[unknown animal]",
    "7e84f845-ac16-41fe-9ff8-df12eb32af55": "MusicBrainz Test Artist",
}
LISTEN_COLUMNS = ["user_id", "listened_at", "recording_mbid", "artist_name", "artist_credit_mbids"]
DASHES = re.compile("[‐-―−﹘﹣－]")
QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
LISTEN_STEPS = [
    ("raw", "R1", "rows in the raw parts"),
    ("in_window", "R1", "inside the window"),
    ("deduplicated", "R2", "after dropping exact duplicate listens"),
    ("repeated_user_time", "R3", "listens sharing (user, time) with another listen; kept"),
    ("no_mbid", "R5", "listens without an artist MBID; user activity only"),
    ("unmapped", "R5", "listens whose MBIDs are not MusicBrainz artists"),
    ("mapped", "R6", "listens credited to >= 1 MusicBrainz artist"),
    ("redirected", "R6", "mapped listens that needed a merged-artist redirect"),
    ("credit_pairs", "R7", "(listen, artist) pairs before removing repeats on one credit"),
    ("artist_listens", "R7", "(listen, artist) pairs counted"),
]


# --- Listens (R1-R3, R5-R7) ---------------------------------------------------

def clean_part(path, lookup, ids, n_current, start, end):
    """Apply R1-R3 and R5-R7 to one raw part.

    Returns (user x artist x month counts, user x day counts, per-month stats).
    """
    t = pq.read_table(path, columns=LISTEN_COLUMNS)
    raw = t.num_rows
    ts = t["listened_at"]
    t = t.filter(pc.and_(pc.greater_equal(ts, pa.scalar(start, ts.type)), pc.less(ts, pa.scalar(end, ts.type))))

    def month_of(ts):
        return pc.add(pc.multiply(pc.year(ts), 100), pc.month(ts)).to_numpy().astype(np.int32)

    stats = pd.DataFrame({"in_window": pd.Series(month_of(t["listened_at"])).value_counts()})

    # R2: a credit is a list, so compare it as one joined string. group_by with no
    # aggregations returns the distinct rows; nulls compare equal to each other.
    t = t.append_column("credit_key", pc.binary_join(t["artist_credit_mbids"], ",")).drop_columns(["artist_credit_mbids"])
    t = t.group_by(["user_id", "listened_at", "recording_mbid", "artist_name", "credit_key"]).aggregate([])
    month = month_of(t["listened_at"])
    day = pc.cast(t["listened_at"], pa.date32()).to_numpy().astype("datetime64[D]").astype(np.int32)
    user = t["user_id"].to_numpy().astype(np.int32)

    # R3: count, do not drop.
    per_time = t.group_by(["user_id", "listened_at"]).aggregate([("user_id", "count")])
    repeated = per_time.filter(pc.greater(per_time["user_id_count"], 1))
    repeated_rows = pd.Series(month_of(repeated["listened_at"])).repeat(repeated["user_id_count"].to_numpy())

    # R5-R7: map MBIDs (current artists first, then merge redirects).
    credit_key = t["credit_key"].combine_chunks()
    has_mbid = pc.fill_null(pc.greater(pc.utf8_length(credit_key), 0), False).to_numpy(zero_copy_only=False)
    credits = pc.split_pattern(credit_key, ",")
    flat = pc.dictionary_encode(pc.list_flatten(credits))
    row = pc.list_parent_indices(credits).to_numpy()
    codes = lookup.get_indexer(flat.dictionary.to_numpy(zero_copy_only=False))[flat.indices.to_numpy()]
    mapped = codes >= 0
    row, codes = row[mapped], codes[mapped]
    artist = ids[codes]
    redirected = np.zeros(t.num_rows, bool)
    redirected[row[codes >= n_current]] = True
    credit_pairs = pd.Series(month[row]).value_counts()
    key = np.unique((row.astype(np.int64) << 32) | artist.astype(np.int64))
    row, artist = (key >> 32).astype(np.int64), (key & 0xFFFFFFFF).astype(np.int32)
    has_mapped = np.zeros(t.num_rows, bool)
    has_mapped[row] = True

    flags = pd.DataFrame({
        "month": month,
        "deduplicated": 1,
        "no_mbid": ~has_mbid,
        "unmapped": has_mbid & ~has_mapped,
        "mapped": has_mapped,
        "redirected": redirected & has_mapped,
    })
    stats = stats.join(flags.groupby("month").sum(), how="outer")
    stats["repeated_user_time"] = repeated_rows.value_counts()
    stats["credit_pairs"] = credit_pairs
    stats["artist_listens"] = pd.Series(month[row]).value_counts()
    stats = stats.fillna(0).astype(np.int64)

    pairs = pa.table({"month": month[row], "user_id": user[row], "artist_id": artist})
    counts = pairs.group_by(["month", "user_id", "artist_id"]).aggregate([("artist_id", "count")])
    counts = counts.rename_columns(["month", "user_id", "artist_id", "listens"])
    user_day = pa.table({"user_id": user, "day": day}).group_by(["user_id", "day"]).aggregate([("day", "count")])
    return counts, user_day.rename_columns(["user_id", "day", "listens"]), stats, raw


def clean_listens(data_dir, start, end):
    mb_dir = os.path.join(data_dir, "musicbrainz")
    files = sorted(glob.glob(os.path.join(data_dir, "listens", "part-*.parquet")), key=part_number)
    if not files:
        sys.exit("no listen parts; run load_listenbrainz.py first")
    lookup, ids = artist_lookup(mb_dir)
    n_current = pq.ParquetFile(os.path.join(mb_dir, "artist.parquet")).metadata.num_rows
    log(f"cleaning {len(files)} listen parts, window {start:%Y-%m-%d} to {end:%Y-%m-%d} (exclusive)")

    counts, user_days, stats, raw = [], [], [], 0
    for i, path in enumerate(files, 1):
        c, ud, s, r = clean_part(path, lookup, ids, n_current, start, end)
        counts.append(c)
        user_days.append(ud)
        stats.append(s)
        raw += r
        if i % 10 == 0 or i == len(files):
            log(f"  {i}/{len(files)} parts")

    # Parts can split a month (and, at a boundary second, a duplicate pair), so
    # sum the partial counts. Exact duplicates split across two parts are not
    # removed; listen_month_log.csv shows how many listens sit at part edges.
    uam = pa.concat_tables(counts).group_by(["month", "user_id", "artist_id"]).aggregate([("listens", "sum")])
    uam = uam.rename_columns(["month", "user_id", "artist_id", "listens"])
    ud = pa.concat_tables(user_days).group_by(["user_id", "day"]).aggregate([("listens", "sum")])
    ud = ud.rename_columns(["user_id", "day", "listens"]).to_pandas()
    month_log = pd.concat(stats).groupby(level=0).sum()
    month_log.index.name = "month"
    return uam, ud, month_log, raw


def flag_users(ud, limit, sensitivity):
    users = ud.groupby("user_id").agg(
        listens_total=("listens", "sum"),
        active_days=("listens", "size"),
        max_listens_per_day=("listens", "max"),
    )
    users[f"over_{sensitivity}_per_day"] = users["max_listens_per_day"] > sensitivity
    users[f"over_{limit}_per_day"] = users["max_listens_per_day"] > limit
    users["excluded_bot"] = users[f"over_{limit}_per_day"]
    return users.reset_index()


# --- Artists (R8-R12) ---------------------------------------------------------

def name_key(name):
    """Comparison key: Unicode-normalized, case-folded, one kind of dash and quote."""
    if not isinstance(name, str):
        return pd.NA
    s = unicodedata.normalize("NFKC", name).translate(QUOTES)
    return " ".join(DASHES.sub("-", s).casefold().split())


def to_int(df, columns, log_rows):
    """R10: float columns holding whole numbers -> nullable Int64; count failures."""
    for col in columns:
        s = df[col]
        bad = s.notna() & (s != s.round())
        log_rows.append({"rule": "R10", "column": col, "from": str(s.dtype), "to": "Int64", "failed": int(bad.sum())})
        df[col] = s.where(~bad).round().astype("Int64")


def build_date(df, prefix):
    """R10: year/month/day parts -> date (missing month/day = 1st) + precision; count failures."""
    y, m, d = (df[f"{prefix}_{p}"] for p in ("year", "month", "day"))
    date = parts_to_date(y, m, d)
    precision = pd.Series(pd.NA, index=df.index, dtype="string")
    precision[y.notna()] = "year"
    precision[y.notna() & m.notna()] = "month"
    precision[y.notna() & m.notna() & d.notna()] = "day"
    failed = int((y.notna() & date.isna()).sum())
    return date, precision, failed


def clean_artists(data_dir, listening, month_cols, export_date, args, log_rows):
    built = pd.read_parquet(os.path.join(data_dir, "dataset", "artists.parquet"))
    old_listen_cols = ["listens_total", "listeners_total", "months_with_listens",
                       "first_listen_month", "last_listen_month", "peak_month_listeners"]
    a = built.drop(columns=old_listen_cols)

    # Recomputed clean listening replaces the built (uncleaned) totals. Inner join:
    # artists whose every listen was a duplicate or from a bot drop out here.
    missing = set(listening.index) - set(a["artist_id"])
    if missing:
        raise RuntimeError(f"{len(missing)} clean artists missing from dataset/artists.parquet; rebuild it")
    a = a.merge(listening, left_on="artist_id", right_index=True, how="inner", validate="one_to_one")

    # R9: text. Keep name as published; add a comparison key.
    for col in ["name", "sort_name", "disambiguation", "area_name"]:
        stripped = a[col].str.strip()
        log_rows.append({"rule": "R9", "column": col, "from": "whitespace", "to": "stripped",
                         "failed": 0, "changed": int((stripped.fillna("") != a[col].fillna("")).sum())})
        a[col] = stripped
    a["disambiguation"] = a["disambiguation"].replace("", pd.NA)
    a["name_key"] = a["name"].map(name_key).astype("string")
    log_rows.append({"rule": "R9", "column": "name_key", "from": "name", "to": "normalized key", "failed": 0,
                     "changed": int((a["name_key"] != a["name"].str.lower()).sum())})
    for col in ["top_tags", "top_genres"]:
        a[col] = a[col].map(lambda s: "; ".join(t.strip().lower() for t in s.split(";")) if isinstance(s, str) else pd.NA)
        a[col] = a[col].astype("string")

    # R10: types.
    int_cols = [c for c in a.columns if re.match(r"(begin|end)_date_(year|month|day)$", c)]
    int_cols += ["n_release_groups", "n_albums", "n_eps", "n_singles", "n_release_groups_in_window",
                 "rating", "rating_count"]
    to_int(a, int_cols, log_rows)
    for prefix in ["begin_date", "end_date"]:
        a[prefix], a[f"{prefix}_precision"], failed = build_date(a, prefix)
        log_rows.append({"rule": "R10", "column": prefix, "from": "year/month/day", "to": "datetime", "failed": failed})
    for col in ["artist_type", "gender", "area_type", "country", "begin_area_country"]:
        a[col] = a[col].astype("category")

    # R11: dates. Release dates after the MusicBrainz export are impossible for
    # artists already being listened to; begin years after it likewise.
    a["flag_future_first_release"] = a["first_release_date"] > export_date
    a.loc[a["flag_future_first_release"], "first_release_date"] = pd.NaT
    # A latest release after the export is an announced release: unusual, kept.
    a["flag_future_last_release"] = a["last_release_date"] > export_date
    a["flag_pre1900_first_release"] = a["first_release_date"] < pd.Timestamp("1900-01-01")
    a["flag_future_begin"] = a["begin_date"] > export_date
    a.loc[a["flag_future_begin"], ["begin_date", "begin_date_year", "begin_date_month", "begin_date_day"]] = pd.NA
    a["flag_end_before_begin"] = a["end_date"] < a["begin_date"]
    a["flag_ended_without_date"] = a["ended"] & a["end_date"].isna()

    # R12: missing values stay missing; flags make them countable.
    a["has_country"] = a["country"].notna()
    a["has_genre"] = a["top_genres"].notna()
    a["has_release_history"] = a["n_release_groups"].notna()
    a["has_rating"] = a["rating"].notna()
    for col in month_cols:
        a[col] = a[col].fillna(0).astype("int64")

    # Metrics for the business question (records counted in cleaning.ipynb).
    listener_cols = [c for c in month_cols if c.startswith("listeners_")]
    lf, ll = a[listener_cols[0]], a[listener_cols[-1]]
    a["listener_growth"] = (ll - lf) / lf.where(lf > 0)
    a["flag_single_listener"] = a["listeners_total"] == 1
    a["is_emerging_candidate"] = (
        (a["first_release_date"] >= pd.Timestamp(args.emerging_since))
        & (a["listeners_total"] >= args.emerging_min_listeners)
    ).fillna(False)

    order = ["artist_id", "artist_mbid", "name", "name_key", "sort_name", "disambiguation",
             "artist_type", "gender", "area_name", "area_type", "country", "begin_area_country",
             "begin_date", "begin_date_precision", "begin_date_year", "begin_date_month", "begin_date_day",
             "end_date", "end_date_precision", "end_date_year", "end_date_month", "end_date_day", "ended",
             "first_release_date", "last_release_date", "n_release_groups", "n_albums", "n_eps", "n_singles",
             "n_release_groups_in_window", "top_tags", "top_genres", "rating", "rating_count"]
    rest = [c for c in a.columns if c not in order]
    return a[order + rest].sort_values("listens_total", ascending=False, ignore_index=True), len(built)


# --- Main ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="~/dso576_data")
    ap.add_argument("--start", default="2026-06-01", help="window start, inclusive (R1)")
    ap.add_argument("--end", default="2026-09-01", help="window end, exclusive (R1)")
    ap.add_argument("--bot-max-daily-listens", type=int, default=500, help="R4: exclude users above this in any day")
    ap.add_argument("--bot-sensitivity", type=int, default=1000, help="second threshold reported for comparison")
    ap.add_argument("--emerging-since", default="2023-01-01", help="provisional: first release on or after")
    ap.add_argument("--emerging-min-listeners", type=int, default=20, help="provisional: clean listeners in window")
    args = ap.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    out = os.path.join(data_dir, "clean")
    os.makedirs(out, exist_ok=True)
    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    with open(os.path.join(data_dir, "musicbrainz", "EXPORT")) as f:
        export_date = pd.Timestamp(datetime.strptime(f.read().strip()[:8], "%Y%m%d"))

    # R1-R3, R5-R7
    uam, ud, month_log, raw = clean_listens(data_dir, start, end)
    month_log.reset_index().to_csv(os.path.join(out, "listen_month_log.csv"), index=False)
    write_atomic(uam, os.path.join(out, "user_artist_month_all.parquet"))

    # R4
    limit, sens = args.bot_max_daily_listens, args.bot_sensitivity
    users = flag_users(ud, limit, sens)
    write_atomic(pa.Table.from_pandas(users, preserve_index=False), os.path.join(out, "users_flagged.parquet"))
    uam = uam.to_pandas()
    bots = set(users.loc[users["excluded_bot"], "user_id"])

    sens_rows = []
    for name, threshold in [("none", None), (f"> {sens}", sens), (f"> {limit}", limit)]:
        flagged = users["max_listens_per_day"] > threshold if threshold else pd.Series(False, index=users.index)
        sens_rows.append({
            "bot_rule": name,
            "users_removed": int(flagged.sum()),
            "users_kept": int((~flagged).sum()),
            "listens_removed": int(users.loc[flagged, "listens_total"].sum()),
            "share_listens_removed": round(users.loc[flagged, "listens_total"].sum() / users["listens_total"].sum(), 4),
        })
    pd.DataFrame(sens_rows).to_csv(os.path.join(out, "bot_sensitivity.csv"), index=False)

    # R8
    mb_artist = pq.read_table(os.path.join(data_dir, "musicbrainz", "artist.parquet"), columns=["id", "gid", "name"]).to_pandas()
    special = mb_artist[mb_artist["gid"].isin(SPECIAL_ARTISTS)]
    wrong = special[special["name"] != special["gid"].map(SPECIAL_ARTISTS)]
    if len(wrong) or len(special) != len(SPECIAL_ARTISTS):
        raise RuntimeError(f"special-purpose artist list does not match MusicBrainz: {wrong.to_dict('records')}")
    special_ids = set(special["id"])

    names = mb_artist.set_index("id")["name"]
    top = {}
    for name, threshold in [("no bot rule", None), (f"bot > {sens}", sens), (f"bot > {limit}", limit)]:
        keep_users = users.loc[~(users["max_listens_per_day"] > threshold), "user_id"] if threshold else users["user_id"]
        sub = uam[uam["user_id"].isin(keep_users) & ~uam["artist_id"].isin(special_ids)]
        top[name] = sub.groupby("artist_id")["listens"].sum().nlargest(20)
    top20 = pd.DataFrame({k: v.index.map(names).tolist() for k, v in top.items()})
    top20.insert(0, "rank", range(1, 21))
    for k, v in top.items():
        top20[f"listens ({k})"] = v.to_numpy()
    top20.to_csv(os.path.join(out, "top20_by_threshold.csv"), index=False)

    # Clean user x artist x month, then artist x month and user x artist.
    rows_all, listens_all = len(uam), int(uam["listens"].sum())
    uam = uam[~uam["user_id"].isin(bots)]
    rows_nobot, listens_nobot = len(uam), int(uam["listens"].sum())
    uam = uam[~uam["artist_id"].isin(special_ids)]
    am = uam.groupby(["artist_id", "month"], as_index=False).agg(listens=("listens", "sum"), listeners=("user_id", "size"))
    ua = uam.groupby(["user_id", "artist_id"], as_index=False).agg(listens=("listens", "sum"), months_active=("month", "size"))
    write_atomic(pa.Table.from_pandas(am, preserve_index=False), os.path.join(out, "artist_month_clean.parquet"))
    write_atomic(pa.Table.from_pandas(ua, preserve_index=False), os.path.join(out, "user_artist_clean.parquet"))

    # Listening per artist: totals from user_artist (distinct listeners), months wide.
    label = {m: f"{m // 100}_{m % 100:02d}" for m in sorted(am["month"].unique())}
    wide_listeners = am.pivot(index="artist_id", columns="month", values="listeners").rename(columns=lambda m: f"listeners_{label[m]}")
    wide_listens = am.pivot(index="artist_id", columns="month", values="listens").rename(columns=lambda m: f"listens_{label[m]}")
    listening = ua.groupby("artist_id").agg(listens_total=("listens", "sum"), listeners_total=("user_id", "size"))
    listening["months_with_listens"] = am.groupby("artist_id").size()
    listening = listening.join(wide_listeners).join(wide_listens)
    month_cols = list(wide_listeners.columns) + list(wide_listens.columns)

    type_log = []
    artists, built_rows = clean_artists(data_dir, listening, month_cols, export_date, args, type_log)
    write_atomic(pa.Table.from_pandas(artists, preserve_index=False), os.path.join(out, "artists_clean.parquet"))
    pd.DataFrame(type_log).to_csv(os.path.join(out, "type_text_log.csv"), index=False)

    # Reconciliation (item 10).
    total = month_log.sum()
    log_rows = [{"rule": rule, "step": step, "table": "listens", "rows": int(raw if step == "raw" else total[step]), "note": note}
                for step, rule, note in LISTEN_STEPS]
    log_rows += [
        {"rule": "R4", "step": "user_artist_month, all users", "table": "user_artist_month", "rows": rows_all,
         "listens": listens_all, "note": "after R1-R3, R5-R7"},
        {"rule": "R4", "step": f"bots removed (> {limit}/day)", "table": "user_artist_month", "rows": rows_nobot,
         "listens": listens_nobot, "note": f"{len(bots)} users excluded"},
        {"rule": "R8", "step": "special-purpose artists removed", "table": "user_artist_month", "rows": len(uam),
         "listens": int(uam["listens"].sum()), "note": f"{len(special_ids)} special-purpose MBIDs"},
        {"rule": "-", "step": "artist_month_clean", "table": "artist_month", "rows": len(am), "listens": int(am["listens"].sum())},
        {"rule": "-", "step": "user_artist_clean", "table": "user_artist", "rows": len(ua), "listens": int(ua["listens"].sum())},
        {"rule": "-", "step": "built artists (dataset/artists.parquet)", "table": "artists", "rows": built_rows},
        {"rule": "R4/R8", "step": "artists_clean", "table": "artists", "rows": len(artists),
         "listens": int(artists["listens_total"].sum()), "note": "artists with >= 1 clean listen"},
    ]
    pd.DataFrame(log_rows).to_csv(os.path.join(out, "cleaning_log.csv"), index=False)
    log("cleaning log:\n" + pd.DataFrame(log_rows).drop(columns="note").to_string(index=False))
    log(f"bot sensitivity:\n{pd.DataFrame(sens_rows).to_string(index=False)}")
    log(f"artists_clean: {len(artists):,} rows x {artists.shape[1]} columns; "
        f"emerging candidates: {int(artists['is_emerging_candidate'].sum()):,}")


if __name__ == "__main__":
    sys.exit(main())
