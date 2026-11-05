# BUILD_SPEC — Emerging Artist Discovery (Team EchoAI) · v2.0

## 1. Vision & Problem Definition

**User:** An editorial curation lead at a music streaming service or independent playlist brand (platform-agnostic).
**Decision:** Which small but fast-growing artists to add to next month's discovery playlists, and which **taste community** each artist fits into.
**Core Mechanism:**
- **Emerging:** Small audience (`recent` monthly listeners $\le$ 90th percentile) combined with high listener growth (`growth` $\ge$ 90th percentile) over a 6-month observation window (March–August 2026).
- **Taste Communities:** Established artists co-listened to by the same listeners (`share_of_fans`), providing immediate stylistic and audience context even when genre tags are completely missing (which is true for ~82% of emerging artists).
- **Audit Resolutions (v2.0):**
  - **AUDIT-01 (Catalogued vs Debut):** Relabeled release date to "First Catalogued (MB)" with an active UI badge indicating when listening activity predated the catalogued release date.
  - **AUDIT-02 (Debut Spike vs Steady Risers):** Introduced curator presets separating "Steady Risers" (consistent audience throughout baseline months) from "Fresh Debuts" (sudden mid-window arrivals with zero-listener early months), ensuring fair growth comparisons.
  - **AUDIT-03 (Top Tracks Context):** Provides recording-level traction metrics with direct MusicBrainz links and listener trajectories.
  - **AUDIT-04 (Country Filter Inclusivity):** Added explicit "Unknown" country filtering so curators can discover the 44% of shortlisted artists lacking country metadata.
  - **Shortlist Persistence & Security:** Tray saved in `localStorage` across page reloads; CSV export hardened against spreadsheet formula injection.

### Use Cases (Select → See → Decide)
| # | User Selects / Inputs | Dashboard Shows | Curator Decides |
|---|---|---|---|
| **U1** | Curator preset or custom sliders (release year, baseline, size & growth percentiles, genre, country) | Ranked shortlist table, KPI summary strip, and size-vs-growth scatter plot | Which artists qualify for detailed editorial review |
| **U2** | Clicks an artist in the table or scatter dot | Profile header, narrative summary sentence ("Why is this artist here?"), and 6-month monthly listener trend | Whether the artist shows sustained momentum or a fleeting spike |
| **U3** | Same artist | "Fans also play" taste community bar chart (% of shared fans playing established artists) | Which playlist sub-genre / sound community the artist fits |
| **U4** | Same artist | Top tracks ranked by recent monthly listeners, linked to MusicBrainz recordings | Which specific song to slot into the playlist |
| **U5** | Clicks **Add** to shortlist, then **Export CSV** | Bottom shortlist tray with automatic "Sounds like" top reference artist, persisted in `localStorage` | Final shortlisted handoff exported to scheduling |

---

## 2. Builder Rules & Governance

1. **Single Source of Truth:** All metrics are computed strictly in one backend module: [`backend/analysis.py`](file:///Users/kunjeshgupta/Documents/USC MSBA/dso576/dso576_project/backend/analysis.py). The API and browser never compute or redefine a metric. Sorting, pagination, formatting, and client-side tray management are permitted.
2. **Mandatory Guess Logging (`BUILD_NOTES.md` Rule):** Any builder or autonomous agent working from this spec must log **every single guess or design choice** made where this spec was silent or ambiguous in [`BUILD_NOTES.md`](file:///Users/kunjeshgupta/Documents/USC MSBA/dso576/dso576_project/BUILD_NOTES.md) (Format: `Section | What was unclear | What was chosen and why`). Completion requires that this log is reviewed and verified.
3. **Verified Numbers:** Every number quoted in documentation and tests must be verified against actual data. Never guess row counts or percentiles.
4. **Scope Control:** Build strictly what is specified in sections 3–6. Section 9 is strictly out of scope.

---

## 3. Metric Definition Table

All metrics are implemented in [`backend/analysis.py`](file:///Users/kunjeshgupta/Documents/USC MSBA/dso576/dso576_project/backend/analysis.py) and adhere to canonical definitions in [`DATA_DECISIONS.md`](file:///Users/kunjeshgupta/Documents/USC MSBA/dso576/dso576_project/DATA_DECISIONS.md).

| Metric | Code Definition (`backend/analysis.py`) | Interpretation & Boundaries |
|---|---|---|
| **Monthly Distinct Listeners** | Distinct non-bot users scrobbling $\ge 1$ listen credited to the artist in that calendar month (UTC). Months with zero scrobbles = `0`. | Bot accounts (>500 scrobbles on any UTC day) removed (Decision D5). Listen credited to multiple artists counts once for each. |
| **Baseline Listeners (`baseline`)** | `(listeners_2026_03 + listeners_2026_04 + listeners_2026_05) / 3.0` | Arithmetic mean of monthly distinct listeners over March–May 2026 (Decision D7). Fractional values allowed. |
| **Recent Listeners (`recent`)** | `(listeners_2026_06 + listeners_2026_07 + listeners_2026_08) / 3.0` | Arithmetic mean of monthly distinct listeners over June–August 2026 (Decision D7). |
| **Growth (`growth`)** | `(recent - baseline) / NULLIF(baseline, 0)` | Fractional ratio (e.g. `1.456` = +145.6% growth). Artists with `baseline = 0` yield `NULL` and are excluded from standard growth ranking. |
| **Size Cutoff (`recent_cutoff`)** | `quantile_cont(recent, size_pct)` over all artists with `baseline >= min_baseline`. Default $p90 \approx 87.33$. | Linear continuous interpolation. Computed globally before genre/country filters so cutoffs remain objective. |
| **Growth Cutoff (`growth_cutoff`)** | `quantile_cont(growth, growth_pct)` over all artists with `baseline >= min_baseline`. Default $p90 \approx 0.2807$ (+28.1%). | Linear continuous interpolation across active candidate population. |
| **Shortlist Criteria** | `baseline >= min_baseline` AND `recent <= recent_cutoff` AND `growth >= growth_cutoff` AND `first_release_date >= min_release` (plus optional genre & country). | Default filters yield **1,131 artists** on canonical data. |
| **Established Artist** | Artist with `recent > default_recent_cutoff` (87.3 listeners/mo). | Reference benchmark for co-listening comparisons. |
| **Share of Fans (`share_of_fans`)** | `shared_listeners / count(fans)` where fans are users who listened to the target artist during Mar–Aug 2026. | Proportion [0.0, 1.0]. Represents co-listening overlap with an established act. |
| **Track Traction (`recent` / `baseline`)** | Mean monthly distinct listeners of a recording during Jun–Aug vs. Mar–May (`recording_month`). | Sourced from recording-level listens; mapped by artist MBID. |

---

## 4. Dashboard Views & Interactions

The dashboard is a responsive single-page application. At screen widths below 900px, elements stack vertically in logical order.

```
+------------------------------------------------------------------------------------+
|  HEADER: EchoAI — Emerging Artist Discovery          [Shortlist Tray Count: (3)]    |
|  KPI Strip: [1,131 Shortlisted] | [Size: <= 87.3/mo] | [Growth: >= +28%]           |
+------------------------------------------------------------------------------------+
|  PRESETS: [ Breaking Out ] [ Steady Climbers ] [ Fresh Debuts ] [ Hidden Gems ]    |
+--------------------------+----------------------------------+----------------------+
| FILTERS (U1)             | MAIN VISUALIZATIONS              | DETAIL PANEL (U2-U4) |
| - First Catalogued >=    | Scatter Plot (Size vs Growth)    | - Artist Profile     |
| - Min Baseline / mo      | [Interactive log-x, %-y points]  |   "Why here?" note   |
| - Size Percentile Slider +----------------------------------+ - 6-Mo Trend Line     |
| - Growth Pct Slider      | Ranked Emerging Artists Table    | - Fans Also Play     |
| - Genre (All / Specific) | Name | Country | MB Date | Growth| - Top Tracks         |
| - Country (All / Unknown)| [Page 1 of 46] [Add to Tray]     |   [Add to Shortlist] |
+--------------------------+----------------------------------+----------------------+
| BOTTOM TRAY (U5): Shortlist (3) | EVAN (Sounds like BTS) | [Export CSV] [Clear]     |
+------------------------------------------------------------------------------------+
```

### 4.1 Header & KPI Strip
- **KPI 1: Artists Shortlisted:** Total candidate acts meeting active filter criteria (`artists.length`).
- **KPI 2: Audience Size Cutoff:** Current upper bound for "emerging" acts (`recent_cutoff`, e.g. "$\le$ 87.3 listeners/mo").
- **KPI 3: Growth Cutoff:** Current minimum growth threshold (`growth_cutoff`, e.g. "$\ge$ +28%").

### 4.2 Curator Presets Bar
One-click presets that configure filter parameters instantly:
1. **Breaking Out (Default):** `size_pct = 0.90`, `growth_pct = 0.90`, `min_baseline = 5`, `min_release = 2023-01-01`. Captures the premier 90th-percentile emerging cohort.
2. **Steady Climbers (AUDIT-02):** Filters for sustained growth acts with scrobbles in all three baseline months (`listeners > 0` in Mar, Apr, and May).
3. **Fresh Debuts (AUDIT-02):** Highlights artists who debuted in the window (0 baseline listeners in Mar/Apr with a burst in May/Jun).
4. **Hidden Gems:** `min_baseline = 3`, `size_pct = 0.75`, `growth_pct = 0.95`. Finds small acts with sharp momentum.
5. **Custom:** Activated whenever the user modifies any slider or dropdown manually.

### 4.3 Filter Panel (U1)
- **First Catalogued in MB On/After:** Year dropdown (2026 down to 2015). Default `2023`.
- **Min Baseline Listeners/mo:** Number input clamped to 1–50. Default `5`.
- **Audience Size Percentile:** Slider 50%–99%. Default `90%`.
- **Growth Percentile:** Slider 50%–99%. Default `90%`.
- **Genre:** Dropdown of top 40 genres from `genre_options()` + "All genres". Helper text: *"Only ~18% of shortlisted artists have genre tags."*
- **Country:** Dropdown of ISO countries from `country_options()` + "All countries" + explicit **"Unknown"** option (resolves AUDIT-04).
- **Reset:** Restores default settings.
- *Debounce:* Any filter modification debounces 300ms before querying `/api/shortlist` and resets the table to page 1.

### 4.4 Size vs. Growth Scatter Chart (U1)
- **X-axis:** Average recent listeners/month on a logarithmic scale.
- **Y-axis:** Growth percentage (`growth * 100`).
- **Plotting:** Each dot represents an artist, color-coded by release year.
- **Reference Lines:** Dashed lines representing `recent_cutoff` (vertical) and `growth_cutoff` (horizontal).
- **Interactivity:** Hovering displays tooltip (`Name`, `Recent/mo`, `Growth %`, `Country`). Clicking selects the artist and highlights the dot with a distinct high-contrast border and 2x radius.

### 4.5 Ranked Shortlist Table (U1)
- **Columns:** Name, Country, Genres, First Catalogued (MB), Baseline/mo, Recent/mo, Growth %, Action (`[Add]`).
- **Sorting:** High-to-low on first click for numeric columns; alphabetical for text; reverse on second click. Missing values sort last. Default sort: `Growth %` descending.
- **Pagination:** 25 rows per page with previous/next controls and row count indicators.
- **Selection:** Clicking any row highlights it and opens the artist detail panel.

### 4.6 Artist Detail Panel (U2–U4)
- **Profile Header:** Name, type (Person/Group), Country, Genres, MusicBrainz link, and an **Add to Shortlist** button.
  - *Debut Intelligence Badge (AUDIT-01):* If listening activity predates the catalogued MusicBrainz release, displays an alert badge: *"Active scrobbles recorded prior to catalogued release"*.
- **Narrative Sentence ("Why is this artist here?"):** Generated dynamically (e.g., *"EVAN grew +1456% from 5.3 to 83.0 listeners/mo, with 89% of fans also listening to BTS."*).
- **6-Month Trend Line (U2):** Line chart showing monthly distinct listeners (March–August 2026). March–May zone shaded with subtle background color labeled *"Baseline"*; June–August shaded *"Recent"*.
- **Fans Also Play (U3):** Horizontal bar chart showing up to 10 established co-listened acts, ranked by `share_of_fans` with percentage labels.
- **Top Tracks (U4):** Table showing top recordings by recent listener traction, displaying recent listeners/mo, baseline listeners/mo, and direct clickable links to the song's MusicBrainz page.

### 4.7 Persistent Shortlist Tray & CSV Export (U5)
- **Client Persistence:** Stored in browser `localStorage` (`dso576_curator_tray`) so curator selections persist across browser refreshes.
- **Card Content:** Artist Name, Growth %, and top taste-community match (*"Sounds like: [Top Artist]"*).
- **Idempotency:** Adding the same artist multiple times is an automatic no-op.
- **Export CSV:** Downloads `shortlist.csv` containing:
  `artist_mbid, name, country, first_catalogued_date, baseline, recent, growth_percent, growth_ratio, sounds_like`
- **Security:** Formula injection prevention enabled: cells starting with `=`, `+`, `-`, `@`, `\t`, `\r` are prefixed with `'` to prevent arbitrary spreadsheet code execution.

---

## 5. System Architecture & API Contract

```
+-------------------------------------------------------------+
| Browser Client (Vanilla JS ES Modules, Chart.js 4.4.1)      |
| web/app.js  <-->  web/api.js  <-->  web/charts.js           |
+-------------------------------------------------------------+
                              | JSON HTTP /api/...
+-------------------------------------------------------------+
| FastAPI Application (api/app.py)                            |
| Validates request schemas, handles errors & CORS            |
+-------------------------------------------------------------+
                              | Python Calls
+-------------------------------------------------------------+
| Analysis Engine (backend/analysis.py)                       |
| Single source of truth; thread-safe DuckDB SQL on Parquet    |
+-------------------------------------------------------------+
                              | Direct Query Execution
+-------------------------------------------------------------+
| Canonical Parquet Tables (~/dso576_data/clean/)             |
| artists_clean, artist_month_clean, user_artist_clean, ...   |
+-------------------------------------------------------------+
```

### 5.1 API Endpoints (`api/app.py`)
- `GET /api/options`: Returns available genres, countries, and parameter defaults.
- `GET /api/shortlist?min_release&min_baseline&size_pct&growth_pct&genre&country&preset`: Returns `{thresholds: {recent_cutoff, growth_cutoff, n_scored}, artists: [...]}`.
- `GET /api/artist/{id}`: Returns profile metadata for a specific artist ID.
- `GET /api/artist/{id}/trend`: Returns array of 6 monthly listener counts for Mar–Aug 2026.
- `GET /api/artist/{id}/fans?n=10`: Returns top co-listened established acts (`share_of_fans`).
- `GET /api/artist/{id}/tracks?n=5`: Returns top recordings with MusicBrainz URLs and listener averages.

### 5.2 Deployment & Local Replication Architecture
- **Local 1-Command Execution (Professor / TA):**
  - **Python native:** `python run.py` (installs missing packages if needed, verifies tables, starts server, and automatically opens `http://localhost:8000`).
  - **Node / npx:** `npm start` (wraps execution through `package.json`).
- **Cloud Vercel Deployment:**
  - Standard Vercel Serverless Function entry point (`api/index.py` wrapping the FastAPI app).
  - Optimized Parquet / DuckDB dataset (<35MB) packaged within Vercel's serverless size limit (well under the 250MB limit) for instant <15ms response times.
  - Zero browser-side heavy downloads: client only receives tiny JSON payloads per query.

---

## 6. Data Cleaning & Replication Pipeline

To ensure the professor can verify data integrity and reproduce the cleaning process:
- **Executable Script:** [`scripts/clean_data.py`](file:///Users/kunjeshgupta/Documents/USC MSBA/dso576/dso576_project/scripts/clean_data.py) executes all cleaning rules:
  - **R1:** Bounding window to March 1 – August 31, 2026.
  - **R2–R3:** Deduplication of exact scrobbles while preserving multi-recording timestamps.
  - **R4–D5:** Exclusion of bot accounts (>500 scrobbles on any UTC day).
  - **R5–R7:** Multi-artist credit handling and mapping merged MBIDs to surviving artists.
  - **R8:** Removal of MusicBrainz special-purpose artists (e.g. *Various Artists*, *[unknown]*).
  - **R11–R12:** Validation of release dates and strict non-imputation of missing metadata.
- **Interactive Notebook:** [`notebooks/01_cleaning_replication.ipynb`](file:///Users/kunjeshgupta/Documents/USC MSBA/dso576/dso576_project/notebooks/01_cleaning_replication.ipynb) provides visual distributions, missingness analysis, and step-by-step audit tables.

---

## 7. Build Order

1. **Backend Verification & Extensions (`backend/analysis.py`):**
   - Ensure thread-safe DuckDB cursor allocation.
   - Verify `thresholds()`, `shortlist()`, `artist_trend()`, `fans_also_play()`, and `top_tracks()`.
   - Add "Unknown" country filtering support and preset categorization.
2. **API Layer (`api/app.py`):**
   - Implement the six REST endpoints with FastAPI and Pydantic validation.
   - Mount static file serving for `web/`.
3. **Web Client Core (`web/api.js` & `web/app.js`):**
   - Implement `api.js` client functions with fetch error handling.
   - Build filter bar, KPI strip, and paginated table in `app.js`.
4. **Visualizations (`web/charts.js`):**
   - Implement `renderScatter()` with log-x axis, cutoffs, and selection sync.
   - Implement `renderTrend()` with baseline/recent shaded bands.
   - Implement `renderFans()` with horizontal co-listening overlap bars.
5. **Detail Panel & Presets Integration:**
   - Connect artist selection to parallel detail fetches.
   - Implement dynamic "Why is this artist here?" summary generator.
   - Hook up preset buttons to auto-populate sliders and trigger queries.
6. **Shortlist Tray & CSV Export:**
   - Wire `localStorage` persistence, card rendering, and duplicate prevention.
   - Implement secure CSV generator with formula escaping.
7. **One-Command Runners & Vercel Configuration:**
   - Create `run.py`, `package.json`, and `vercel.json`.

---

## 8. Acceptance Checks (Must Pass 100%)

1. **Backend Self-Test:** `python backend/analysis.py` runs without errors, computes global quantiles, and verifies EVAN as #1 emerging artist.
2. **API Verification:** `curl http://localhost:8000/api/shortlist` returns default emerging shortlist with cutoffs (`recent_cutoff` $\approx 87.3$, `growth_cutoff` $\approx 0.281$).
3. **Ground Truth Validation:** Selecting **EVAN** (KR, +1456%) shows monthly listeners `[5, 6, 5, 89, 99, 61]`, and **BTS** is ranked #1 under "Fans also play" at **89%**.
4. **Preset Functionality:** Clicking "Steady Climbers" eliminates zero-baseline artists; clicking "Fresh Debuts" surfaces acts debuting mid-window.
5. **Filter Decoupling:** Changing Genre (e.g. to "hip hop") or Country filters the table rows without shifting the global cutoffs in the KPI strip.
6. **Country Inclusivity (AUDIT-04):** Selecting "Unknown" in the Country dropdown displays artists lacking country metadata (e.g. Silk & Static).
7. **Tray Persistence & Security:** Adding artists persists in `localStorage` across page refresh; exporting CSV generates all 9 columns with formula characters safely escaped.
8. **Fault Tolerance:** If the backend is temporarily disconnected, the UI gracefully displays *"Couldn't load — retry"* on affected cards while keeping the page responsive.

---

## 9. Out of Scope

- **Demographic listener data:** Age, gender, and listener location do not exist in MusicBrainz or ListenBrainz.
- **Predictive hit forecasting:** The app surfaces empirical historical traction, not machine-learning hit predictions.
- **User authentication or multi-user cloud accounts:** Shortlist state is maintained locally in `localStorage`.
- **Modifying raw data:** Upstream source dumps are treated as immutable.
