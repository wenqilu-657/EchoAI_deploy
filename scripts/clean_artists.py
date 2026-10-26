"""Clean the MusicBrainz artist table (DSO 576 Module 6). Rules and reasons: plan.md.
Originals in data/raw/ are never modified.
Run from the repo root:  python scripts/clean_artists.py
Writes: data/clean/artist_clean.csv.gz (gitignored), output/sample_50_rows.json, output/cleaning_log.md
Exits non-zero if any row-count, key, or record check fails."""
import csv, json, re, sys, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

RAW, OUT_DATA, OUT_REP = Path("data/raw/mb/mbdump"), Path("data/clean"), Path("output")
DUMP_YEAR = 2026  # dump 20260930: a begin year after this is in the future
COLS = ["id", "gid", "name", "sort_name", "begin_year", "begin_month", "begin_day", "end_year", "end_month",
        "end_day", "type", "area", "gender", "comment", "edits_pending", "last_updated", "ended",
        "begin_area", "end_area"]
# R1: all strings; \N is missing; keep_default_na=False so a name like "NA" or "null" stays a name
READ = dict(sep="\t", header=None, na_values=["\\N"], keep_default_na=False, quoting=csv.QUOTE_NONE,
            dtype=str, encoding="utf-8")
LOG, FAILS = [], []


def note(rule, rows, what):
    LOG.append((rule, int(rows), what))
    print(f"[{rule}] {int(rows):,} rows - {what}", flush=True)


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


a = pd.read_csv(RAW / "artist", names=COLS, **READ)
n0, miss_before = len(a), a.isna().sum()
dup_rows_before = int(a.duplicated().sum())
CHECK_IDS = ["208838", "294902", "3249846", "653157"]
indigo_raw = int((a.name == "Indigo").sum())
for p in ("begin", "end"):  # keep the original date text so any fix can be audited
    parts = a[[f"{p}_year", f"{p}_month", f"{p}_day"]]
    a[f"{p}_date_raw"] = (parts.fillna("").agg("-".join, axis=1)).where(parts.notna().any(axis=1))
raw_checks = a[a.id.isin(CHECK_IDS)].set_index("id")  # original text, for the record checks
note("R1", n0, "loaded as text; \\N -> missing")

# R2 keys
assert a.gid.is_unique and a.id.is_unique, "id/gid must be unique"
note("R2", a.id.duplicated().sum() + a.gid.duplicated().sum(), "repeated id or gid (expect 0)")

# R3 text: decode the dump's backslash escapes; keep case/accents; flag (not change) non-NFC names
ESC = {"\\": "\\", "t": "\t", "n": "\n", "r": "\r"}
unescape = lambda s: re.sub(r"\\(.)", lambda m: ESC.get(m.group(1), m.group(0)), s)
for c in ("name", "sort_name", "comment"):
    m = a[c].str.contains("\\", regex=False)
    a.loc[m, c] = a.loc[m, c].map(unescape)
    note("R3", m.sum(), f"{c}: dump escapes decoded")
    if c == "name":
        name_decoded = m.to_numpy()
a["flag_name_not_nfc"] = a.name != a.name.map(lambda s: unicodedata.normalize("NFC", s))
note("R3", a.flag_name_not_nfc.sum(), "name not in NFC form (flagged, not changed)")

# R4 types
for c in ("begin_year", "begin_month", "begin_day", "end_year", "end_month", "end_day", "edits_pending"):
    v = pd.to_numeric(a[c], errors="coerce")
    note("R4", (a[c].notna() & v.isna()).sum(), f"{c}: failed numeric conversions (expect 0)")
    a[c] = v.astype("Int32")
lu = pd.to_datetime(a.last_updated, utc=True, format="ISO8601", errors="coerce")
note("R4", (a.last_updated.notna() & lu.isna()).sum(), "last_updated: failed conversions (expect 0)")
a["last_updated"] = lu
assert a.ended.isin(["t", "f"]).all(), "unexpected value in ended"
a["ended"] = a.ended.eq("t")

# R5/R6 dates: calendar-validate with our own rules, NOT pd.to_datetime (it cannot hold years < 1677)
DIM = np.array([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
for p in ("begin", "end"):
    yy, mm, dd = (a[f"{p}_{k}"].to_numpy(dtype="float64", na_value=np.nan) for k in ("year", "month", "day"))
    a[f"flag_orphan_{p}_part"] = (~np.isnan(mm) & np.isnan(yy)) | (~np.isnan(dd) & np.isnan(mm))
    zero = yy == 0                                    # there is no year 0
    bad_month = ~np.isnan(mm) & ((mm < 1) | (mm > 12))
    ym = np.where(np.isnan(yy) | zero, 4.0, yy)       # unknown year: allow Feb 29
    leap = np.where(ym < 1582, ym % 4 == 0, (ym % 4 == 0) & ((ym % 100 != 0) | (ym % 400 == 0)))  # Julian before 1582
    mi = np.where(np.isnan(mm) | bad_month, 1, mm).astype(int)
    bad_day = ~np.isnan(dd) & ~np.isnan(mm) & ~bad_month & ((dd < 1) | (dd > DIM[mi] + ((mi == 2) & leap)))
    a[f"{p}_year"] = a[f"{p}_year"].mask(zero)
    a[f"{p}_month"] = a[f"{p}_month"].mask(bad_month)
    a[f"{p}_day"] = a[f"{p}_day"].mask(bad_day)
    a[f"flag_invalid_{p}_date"] = zero | bad_month | bad_day
    note("R6", a[f"flag_invalid_{p}_date"].sum(),
         f"{p}: impossible date part set to missing (year 0: {zero.sum()}, bad month: {bad_month.sum()}, "
         f"bad day: {bad_day.sum()}); original in {p}_date_raw")
    y, m, d = (a[f"{p}_{k}"].notna() for k in ("year", "month", "day"))
    a[f"{p}_precision"] = np.select([y & m & d, y & m, y], ["day", "month", "year"], "none")
    a[f"{p}_precision"] = a[f"{p}_precision"].astype("category")
a["flag_future_begin"] = (a.begin_year > DUMP_YEAR).fillna(False).astype(bool)           # R7 kept, flagged
a["flag_begin_after_end"] = (a.begin_year > a.end_year).fillna(False).astype(bool)      # R8 kept, flagged
a["flag_ended_no_date"] = a.ended & a[["end_year", "end_month", "end_day"]].isna().all(axis=1)  # R9
for c in ("flag_future_begin", "flag_begin_after_end", "flag_ended_no_date"):
    note("R7-9", a[c].sum(), f"{c} (values kept, only flagged)")

# R10 labels from lookup tables (1:1 joins on id; originals kept; missing -> "Unknown", never imputed)
def lookup(name, cols):
    s = pd.read_csv(RAW / name, usecols=cols, names=["id", "name"], **READ).set_index("id")["name"]
    assert s.index.is_unique, f"{name} lookup ids not unique"
    return s
LK = {"type": lookup("artist_type", [0, 1]), "gender": lookup("gender", [0, 1]),
      "area": lookup("area", [0, 2])}
merge_rows = []
for col, lk, label in [("type", "type", "type_label"), ("gender", "gender", "gender_label"),
                       ("area", "area", "area_name"), ("begin_area", "area", "begin_area_name"),
                       ("end_area", "area", "end_area_name")]:
    orphans = int((a[col].notna() & ~a[col].isin(LK[lk].index)).sum())
    a[label] = a[col].map(LK[lk]).fillna("Unknown").astype("category")
    merge_rows.append((f"artist.{col} -> {lk}.id", "many-to-one", orphans, f"{(a[col] .isna()).sum():,}"))
    note("R10", orphans, f"{col}: orphan ids with no lookup match (expect 0)")
assert len(a) == n0, "label joins changed the row count"

# R12 shared names are kept (different artists); mark them
a["name_shared_count"] = a.name.map(a.name.value_counts()).astype("Int32")

# ---- validation ----
n1 = len(a)
dups_after = (int(a.id.duplicated().sum()), int(a.gid.duplicated().sum()))
if n1 != n0: FAILS.append(f"row count changed {n0} -> {n1}")

def record_checks():
    rows = []
    def add(i, what, raw, actual, expected, ok):
        rows.append((i, what, raw, actual, expected, "PASS" if ok else "FAIL"))
        if not ok: FAILS.append(f"record check {i} failed")
    g = lambda i: a[a.id == i].iloc[0]
    r = g("208838"); date = lambda p: f"{r[p+'_year']}-{r[p+'_month']}-{r[p+'_day']}"
    add(1, "Blaise Pascal (208838)", f"{raw_checks.loc['208838','begin_date_raw']} / {raw_checks.loc['208838','end_date_raw']}",
        f"{date('begin')} / {date('end')}, invalid flags {r.flag_invalid_begin_date}/{r.flag_invalid_end_date}",
        "1623-6-19 / 1662-8-19, no invalid flag", date("begin") == "1623-6-19" and date("end") == "1662-8-19"
        and not r.flag_invalid_begin_date and not r.flag_invalid_end_date)
    r = g("294902")
    add(2, "Horn\\Sick (294902)", raw_checks.loc["294902", "name"], r["name"], "Horn\\Sick (one backslash)",
        raw_checks.loc["294902", "name"] == "Horn\\\\Sick" and r["name"] == "Horn\\Sick")
    r = g("3249846")
    add(3, "Tristan Case (3249846)", raw_checks.loc["3249846", "begin_year"],
        f"{r.begin_year}, flag_future_begin={r.flag_future_begin}", "2027 kept, flag True",
        r.begin_year == 2027 and r.flag_future_begin)
    r = g("653157")
    add(4, "Orquesta Sinfonica Nacional de Colombia (653157)",
        f"begin {raw_checks.loc['653157','begin_date_raw']}, end {raw_checks.loc['653157','end_date_raw']}",
        f"begin {r.begin_year}-{r.begin_month}, end {r.end_year}, flag={r.flag_begin_after_end}, precision={r.begin_precision}",
        "both years kept, flag True, precision month",
        r.begin_year == 2003 and r.end_year == 2002 and r.flag_begin_after_end and r.begin_precision == "month")
    ind = a[a.name == "Indigo"]
    add(5, "Indigo (shared name)", f"{indigo_raw} rows", f"{len(ind)} rows, name_shared_count={sorted(set(int(x) for x in ind.name_shared_count))}",
        "250 rows kept, none merged, count 250", indigo_raw == len(ind) == 250 and set(ind.name_shared_count) == {250})
    return rows
checks = record_checks()

OUT_DATA.mkdir(parents=True, exist_ok=True); OUT_REP.mkdir(exist_ok=True)
# 50-row sample chosen by rule (see "why_selected")
chosen = {}
def add(idx, why):
    for i in idx:
        if i not in chosen and len(chosen) < 50: chosen[i] = why
add(a.index[a.id.isin(CHECK_IDS)], "record check")
add(a.index[a.name == "Indigo"][:1], "name shared by 250 artists")
for mask, k, why in [(a.flag_future_begin, 4, "begin year in the future"), (a.flag_begin_after_end, 2, "begin year after end year"),
                     (a.flag_invalid_begin_date | a.flag_invalid_end_date, 4, "impossible date part blanked"),
                     (a.flag_ended_no_date, 3, "ended but no end date"), (a.flag_orphan_begin_part, 3, "month/day without year"),
                     (name_decoded, 3, "backslash escape decoded"), (a.flag_name_not_nfc, 2, "name not NFC"),
                     (a.begin_year < 0, 2, "BCE begin year (valid)"), (a.begin_precision == "year", 3, "year-only begin date"),
                     (a.type.isna() & a.area.isna() & a.gender.isna(), 3, "type, area and gender all missing")]:
    add(a.index[pd.Series(mask, index=a.index).fillna(False).to_numpy(dtype=bool)][:k], why)
rest = 50 - len(chosen)
add(a.drop(index=list(chosen)).sample(n=rest, random_state=0).index, "random ordinary row (seed 0)")
sample = a.loc[list(chosen)].copy(); sample.insert(0, "why_selected", [chosen[i] for i in sample.index])
(OUT_REP / "sample_50_rows.json").write_text(json.dumps(json.loads(sample.to_json(orient="records", date_format="iso", force_ascii=False)),
                                                           ensure_ascii=False, indent=1), encoding="utf-8")
a.to_csv(OUT_DATA / "artist_clean.csv.gz", index=False)

# ---- report ----
cmp_cols = [c for c in COLS if c in a.columns]
miss_rows = [(c, f"{miss_before[c]:,}", f"{a[c].isna().sum():,}", f"{a[c].isna().sum() - miss_before[c]:+,}") for c in cmp_cols]
uniq = lambda c: ", ".join(f"{k}: {v:,}" for k, v in a[c].value_counts(dropna=False).items())
yr = lambda c: a[c].dropna().astype(int).describe(percentiles=[.01, .5, .99]).round(1)
rep = ["# Cleaning log - MusicBrainz artist table", "", f"Dump 20260930-002222 | script `scripts/clean_artists.py` | plan `plan.md`", "",
       "## Row counts (checklist 10)", f"- Before: **{n0:,}** | After: **{n1:,}** | Dropped: **{n0 - n1}** (rule R13: no rows dropped)",
       f"- Exact duplicate rows before: {dup_rows_before}; repeated id / gid after: {dups_after[0]} / {dups_after[1]}",
       "", "## Rules applied (rule, rows affected, what)", table(["rule", "rows", "what"], [(r, f"{n:,}", w) for r, n, w in LOG]),
       "", "## Missing values before / after (checklist 7)", table(["column", "before", "after", "change"], miss_rows),
       "", "Changes in date columns come only from blanking impossible date parts (R6). Missing type/area/gender are kept missing; labels say Unknown.",
       "", "## Label joins (checklist 9)", table(["join", "relationship", "orphan keys", "ids missing (not joined)"], merge_rows),
       f"Row count before/after joins: {n0:,} / {n1:,} (no extra rows).",
       "", "## Unique values (checklist 5, 7)", f"- type_label: {uniq('type_label')}", f"- gender_label: {uniq('gender_label')}",
       f"- ended: {uniq('ended')}", f"- begin_precision: {uniq('begin_precision')}", f"- end_precision: {uniq('end_precision')}",
       "", "## Numeric ranges", "begin_year:", "```", yr("begin_year").to_string(), "```", "end_year:", "```", yr("end_year").to_string(), "```",
       "", "## Record counts behind each metric (checklist 11)",
       table(["metric / group key", "records used", "records missing (kept, shown as Unknown / excluded from year stats)"],
             [("begin_year (any age/newness metric)", f"{a.begin_year.notna().sum():,}", f"{a.begin_year.isna().sum():,}"),
              ("type_label", f"{(a.type_label != 'Unknown').sum():,}", f"{(a.type_label == 'Unknown').sum():,}"),
              ("area_name", f"{(a.area_name != 'Unknown').sum():,}", f"{(a.area_name == 'Unknown').sum():,}"),
              ("gender_label", f"{(a.gender_label != 'Unknown').sum():,}", f"{(a.gender_label == 'Unknown').sum():,}")]),
       "Missing group keys stay in the data as their own Unknown group; they are never dropped or guessed.",
       "", "## Flags", table(["flag", "rows"], [(c, f"{int(a[c].sum()):,}") for c in a.columns if c.startswith("flag_")]),
       "", "## Reconciliation with the raw profile (pinned dump 20260930-002222)",
       "- Raw begin_year > end_year: 2 rows. After R6 blanks the impossible end year 0, **1** remains (the other row's end year was 0).",
       "- Raw 'ended = t but no end date': 29,575 rows. After the same year-0 fix: 29,576 (+1, the row whose end year 0 was blanked).",
       "- A pandas `to_datetime` check flags ~1,000 begin and ~1,000 end dates as impossible, but they are valid dates before 1677 that pandas cannot hold (e.g. Blaise Pascal 1623-06-19). The calendar check finds none; the only impossible parts are year 0.",
       "", "## Five record checks (expected written in plan.md before running) (checklist 12)",
       table(["#", "record", "original", "actual", "expected", "result"], checks),
       "", "## Sample", "`output/sample_50_rows.json`: 50 rows chosen by rule; field `why_selected` gives the reason for each."]
(OUT_REP / "cleaning_log.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
print("\n".join(rep[:6])); print(table(["#", "record", "original", "actual", "expected", "result"], checks))
if FAILS:
    print("FAILED:", FAILS, file=sys.stderr); sys.exit(1)
print(f"OK: {n1:,} rows -> data/clean/artist_clean.csv.gz, output/cleaning_log.md, output/sample_50_rows.json")
