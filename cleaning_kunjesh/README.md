# Module 6 cleaning submission

This folder contains the reproducible ListenBrainz cleaning workflow for the emerging-artist discovery project.

## Source

The raw sample is a 50-listen public response for ListenBrainz user `hwnrwx`:

`https://api.listenbrainz.org/1/user/hwnrwx/listens?count=50`

The source JSON is preserved as `listenbrainz_sample.json`. ListenBrainz documents the response as a payload containing a list of listen events, each with `listened_at` and nested `track_metadata`. The sample is descriptive only and is not representative of Spotify users.

## Run

```bash
python3 cleaning_kunjesh/cleaning.py --input cleaning_kunjesh/listenbrainz_sample.json
python3 cleaning_kunjesh/build_submission.py
```

The cleaner writes `cleaning_kunjesh/output/cleaned_listens.csv`, `metrics.csv`, `missingness.csv`, `cleaning_decision_log.csv`, `record_checks.csv`, and `validation_summary.json`. The PDF is `cleaning_kunjesh/Module_6_Submission.pdf`.

## Branch metadata

- Branch: `kunjesh`
- Branch URL: https://github.com/kunjeshgupta/dso576_project/tree/kunjesh
- Commit ID: `fff1c088381a946bd1d2fae77593fc72bf441037` (implementation commit)

## Cleaning policy

Each row is one listen event. Text is trimmed while raw values are preserved. Timestamps are coerced to UTC. Only exact duplicate payloads are removed; repeated IDs are retained because repeated listens are valid events. Events without a usable timestamp or listener ID are excluded from time-based metrics and counted explicitly. No merge is performed.
