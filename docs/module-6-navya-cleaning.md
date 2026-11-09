## Module 6 - Project data cleaning (Navya Gupta)

- **Branch:** `navya` | **Branch URL:** https://github.com/kunjeshgupta/dso576_project/tree/navya | **Commit ID:** 0b6827ab82aab47d301e103b44dc46d93bc6f525
- **Data source and version:** MusicBrainz core database dump `20260930-002222` (CC0), `mbdump.tar.bz2` from https://data.metabrainz.org/pub/musicbrainz/data/fullexport/20260930-002222/ . Downloaded 2026-10-03. Tables used: `artist` (2,999,670 rows), `artist_type`, `gender`, `area`. The raw dump is not committed (see `.gitignore`) and is never modified.
- **Plan and decisions:** `plan.md` (rules, reasons, expected record-check results written before the code ran). **Results:** `output/cleaning_log.md`.
- **Run instructions** (from the repo root; needs about 4 GB of free RAM and ~8 GB of disk during extraction):
  ```
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  bash scripts/extract_musicbrainz.sh      # streams the dump, keeps 4 tables in data/raw/mb/ (10-30 min)
  python scripts/clean_artists.py          # ~3 min; exits non-zero if any check fails
  ```
- **Expected output files:** `data/clean/artist_clean.csv.gz` (full cleaned table, not committed), `output/sample_50_rows.json` (50 rows chosen by rule), `output/cleaning_log.md` (counts, before/after missing values, record checks). Expected: 2,999,670 rows before and after; all five record checks PASS.
- **Dependencies:** `requirements.txt` (pandas, numpy). Python 3.9+.
- `scripts/fetch_listens.py` is an unused first attempt at the ListenBrainz API sample (the API was unavailable on 2026-10-03); it needs `requests` and is not part of the cleaning run.
