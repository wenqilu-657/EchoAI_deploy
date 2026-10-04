# Cleaning log - MusicBrainz artist table

Dump 20260930-002222 | script `scripts/clean_artists.py` | plan `plan.md`

## Row counts (checklist 10)
- Before: **2,999,670** | After: **2,999,670** | Dropped: **0** (rule R13: no rows dropped)
- Exact duplicate rows before: 0; repeated id / gid after: 0 / 0

## Rules applied (rule, rows affected, what)
| rule | rows | what |
|---|---|---|
| R1 | 2,999,670 | loaded as text; \N -> missing |
| R2 | 0 | repeated id or gid (expect 0) |
| R3 | 119 | name: dump escapes decoded |
| R3 | 103 | sort_name: dump escapes decoded |
| R3 | 90 | comment: dump escapes decoded |
| R3 | 6 | name not in NFC form (flagged, not changed) |
| R4 | 0 | begin_year: failed numeric conversions (expect 0) |
| R4 | 0 | begin_month: failed numeric conversions (expect 0) |
| R4 | 0 | begin_day: failed numeric conversions (expect 0) |
| R4 | 0 | end_year: failed numeric conversions (expect 0) |
| R4 | 0 | end_month: failed numeric conversions (expect 0) |
| R4 | 0 | end_day: failed numeric conversions (expect 0) |
| R4 | 0 | edits_pending: failed numeric conversions (expect 0) |
| R4 | 0 | last_updated: failed conversions (expect 0) |
| R6 | 8 | begin: impossible date part set to missing (year 0: 8, bad month: 0, bad day: 0); original in begin_date_raw |
| R6 | 1 | end: impossible date part set to missing (year 0: 1, bad month: 0, bad day: 0); original in end_date_raw |
| R7-9 | 25 | flag_future_begin (values kept, only flagged) |
| R7-9 | 1 | flag_begin_after_end (values kept, only flagged) |
| R7-9 | 29,576 | flag_ended_no_date (values kept, only flagged) |
| R10 | 0 | type: orphan ids with no lookup match (expect 0) |
| R10 | 0 | gender: orphan ids with no lookup match (expect 0) |
| R10 | 0 | area: orphan ids with no lookup match (expect 0) |
| R10 | 0 | begin_area: orphan ids with no lookup match (expect 0) |
| R10 | 0 | end_area: orphan ids with no lookup match (expect 0) |

## Missing values before / after (checklist 7)
| column | before | after | change |
|---|---|---|---|
| id | 0 | 0 | +0 |
| gid | 0 | 0 | +0 |
| name | 0 | 0 | +0 |
| sort_name | 0 | 0 | +0 |
| begin_year | 2,395,848 | 2,395,856 | +8 |
| begin_month | 2,659,330 | 2,659,330 | +0 |
| begin_day | 2,681,254 | 2,681,254 | +0 |
| end_year | 2,843,536 | 2,843,537 | +1 |
| end_month | 2,895,954 | 2,895,954 | +0 |
| end_day | 2,901,402 | 2,901,402 | +0 |
| type | 680,060 | 680,060 | +0 |
| area | 1,509,870 | 1,509,870 | +0 |
| gender | 1,725,708 | 1,725,708 | +0 |
| comment | 0 | 0 | +0 |
| edits_pending | 0 | 0 | +0 |
| last_updated | 136,417 | 136,417 | +0 |
| ended | 0 | 0 | +0 |
| begin_area | 2,501,971 | 2,501,971 | +0 |
| end_area | 2,922,993 | 2,922,993 | +0 |

Changes in date columns come only from blanking impossible date parts (R6). Missing type/area/gender are kept missing; labels say Unknown.

## Label joins (checklist 9)
| join | relationship | orphan keys | ids missing (not joined) |
|---|---|---|---|
| artist.type -> type.id | many-to-one | 0 | 680,060 |
| artist.gender -> gender.id | many-to-one | 0 | 1,725,708 |
| artist.area -> area.id | many-to-one | 0 | 1,509,870 |
| artist.begin_area -> area.id | many-to-one | 0 | 2,501,971 |
| artist.end_area -> area.id | many-to-one | 0 | 2,922,993 |
Row count before/after joins: 2,999,670 / 2,999,670 (no extra rows).

## Unique values (checklist 5, 7)
- type_label: Person: 1,609,190, Unknown: 680,060, Group: 662,859, Character: 18,002, Orchestra: 11,951, Choir: 10,954, Other: 6,654
- gender_label: Unknown: 1,725,708, Male: 973,010, Female: 293,735, Not applicable: 2,639, Non-binary: 2,631, Other: 1,947
- ended: False: 2,813,925, True: 185,745
- begin_precision: none: 2,395,856, day: 309,092, year: 272,783, month: 21,939
- end_precision: none: 2,843,537, day: 98,240, year: 52,445, month: 5,448

## Numeric ranges
begin_year:
```
count    603814.0
mean       1974.3
std          55.6
min        -535.0
1%         1780.0
50%        1986.0
99%        2024.0
max        4428.0
```
end_year:
```
count    156133.0
mean       1979.8
std          80.6
min        -406.0
1%         1619.0
50%        2001.0
99%        2026.0
max        3999.0
```

## Record counts behind each metric (checklist 11)
| metric / group key | records used | records missing (kept, shown as Unknown / excluded from year stats) |
|---|---|---|
| begin_year (any age/newness metric) | 603,814 | 2,395,856 |
| type_label | 2,319,610 | 680,060 |
| area_name | 1,489,800 | 1,509,870 |
| gender_label | 1,273,962 | 1,725,708 |
Missing group keys stay in the data as their own Unknown group; they are never dropped or guessed.

## Flags
| flag | rows |
|---|---|
| flag_name_not_nfc | 6 |
| flag_orphan_begin_part | 9,368 |
| flag_invalid_begin_date | 8 |
| flag_orphan_end_part | 37 |
| flag_invalid_end_date | 1 |
| flag_future_begin | 25 |
| flag_begin_after_end | 1 |
| flag_ended_no_date | 29,576 |

## Reconciliation with the raw profile (pinned dump 20260930-002222)
- Raw begin_year > end_year: 2 rows. After R6 blanks the impossible end year 0, **1** remains (the other row's end year was 0).
- Raw 'ended = t but no end date': 29,575 rows. After the same year-0 fix: 29,576 (+1, the row whose end year 0 was blanked).
- A pandas `to_datetime` check flags ~1,000 begin and ~1,000 end dates as impossible, but they are valid dates before 1677 that pandas cannot hold (e.g. Blaise Pascal 1623-06-19). The calendar check finds none; the only impossible parts are year 0.

## Five record checks (expected written in plan.md before running) (checklist 12)
| # | record | original | actual | expected | result |
|---|---|---|---|---|---|
| 1 | Blaise Pascal (208838) | 1623-6-19 / 1662-8-19 | 1623-6-19 / 1662-8-19, invalid flags False/False | 1623-6-19 / 1662-8-19, no invalid flag | PASS |
| 2 | Horn\Sick (294902) | Horn\\Sick | Horn\Sick | Horn\Sick (one backslash) | PASS |
| 3 | Tristan Case (3249846) | 2027 | 2027, flag_future_begin=True | 2027 kept, flag True | PASS |
| 4 | Orquesta Sinfonica Nacional de Colombia (653157) | begin 2003-12-, end 2002-- | begin 2003-12, end 2002, flag=True, precision=month | both years kept, flag True, precision month | PASS |
| 5 | Indigo (shared name) | 250 rows | 250 rows, name_shared_count=[250] | 250 rows kept, none merged, count 250 | PASS |

## Sample
`output/sample_50_rows.json`: 50 rows chosen by rule; field `why_selected` gives the reason for each.
