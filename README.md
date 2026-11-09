# EchoAI: Emerging Artist Discovery (USC MSBA DSO 576)

**Live demo: https://echo-ai-deploy.vercel.app/**

EchoAI helps an editorial playlist curator (at a streaming service or an independent playlist) find small artists whose audience is growing fast, before they reach the mainstream. It is built on MusicBrainz artist metadata and ListenBrainz listening data from March to August 2026.

> **Read this first: the live demo runs on a 58-artist test fixture (56 KB), not the full data.** The full cleaned dataset covers 610,423 artists and yields 1,131 emerging artists at the default settings. The demo yields 6. The demo shows how the product works; its 6 artists are not research findings. See [Data scope](#data-scope) and [Limitations](#limitations).

## User scenario

**Who:** a playlist curator who builds a weekly "rising artists" playlist and has no demographic or streaming-platform data, only public listening behaviour.

**Decision:** which small, fast-growing artists are worth a closer listen and a place on a shortlist this week?

**Walkthrough (about 2 minutes):**

1. **Discovery Hub.** Read the catalog size and observation window, then click *Enter Discovery Studio*.
2. **Studio.** The default view lists the artists that pass every gate: first release 2023 or later, at least 5 baseline listeners, audience below the 90th percentile, growth above the 90th percentile.
3. **Tune the definition.** Four sliders (release year, growth percentile, size percentile, minimum baseline listeners) re-run the shortlist instantly. The heading and the sentence under it show the exact cutoffs in use.
4. **Filter.** Search by name, and filter by category, genre, market and audience size. Sort by growth, listeners, smallest audience or name. Reset clears everything.
5. **Inspect.** Click an artist (card, table row or chart point) to see the editorial summary, the 6-month trajectory, the "fans also listen to" taste community and a lead track.
6. **Shortlist and export.** Add artists to the shortlist tray and export it as CSV.

## What counts as "emerging"

An artist is emerging when all four gates pass. All four thresholds are sliders in the dashboard.

| Gate | Default | Why |
|---|---|---|
| First release date | 2023-01-01 or later | Without it, long-established acts dominate the growth ranking |
| Baseline audience | at least 5 average monthly listeners, Mar to May | Below 5 listeners, a growth percentage is mostly noise |
| Size ceiling | recent monthly listeners at or below the 90th percentile | Keeps stars out |
| Growth | growth at or above the 90th percentile | "Small but growing" |

`baseline` is the average monthly distinct listeners for March to May. `recent` is the same average for June to August. `growth = (recent - baseline) / baseline`. Percentiles are computed over artists with a baseline of at least 5.

| | Full data | Demo (58 artists) |
|---|---|---|
| Artists scored | 610,423 | 58 |
| Emerging at defaults | 1,131 | 6 |
| 90th percentile recent listeners | 87.3 per month | 298.0 per month |
| 90th percentile growth | +28.1% | +407% |

## Reading the numbers

- **"Mar '26" and "Aug '26" on each card are period averages**, not single months: the baseline average (Mar to May) and the recent average (Jun to Aug). The monthly trajectory chart shows the real month-by-month values.
- **6M Growth** is the growth formula above. A large percentage from a tiny base (for example +1456% from 5.3 listeners) means a few listeners, not a large audience. Read it together with the listener counts.
- **Fans also listen to** is the taste community: for the selected artist, the established artists ranked by the share of that artist's listeners who also listen to them. It is behavioural overlap and uses no demographic data.
- **Categories:** *Emerging Acts* pass all four gates. *Mainstream Benchmarks* are artists whose recent audience is above the size ceiling. *Developing Candidates* are everything else: in the catalog but failing at least one gate.
- **Taste-community benchmarks** are artists with more than about 87 average monthly listeners in the full data. That cutoff is fixed at the full-data value, so it does not move with the sliders.
- **Audience scale:** Micro (under 50 listeners per month), Rising (50 to 300), Mainstream (over 300).
- **Percentile cutoffs move with the baseline slider.** Raising the minimum baseline shrinks the population the percentiles are computed on, so the cutoff for "90th percentile growth" changes too. The sentence under the heading always shows the cutoff in use.

## Controls and difficult cases

| Situation | What happens |
|---|---|
| Sliders set so nothing qualifies, or a search matches nothing | A message says no artists matched and suggests loosening the sliders, clearing the search or clicking Reset |
| Artist with missing genre, country or release date | Shown as `Unknown`, never guessed or filled in |
| Artist with fewer than 5 baseline listeners | Not given a growth figure, so it cannot enter the growth ranking |
| Many results | Results are paged; switch between cards and a data table |
| Shortlist is empty | The export button stays disabled until an artist is added |
| Filters get confusing | *Reset* clears the search and the filters |

## Data scope

| Item | Value |
|---|---|
| Listening data | ListenBrainz Spark full dump 2722 (2026-10-15), all users, listens from 2026-03-01 up to 2026-09-01 |
| Artist metadata | MusicBrainz full export 20260930-002222 (CC0) |
| Listens in the window | 249,645,377, then 244,794,323 after removing exact duplicates, then 232,640,849 credited to an artist |
| Artists in the cleaned data | 610,423 |
| Artist identity | MusicBrainz artist ID. Merged IDs are redirected. Names are display only |
| Bots | Users with more than 500 listens on any UTC day are excluded (1,692 of 58,378 users, 39.2% of listens). A 1,000-listens threshold is reported as a sensitivity check (28.4%) |
| Excluded | Listens with no artist ID (37.3M, 15%), and special-purpose artists such as Various Artists and [unknown] |
| Not imputed | Genre, country and release date are left missing when missing |

Every cleaning and metric decision is recorded in [DATA_DECISIONS.md](DATA_DECISIONS.md) (D1 to D10), with the glossary in [GLOSSARY.md](GLOSSARY.md) and the scoring rationale in [docs/adr](docs/adr).

The tables in `data/clean/` are the 58-artist fixture (a few KB each), so the repository clones instantly. The full cleaned tables (about 1.5 GB) are not in this repository. To rebuild them, follow `extraction/README.md` (about 3 hours). Row counts and SHA-256 prefixes to check a rebuild against are in DATA_DECISIONS.md, section 5.

## Limitations

- **The live demo is a 58-artist test fixture.** Its 6 emerging artists show the product working, not real findings. Findings come from the full data (1,131 emerging artists).
- **Audience bias.** ListenBrainz users are self-selected music enthusiasts, not a streaming platform's audience. "Growth" means traction inside this community.
- **No demographics.** No listener age, gender, location or playlist data exists in any source, so the dashboard cannot say who the listeners are. Taste communities are co-listening overlap only.
- **Sparse metadata.** In the full data, 20% of artists have a genre, 63% a country and 75% a first release date. Only 18% of the default shortlist has a genre, so "All genres" is the default and the genre filter is a weak signal.
- **New-artist blind spot.** An artist needs at least 5 baseline listeners to get a growth figure. In the full data, 355 artists that debuted in March 2026 or later and have at least 5 recent listeners are left out of the growth ranking because they have no baseline.
- **Percentage growth from tiny numbers is unstable.** The 5-listener floor reduces this but does not remove it.
- **Rule-based bot filter.** The 500-listens-per-day cutoff is a judgement call; a different cutoff changes the shortlist (see the sensitivity check above).
- **Tracks.** Lead tracks come from a table that removes bots but not exact duplicates (about 2% of listens), and credits only the first listed artist on each recording.
- **Six-month window.** March to August 2026 is enough for a trend, not for seasonality.

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py          # or: npm start
```

The app opens at http://localhost:8000. `run.py` loads the data through `backend/analysis.py`.

Checks:

```bash
python scripts/clean_data.py               # replication audit of the cleaning rules
python audit/kunjesh_audit_checks.py       # feature and threshold checks
python -m unittest discover tests          # unit and integration tests
python backend/analysis.py                 # self-check on the loaded data
```

## Deployment

Deployed on Vercel at https://echo-ai-deploy.vercel.app/ using `vercel.json` and `api/index.py` (FastAPI backend, static front end in `web/`).

## Repository map

| Path | Contents |
|---|---|
| `web/` | Front end (plain HTML, CSS and JavaScript) |
| `api/`, `backend/` | FastAPI app and DuckDB analysis (`backend/analysis.py`) |
| `data/clean/` | The 58-artist fixture tables the app and the live demo read |
| `extraction/`, `scripts/` | Scripts that build and clean the data |
| `audit/`, `tests/` | Audit checks and tests |
| `DATA_DECISIONS.md`, `GLOSSARY.md`, `BUILD_SPEC.md`, `docs/adr/` | Decisions, terms, build specification, scoring rationale |
| `docs/` | Course history: the Module 3 starter instructions and the Module 6 cleaning submission |
