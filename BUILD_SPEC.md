# BUILD_SPEC — Emerging Artist Discovery (Team EchoAI) · v1.1

## 1. Vision

**User:** an editorial curator at a streaming service or indie playlist brand.
**Decision:** which small but fast-growing artists to add to next month's discovery playlists, and which **taste community** each one fits. A taste community is the established artists the same listeners already play.
**Why it improves current practice:** charts surface artists who are already big, and reviewing submissions one by one does not show who is gaining listeners. This tool ranks artists who are still small but growing fast in real listening data (ListenBrainz, Mar–Aug 2026: 58,378 listeners, 138M artist-credited listens after removing bots). It also shows each artist's audience overlap with established artists, which works even for artists with no genre tags (82% of the default shortlist).
**Changed since Phase 1:** the listener age/gender, listener-geography and playlist-engagement panels are removed, because no source contains those fields. "Listener segment" becomes "taste community" (co-listening). "Spotify" becomes a general streaming or indie curator, because ListenBrainz users are not Spotify's population. The Phase 1 output (a shortlist for human review) is kept.

### Use cases (select → see → decide)
| # | User selects / inputs | Dashboard shows | User decides |
|---|---|---|---|
| U1 | Release year, audience-size and growth percentiles, optional genre/country | Ranked shortlist + size-vs-growth scatter | Which artists deserve a closer look |
| U2 | Clicks an artist | 6-month listener trend, baseline vs recent | Sustained growth or a one-month spike |
| U3 | Same artist | "Fans also play": established artists by share of shared listeners | Which playlist/taste community to place them in |
| U4 | Same artist | Top tracks by recent listeners, linked to MusicBrainz | Which track to slot |
| U5 | **Add to shortlist**, then **Export CSV** | Shortlist tray with a suggested "sounds like" artist each | Final list handed to scheduling |

## 2. How to use this spec (building agent)
**Task:** build `api/` and `web/` as specified in sections 3–5, in the order in section 6, until every check in section 7 passes.
**Already done, do not edit:** `extraction/` (builds the data), `DATA_DECISIONS.md` (definitions D1–D10), `backend/analysis.py` (all metrics; `python backend/analysis.py` is its test).
**Rules:**
1. Every metric shown comes from a `backend/analysis.py` function. The API and browser never compute or redefine a metric; counting returned rows, sorting, paging and formatting are allowed.
2. If a needed function seems missing or wrong, stop and report it. Do not edit `backend/`, `extraction/` or the data.
3. Build only what this spec lists. Section 8 is out of scope.
4. If something is truly unspecified, choose the simplest option consistent with this spec and log it in `BUILD_NOTES.md` (section · what was unclear · what you chose). Done means every check passes and this log is empty or reviewed.

**Prerequisites:** Python ≥ 3.11 venv with `pip install -r requirements.txt` (add `fastapi` and `uvicorn` to it). The five canonical Parquet tables listed in `DATA_DECISIONS.md` §5 must be in `~/dso576_data/clean/` (or `$DSO576_DATA`); rebuild or verify them as in §6 there. Check 1 below confirms the data is in place.

## 3. Dashboard (single page)

**Starting view:** default filters applied; the KPI strip, scatter and table load immediately; the detail panel says "Select an artist to see details."
**Layout:** header + KPI strip on top; filters in a left column; scatter above the table in the center; detail panel on the right; shortlist tray across the bottom. Below 900 px wide, stack in that order.

### Metric definitions (as implemented in `backend/analysis.py`; data rules in `DATA_DECISIONS.md`)
| Metric | Definition |
|---|---|
| Monthly listeners | Distinct non-bot users with ≥ 1 listen credited to the artist in that calendar month (UTC), from `artist_month_clean`. A listen credited to several artists counts for each. A month with no listens = 0. |
| `baseline` / `recent` | Mean of monthly listeners over Mar–May / Jun–Aug 2026: (sum of the 3 months) ÷ 3, zeros included. |
| `growth` | (`recent` − `baseline`) ÷ `baseline`, a proportion. `null` when `baseline` = 0; such artists are never shortlisted. |
| Cutoffs (`thresholds()`) | `recent_cutoff` = `size_pct` quantile of `recent`; `growth_cutoff` = `growth_pct` quantile of `growth` (linear interpolation), over all artists with `baseline` ≥ `min_baseline`. Only those three controls change the cutoffs; release year, genre and country filter afterwards. |
| Shortlisted | `baseline` ≥ `min_baseline`, `recent` ≤ `recent_cutoff`, `growth` ≥ `growth_cutoff`, `first_release_date` ≥ `min_release`, plus optional genre (exact match within `top_genres`) and country. |
| Established artist | `recent` > the **default** `recent_cutoff` (87.3), independent of the sliders. |
| `share_of_fans` | Of all non-bot users who listened to the selected artist at any time Mar–Aug 2026 (`user_artist_clean`), the share who also listened to the other artist in that window. |
| Track `recent` / `baseline` | Mean monthly distinct listeners of a recording over Jun–Aug / Mar–May (`recording_month`); tracks are matched by the artist's MBID. |

### Filters (U1) — any change reloads the shortlist (300 ms debounce) and resets the table to page 1
| Control | Type | Default | `shortlist()` argument |
|---|---|---|---|
| First release on/after | Year select 2015–2026 | 2023 | `min_release` = `"YYYY-01-01"` |
| Min baseline listeners/month | Number 1–50 | 5 | `min_baseline` |
| Audience size: below percentile | Slider 50–99 | 90 | `size_pct` = value / 100 |
| Growth: at/above percentile | Slider 50–99 | 90 | `growth_pct` = value / 100 |
| Genre | "All genres" + `genre_options()` | All | `genre` (omit for All) |
| Country (ISO code) | "All countries" + `country_options()` | All | `country` (omit for All) |
| Reset | Button | — | restores all defaults |

Helper text under Genre: "Only ~18% of shortlisted artists have genre tags."

### Views and metrics
| Element | Serves | Question it answers | Source → field(s) | Display |
|---|---|---|---|---|
| KPI: Artists shortlisted | U1 | How many candidates meet the bar? | number of rows returned by `/api/shortlist` | integer |
| KPI: Size cutoff | U1 | What counts as "small" now? | `thresholds()` → `recent_cutoff` | "≤ 87.3 listeners/mo" |
| KPI: Growth cutoff | U1 | What counts as "fast-growing" now? | `thresholds()` → `growth_cutoff` | "≥ +28%" |
| Scatter | U1 | Who grows fastest relative to size? | `shortlist()` → x `recent` (log axis), y `growth` × 100 (%) | one color per first-release year; dashed lines at both cutoffs; tooltip: name, recent, growth |
| Table | U1 | Ranked list to scan | `shortlist()` | Name, Country, Genres, First release, Baseline/mo, Recent/mo, Growth %, [Add]; sorted by growth desc; any column sortable; 25 rows/page |
| Detail header | U2 | Who is this? | `artist_profile(id)` | name, type, country, genres, first release, baseline, recent, growth, [Add] |
| Trend line | U2 | Sustained growth or a spike? | `artist_trend(id)` → `month`, `listeners` | 6 points Mar–Aug 2026; Mar–May shaded "baseline", Jun–Aug "recent" |
| Fans also play | U3 | Which taste community? | `fans_also_play(id, 10)` → `name`, `top_genres`, `share_of_fans` | horizontal bars, % of this artist's listeners; label = name + first genre in `top_genres` |
| Top tracks | U4 | Which track drives the growth? | `top_tracks(id, 5)` → `url`, `recent`, `baseline` | rows "Track 1…5" linked to `url`, with recent vs baseline listeners/mo |
| Shortlist tray | U5 | What am I handing off? | client state + `fans_also_play(id, 1)` | name, growth %, "Sounds like: <top fans-also-play name>", [Remove], [Export CSV] |

**Interactions:** clicking a table row or a scatter point selects that artist, highlights it in both, and loads the four detail sections in parallel. The selection stays when filters change, even if the artist leaves the shortlist. **Add** (table or detail header) puts the artist in the tray and ignores duplicates. It fetches `fans/?n=1` for "Sounds like" if not already cached; if there is none, it shows "—". **Export CSV** downloads `shortlist.csv` with columns `artist_mbid, name, country, first_release_date, baseline, recent, growth, sounds_like`, in tray order. The tray is kept in page memory only.

**Display rules:** missing genre/country → "Unknown"; growth = `growth × 100`, no decimals, with sign; listener counts one decimal; dates `YYYY-MM-DD`. While a section loads it shows "Loading…". Empty shortlist → "No artists match — loosen a filter" in place of the scatter and table. Empty top tracks → "No track-level data". A failed request shows "Couldn't load — retry" in that section only. Footer: "Source: ListenBrainz (dump 2722) + MusicBrainz, Mar–Aug 2026. ListenBrainz listeners are self-selected enthusiasts; growth means traction in this community, not mainstream popularity."

## 4. Architecture

Each piece has one job and talks only to its neighbor, so each can be built and checked alone.

| Piece | Path | Job | Checked by | Must not |
|---|---|---|---|---|
| Data | `~/dso576_data/clean/*.parquet` | Canonical tables (`DATA_DECISIONS.md`) | `extraction/` logs | be written by the app |
| Analysis | `backend/analysis.py` (exists) | All metric logic → DataFrames; safe for concurrent calls | `python backend/analysis.py` | know about HTTP or HTML |
| API | `api/app.py` | Translate HTTP ↔ analysis calls; serve `web/` | curl / `/docs` | contain metric logic |
| Fetch | `web/api.js` | One function per endpoint, returns parsed JSON or throws | browser console | touch the DOM |
| Charts | `web/charts.js` | `renderScatter`, `renderTrend`, `renderFans(container, data)`; draw only | open with sample JSON | fetch or hold state |
| App | `web/app.js` + `index.html` + `styles.css` | One `state` object (`filters`, `rows`, `thresholds`, `selectedId`, `tray`), event wiring, table, KPIs, tray, CSV | acceptance checks | compute metrics (sort, page and format are fine) |

`web/*.js` are ES modules (`<script type="module">`). No other shared state.

### API contract
| Endpoint | Calls | Returns (JSON) |
|---|---|---|
| `GET /api/options` | `genre_options()`, `country_options()` | `{genres:[str], countries:[str], defaults:{min_release:"2023-01-01", min_baseline:5, size_pct:0.9, growth_pct:0.9}}` |
| `GET /api/shortlist?min_release&min_baseline&size_pct&growth_pct&genre&country` (all optional) | `thresholds()`, `shortlist()` | `{thresholds:{recent_cutoff, growth_cutoff, n_scored}, artists:[Artist]}` |
| `GET /api/artist/{id}` | `artist_profile(id)` | `Artist`, 404 if unknown |
| `GET /api/artist/{id}/trend` | `artist_trend(id)` | `[{month, listeners, listens}]` (`month` = 202603…202608) |
| `GET /api/artist/{id}/fans?n=10` | `fans_also_play(id, n)` | `[{artist_id, name, top_genres, recent, shared_listeners, share_of_fans}]` |
| `GET /api/artist/{id}/tracks?n=5` | `top_tracks(id, n)` | `[{recording_mbid, url, recent, baseline, listens}]` |

`Artist` = `{artist_id, artist_mbid, name, artist_type, country, top_genres, first_release_date, baseline, recent, growth}`. `growth` and `share_of_fans` are proportions (0.28 = 28%). `top_genres` is a "; "-separated string or null. NaN → `null`, dates → `"YYYY-MM-DD"`, invalid parameters → 422.

## 5. Technical choices
- **API:** FastAPI + uvicorn, run with `uvicorn api.app:app --reload`, open `http://localhost:8000`. FastAPI serves `web/` at `/`.
- **Queries:** `analysis.py` uses DuckDB on the Parquet files in place, so nothing large is loaded into memory (the track table is 1.2 GB). All functions together run in about 1 s on a MacBook Air.
- **Web:** plain HTML/CSS/vanilla JS; Chart.js 4 from cdnjs; no framework, no build step.
- **Caching:** the analysis layer caches thresholds, options and top tracks; `web/api.js` caches artist responses by id for the session.
- **Config:** only `DSO576_DATA` (data folder). The browser uses relative `/api/...` URLs, so deployment = the same app on any host with the Parquet files.

## 6. Build order
1. `api/app.py`: six endpoints; check each with curl or `/docs`.
2. `web/api.js` + `web/app.js` skeleton: filters from `/api/options`, KPIs and table from `/api/shortlist`.
3. `web/charts.js` scatter; selection sync between table and scatter.
4. Detail panel: header, trend, fans also play, top tracks.
5. Shortlist tray and CSV export.
6. Loading, empty and error states; narrow layout; footer.

## 7. Acceptance checks
1. `python backend/analysis.py` prints the data summary (610,423 artists; 1,131 shortlisted; 82.5% of them without genre) and `ok: 1131 shortlisted…`.
2. `GET /api/shortlist` (no parameters) returns 1,131 artists with `recent_cutoff` ≈ 87.3 and `growth_cutoff` ≈ 0.281; on page load the KPIs read 1,131 / ≤ 87.3 / ≥ +28%.
3. The table's first row is **EVAN** (KR, +1456%). Selecting it shows trend listeners 5, 6, 5, 89, 99, 61 and **BTS** first in "Fans also play" (89%).
4. First release 2025 → fewer rows, same cutoffs. Genre "hip hop" → every row's genres include "hip hop", same cutoffs.
5. Shortlisted artists without genres show "Unknown".
6. Adding 3 artists (one twice) and exporting gives `shortlist.csv` with 3 rows and the 8 listed columns.
7. Stop the API, then click an artist that has not been opened this session (so nothing is cached): its detail sections show "Couldn't load — retry" while the rest of the page stays usable.

## 8. Out of scope
Listener demographics, listener location, playlist data (not in any source); predicting future hits; accounts or saved shortlists; editing data; track titles (not in the data, so tracks link to MusicBrainz).
