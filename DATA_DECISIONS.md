# Data decisions (Phase 2 reconciliation)

Team EchoAI's single source of truth for data definitions. BUILD_SPEC.md and the backend code use these definitions. Decided 2026-10-18, after comparing all five Module 6 cleanings.

## 1. What each Module 6 cleaning did

| Member | Data | One row = | Artist key | Bots | "Emerging" |
|---|---|---|---|---|---|
| Navya | MusicBrainz `artist` table, dump 20260930 (2,999,670 artists) | artist | MBID (`gid`) | n/a | undecided |
| Hosung | All Jun–Aug 2026 listens (Spark dump 2663) joined to MusicBrainz | user × artist × month | MBID | dropped >500 listens/day | first release ≥ 2023-01-01 & ≥ 20 listeners |
| Lorelei | 1% user sample, Jun–Aug 2026, dump 2663 (821,915 listens) | listen | name key + MBID | reviewed list required, not applied | same as Hosung |
| Tony | API, user `rob`, 100 listens | listen | name | none | — |
| Kunjesh | API, user `hwnrwx`, 50 listens | listen | name key | none | — |

**Already agreed (kept as is):** drop exact duplicate listens; keep repeat listens and same-timestamp listens to different recordings; never impute missing values (missing = `Unknown` / `has_*` flag); keep raw data unchanged and outside git.

Tony's and Kunjesh's single-user API samples validated the listen record format. They are too small for artist-level metrics, so they are not part of the canonical data.

## 2. Decisions

| # | Topic | Decision | Why |
|---|---|---|---|
| D1 | Source | ListenBrainz Spark full dump **2722 (2026-10-15)**, **all users**, listens **2026-03-01 to 2026-09-01 (exclusive)**, joined to MusicBrainz export **20260930-002222**. | Six months are needed for a trend. A 1% sample leaves small artists with 0–2 listeners. Dump 2663 is no longer published. |
| D2 | Unit of analysis | Dashboard tables are **artist** (one row per artist), **artist × month**, **user × artist** (for co-listening), and **recording × month**. Listens are only an intermediate step. | The decisions are about artists. Aggregates keep the dashboard fast. |
| D3 | Artist identity | **MusicBrainz artist MBID**. Merged MBIDs are redirected to the surviving artist. A listen credited to several artists counts once for each. Names are for display only. | Names are not unique (for example, "Indigo" is 250 different artists). |
| D4 | Listens without an MBID | Excluded from artist metrics, counted in the log (37.3M of 244.8M deduplicated listens, 15%). | Matching by name would merge different artists. |
| D5 | Bots | Exclude users with **> 500 listens on any UTC day** (1,692 of 58,378 users; 39.2% of listens). Report the > 1,000 threshold as a sensitivity check (28.4% of listens). | One listener scrobbling thousands of plays a day would dominate a small artist's numbers. |
| D6 | Special-purpose artists | Exclude MusicBrainz special-purpose artists (Various Artists, [unknown], …). | They are not real artists. |
| D7 | Growth | `baseline` = average monthly distinct listeners, Mar–May. `recent` = the same for Jun–Aug. `growth = (recent − baseline) / baseline`. Only computed when `baseline ≥ 5`. | Three-month averages smooth one-month spikes. Below 5 listeners, growth is noise. |
| D8 | Emerging shortlist (defaults) | `first_release_date ≥ 2023-01-01` **and** `baseline ≥ 5` **and** `recent ≤` 90th percentile **and** `growth ≥` 90th percentile. Percentiles are computed over all artists with `baseline ≥ 5`. Defaults give **1,131 artists** (p90 recent = 87.3 listeners/month, p90 growth = +28.1%). All four thresholds are dashboard controls. | Combines the team's release rule (Hosung = Lorelei) with "small but growing". Without the release filter, legacy acts (e.g., Tammy Wynette) dominate. |
| D9 | Taste community | For a selected artist: established artists ranked by the **share of the selected artist's listeners who also listen to them**, using `user_artist_clean`. | Behavioural segment, no demographic data needed. |
| D10 | Missing metadata | Genre, country and release date stay missing; filters include an "Unknown / all" option. | Coverage is low (below). |

## 3. Checked coverage and edge cases (canonical run)

| Item | Value |
|---|---|
| Listens in window → after dedup → credited to an artist | 249,645,377 → 244,794,323 → 232,640,849 |
| Monthly raw listens, Mar–Aug | 42.7M, 41.7M, 43.2M, 42.4M, 40.3M, 39.4M (no missing month) |
| Artists in `artists_clean` | 610,423 |
| With genre / country / first release date | 121,512 (20%) / 382,292 (63%) / 458,297 (75%) |
| Shortlist with genre / country | 198 of 1,131 (18%) / 639 (56%) |
| Artists debuting Mar 2026 or later with ≥ 5 recent listeners but < 5 baseline | 355. **Excluded from growth ranking** (no baseline). |
| Future first-release dates in shortlist | 0 |

## 4. Known limits (for the write-up)

- ListenBrainz users are self-selected enthusiasts, not a streaming platform's audience. Growth means traction within this community.
- No listener age, gender, location, or playlist data exists in any source.
- The genre filter covers only 18% of the default shortlist. "All genres" is the default.

## 5. Rebuild

See `extraction/` (scripts, run order, Python 3.13). Outputs are written to `~/dso576_data/clean/` and are not committed.
