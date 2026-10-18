# Canonical data build

Rebuilds the team's canonical tables (definitions in `../DATA_DECISIONS.md`). The scripts are Hosung's Module 6 pipeline (`origin/hosung:module6_hosung/scripts`), with the window extended to March–August 2026. `recording_month.py` is new.

Needs Python 3.13, about 15 GB of free disk, and roughly 3 hours. Data goes to `~/dso576_data/` (outside the repo).

```bash
cd extraction
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/load_listenbrainz.py --out-dir ~/dso576_data --months 6 --end 2026-09-01   # ListenBrainz Spark dump 2722
python scripts/build_dataset.py --data-dir ~/dso576_data                                  # joins MusicBrainz export (latest)
python scripts/clean_dataset.py --data-dir ~/dso576_data --start 2026-03-01               # rules R1–R12, bots > 500/day
python scripts/recording_month.py --data-dir ~/dso576_data                                # song × month
```

The download resumes if interrupted; rerun the same command. MetaBrainz keeps only the two latest dumps. If dump 2722 is gone, pass `--url` with the current `listenbrainz-spark-dump-*.tar` from https://data.metabrainz.org/pub/musicbrainz/listenbrainz/fullexport/.

Outputs in `~/dso576_data/clean/`: `artists_clean`, `artist_month_clean`, `user_artist_clean`, `recording_month`, `users_flagged` (Parquet), plus logs (`cleaning_log.csv`, `bot_sensitivity.csv`, `listen_month_log.csv`).
