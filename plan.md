# Cleaning plan - MusicBrainz artist table (DSO 576 Module 6)

Status: APPROVED with the default decisions D1-D5 (Navya, 2026-10-03). Implemented in `scripts/clean_artists.py`; results in `output/cleaning_log.md`. Originals in `data/raw/` are never modified.

Outcome notes (added after running): (a) the calendar check found NO impossible dates other than year 0 (8 begin, 1 end); the ~1,000 'impossible' dates a pandas check reports are valid pre-1677 dates. (b) `begin_year > end_year` is 1 after blanking end year 0 (raw: 2). (c) full cleaned file is `data/clean/artist_clean.csv.gz` (CSV, not parquet, to avoid an extra dependency).

## 1. Goal (Envision)
Project vision (Vision B, `project-start.md`): an editorial curation lead at Spotify must decide which **emerging artists** to add to next month's discovery playlists, and which listener segment to surface each one to.
This dataset is the artist side of that decision. Clean it so an analysis/dashboard can later answer: *which artists look new (recent `begin` date, still active), what kind of entity are they (person/group/...), and where are they from.*
Main comparison: artists by start year x type x area. (The exact "emerging" threshold is still an open team question #2 - NOT decided here; see Decision D1.)

## 2. Source (checklist 3)
- MusicBrainz core dump `20260930-002222` (CC0), `mbdump.tar.bz2`, downloaded 2026-10-03 by `scripts/extract_musicbrainz.sh`.
- Kept tables, unchanged, in `data/raw/mb/mbdump/`: `artist`, `artist_type`, `gender`, `area` (tab-separated, no header, `\N` = NULL). Official `MD5SUMS` + `MANIFEST.txt` + extracted-file sha256 saved beside them.
- Load rule: read as all-strings, `sep="\t"`, `na_values=["\\N"]`, `keep_default_na=False` (so a name like "NA" or "null" is NOT turned into missing), no quoting.
- `data/` is gitignored; the raw dump is not committed. Re-run the script to recreate it.

## 3. One row (checklist 2)
One row = one MusicBrainz **artist entity** (a person, group, orchestra, choir, character, or other). Unique key: `gid` (UUID); `id` is also unique. Name is NOT a key.

## 4. What the raw data looks like (profiled on the full table, 2026-10-03)
| Finding | Count |
|---|---|
| Rows / columns | 2,999,670 / 19 (every line has exactly 19 fields) |
| Exact duplicate rows; repeated `id`; repeated `gid` | 0 ; 0 ; 0 |
| Names shared by >1 artist | 129,816 names (432,170 rows), e.g. "Indigo" x250 |
| Same name + same sort_name + empty comment | 0 (MusicBrainz forces a disambiguation `comment`, so shared names are different artists) |
| Missing: type / area / gender | 680,060 / 1,509,870 / 1,725,708 |
| Missing: begin_year / begin_month / begin_day | 2,395,848 / 2,659,330 / 2,681,254 |
| Missing: end_year; `ended = t` | 2,843,536 ; 185,745 (29,575 of them have no end date) |
| Begin year-only (no month) | 272,790 of 613,155 artists that have any begin date |
| `begin_year` > 2026 | 25 (e.g. 4428, 2072, 2027) |
| `begin_year` > `end_year` | 2 |
| `end_year` = 0 | present (e.g. artist 3045772) |
| Names containing a backslash | 119 (dump escapes `\` as `\\`, e.g. `Horn\\Sick`) |
| Names not in Unicode NFC form | 6 |
| Leading/trailing/double spaces, control chars, empty names | 0 |
| Orphan `type`/`area`/`begin_area` ids (no lookup match) | 0 |
| `last_updated` missing | 136,417 (range 2008-11-24 to 2026-09-30) |
| Gender filled on non-Person types | 20,880 (Character 14,813; Other 2,840; type missing 3,227) |
| Negative begin years (BCE) | present (min -535) - historical, valid |

## 5. Rules (checklist 4-8) - applied in this order
General rules from the professor: never drop a row without a documented reason; never change categories/units without logging it; flag suspicious values before deciding; report what changed after each major step.

| # | Column(s) | Rule | Why |
|---|---|---|---|
| R1 | all | Load as strings; `\N` -> missing; keep `""` (empty comment) as empty text, not missing. | Avoid pandas guessing types; keep real "NA" names. |
| R2 | `id`, `gid` | Keep as text. Check uniqueness (expect 0 dups). | IDs are labels, not numbers. |
| R3 | `name`, `sort_name`, `comment` | Decode the dump's text escapes (`\\`->`\`, `\t`, `\n`, `\r`). Keep case, accents and spelling. No NFC rewrite (6 rows) - flag only. | Backslash names are an export artifact; case/accents carry meaning (stylised names like "UNlT"). |
| R4 | date parts | Convert to nullable integers. Failed conversions: expect 0, count them. | Checklist 4. |
| R5 | begin/end dates | Add `begin_precision` / `end_precision` (none/year/month/day). Do NOT invent missing months/days. | 45% of known begin dates are year-only. |
| R6 | begin/end dates | Validate calendar dates with Python `calendar`/`datetime.date`, **not** `pd.to_datetime`. Pandas cannot hold dates before 1677, so it flags valid historical dates (e.g. Blaise Pascal 1623-06-19) as invalid. Only truly impossible dates (e.g. Feb 30, year 0) get a flag column and the bad part set to missing (original kept in `*_raw`). | "Unusual does not always mean wrong." |
| R7 | `begin_year` | Keep BCE/old years. Add `flag_future_begin` for year > 2026; **keep the value** unless Decision D2 says otherwise. | Some are documented fictional acts. |
| R8 | begin vs end | Add `flag_begin_after_end` (expect 2). Keep both values; do not "fix". | Cannot tell which is wrong. |
| R9 | `ended`, end dates | `ended` -> boolean. Keep the 29,575 "ended, no end date" as is; flag `flag_ended_no_date`. | Real world: known to have ended, date unknown. |
| R10 | `type`, `gender`, `area`, `begin_area`, `end_area` | Add label columns (`type_label`, `gender_label`, `area_name`, ...) via lookups. Missing stays "Unknown" in labels; original id columns kept. No imputing. | Missing != Other. Any fill would be a guess. |
| R11 | gender on non-Person | Keep (Character rows legitimately have gender). Report count only. | Domain rule, see D3. |
| R12 | duplicates | De-dupe key = `gid`. Expect 0 removed. Shared names are kept and marked `name_shared_count`. | Same name is not the same artist. |
| R13 | rows | **No rows dropped** in the cleaning step. Any later "emerging" filter is analysis, not cleaning, and is applied on a copy. | Makes before/after counts reconcile exactly. |
| R14 | `edits_pending`, `last_updated` | Parse timestamp (UTC); keep missing. Not used for the question. | Metadata only. |

## 6. Decisions for Navya (human in the loop) - please confirm or change
- **D1** What counts as "emerging"? (e.g. `begin_year` >= 2021 and not ended.) Cleaning does not need it, but the dashboard will. Default: leave undecided, add `begin_year` + precision so any threshold works.
- **D2** Future begin years (25 rows, some documented fictional). Default: keep + flag. Alternative: set to missing.
- **D3** Keep gender on Character/Other entities? Default: keep.
- **D4** Restrict the final analysis table to Person + Group? Default: keep all types in the cleaned file; restrict later.
- **D5** Sample for GitHub: `.csv/.tsv/.parquet` are gitignored, so the <=50-row sample goes in as `.json` (`output/sample_50_rows.json`). Default: yes.

## 7. Outputs and validation plan (checklist 7, 10-13)
Files (all produced by one script, `scripts/clean_artists.py`, run from repo root):
- `data/clean/artist_clean.csv.gz` (gitignored, full table), `output/sample_50_rows.json` (<=50 hard cases, chosen by rule), `output/cleaning_log.md` (rule, rows affected, before/after).
Checks run automatically and printed:
1. Row count before = after (2,999,670) and per-rule rows changed.
2. Missing counts before/after for every affected column.
3. Unique values in `type_label`, `gender_label`, `ended`.
4. min / max / distribution of `begin_year`, `end_year`.
5. Duplicate counts (rows, id, gid) = 0.
6. Five record checks below, original vs actual.
Reproducibility: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && bash scripts/extract_musicbrainz.sh && python scripts/clean_artists.py`.

### Five record checks - EXPECTED results written BEFORE running the code
| # | Artist (id) | Raw situation | Expected after cleaning, and why |
|---|---|---|---|
| 1 | Blaise Pascal (208838) | begin 1623-06-19, end 1662-08-19 | Dates **kept unchanged**, no invalid flag. Both are real calendar dates; only pandas' 1677 limit would call them invalid. |
| 2 | Horn\\Sick (294902) | name stored `Horn\\Sick` | name becomes `Horn\Sick` (one backslash). Export escape decoded. |
| 3 | Tristan Case (3249846) | begin_year 2027, no end, no comment | Value kept, `flag_future_begin` = True. Unknown whether error or fiction; not guessing. |
| 4 | Orquesta Sinfonica Nacional de Colombia (653157) | begin 2003-12, end_year 2002, ended=t | Both years kept, `flag_begin_after_end` = True, `begin_precision`=month. |
| 5 | Indigo (name appears 250 times) | 250 distinct artists, same name | All 250 rows kept, none merged; `name_shared_count` = 250. |

## 8. Mapping to the 14 checklist items
1 Vision/question: section 1 | 2 One row: section 3 | 3 Source: section 2 | 4 Types: R4 | 5 Text: R3 | 6 Duplicates: R12 | 7 Missing: R10, table in log | 8 Suspicious values: R6-R9 | 9 Merges: **Not applicable for the cleaning step** - lookups are label joins done 1:1 on id (row count must stay 2,999,670; orphan keys = 0); will still report it | 10 Reconcile: section 7 check 1 | 11 Calculations: record counts per metric in the log | 12 Records: section 7 table | 13 Reproducibility: command above | 14 Limitations: below.

## 9. Known limitations (checklist 14)
- MusicBrainz is volunteer-edited: missing begin dates (80%) mean "not entered", not "unknown to the world".
- This is a catalog of artists, not of listening. It shows who exists and when they started, not who is gaining listeners; that needs the ListenBrainz side (API was down on 2026-10-03).
- "Emerging" and the listener-segment match (project questions 2 and 3) are not answered by cleaning.
