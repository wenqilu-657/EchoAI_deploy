# My Module 9 audit — Kunjesh Gupta

## Context

- **Name:** Kunjesh Gupta
- **Team app and version or commit checked:** Commit `5f34885` / `dc140f0` (Emerging Artist Discovery app, Phase 2 backend & Phase 3 web dashboard)
- **Intended user and decision:** Editorial curation lead at a music streaming service or independent playlist brand deciding which emerging artists to add to next month’s discovery playlists, and which taste community (co-listened established artists) each one fits into.

---

## 1. Feature audit: Shortlist Tray & CSV Export (U5)

- **Feature and intended behavior:**
  In U5, when a curator identifies an emerging artist for playlist consideration, they click **Add** (from either the ranked table row or the detail panel header). This adds the artist to the bottom Shortlist Tray, automatically queries `GET /api/artist/{id}/fans?n=1` to populate a "Sounds like" artist recommendation, ignores duplicate clicks, and exports the final tray contents to `shortlist.csv` via the **Export CSV** button.

- **Inputs and steps to reproduce:**
  1. Start the app server (`uvicorn api.app:app`) and open `http://localhost:8000`.
  2. Click **Add** on EVAN in the table row. Verify that EVAN appears in the bottom tray with `Sounds like: BTS`.
  3. Click **Add** on EVAN again (from both the table row and the detail panel header).
  4. Click **Add** on two other emerging artists.
  5. Click **Export CSV** and open `shortlist.csv` in a text editor and spreadsheet application.
  6. Reload the browser page (`F5` or `Cmd+R`).
  7. Run `python audit/kunjesh_audit_checks.py` (feature section).

- **Expected behavior:**
  1. Adding an already-queued artist is an idempotent no-op (no duplicate rows in the tray or the exported CSV).
  2. "Sounds like" artist correctly displays the #1 co-listened established artist from `fans_also_play(id, 1)`.
  3. The exported CSV contains exactly the 8 columns specified in BUILD_SPEC §3: `artist_mbid, name, country, first_release_date, baseline, recent, growth, sounds_like`.
  4. Formula injection protection is applied to cells starting with `=`, `+`, `-`, or `@` to protect spreadsheet users.

- **Actual behavior and evidence:**
  * **Deduplication:** PASS. `web/app.js` line 123 checks:
    ```javascript
    if (!a || state.tray.some((t) => t.artist.artist_id === a.artist_id)) return;
    ```
    Repeated clicks on the same artist do not create duplicate tray cards or duplicate CSV rows.
  * **"Sounds like" resolution:** PASS. Resolves via:
    ```javascript
    (await getFans(a.artist_id, 1))[0]?.name ?? "—"
    ```
    For EVAN, BTS is returned and displayed as the top co-listened artist.
  * **Formula injection escaping:** PASS. `csvCell()` in `web/app.js` line 147 tests `/^[=+\-@\t\r]/.test(s)` and prepends a single quote `'` so spreadsheet programs (like Excel) do not execute strings starting with formula operators.
  * **CSV Growth Column Format:** In `web/app.js`, `growth` is exported as an unrounded decimal ratio (e.g., `14.5625`) without a `%` sign. While mathematically precise for data pipelines, curators opening the CSV directly in Excel may expect a formatted percentage (e.g., `+1456%`) or an explicit header (`growth_ratio`).
  * **Tray In-Memory Volatility:** The tray is stored purely in client-side JavaScript memory (`state.tray`). If a curator reloads the page, the queued tray is wiped clean.

- **Conclusion and recommended change:**
  The feature meets the specification and correctly implements formula injection security safeguards. Recommended improvements:
  1. Add `localStorage` caching so accidental page refreshes do not wipe the curator's curated shortlist tray.
  2. Rename the exported header to `growth_ratio` or format it as a percentage string (`+1456%`) to match the dashboard display.

---

## 2. Number audit: Audience Size & Growth Cutoff Quantiles (`thresholds()`)

- **Number audited and its meaning:**
  The audience size cutoff (`recent_cutoff`, default $\le 87.3$ listeners/mo) and growth cutoff (`growth_cutoff`, default $\ge +28.1\%$) shown in the KPI summary cards and as dashed reference lines on the size-vs-growth scatter plot.

- **Formula, units, population, and time window:**
  * **Population:** All artists with `baseline >= min_baseline` (default $\ge 5$ listeners/month over March–May 2026).
  * **Size Cutoff:** 90th percentile of `recent` (average monthly distinct listeners over June–August 2026).
  * **Growth Cutoff:** 90th percentile of `growth = (recent - baseline) / baseline`.
  * **Time window:** March–August 2026 (6 calendar months).
  * **Units:** listeners/month for `recent`; proportion (decimal ratio) for `growth`.
  * **Formula in code:** DuckDB `quantile_cont(recent, 0.90)` and `quantile_cont(growth, 0.90)`.

- **Relevant data assumptions:**
  1. An artist is "emerging" if their audience is small (below the 90th percentile of active acts) and fast-growing (at or above the 90th percentile of growth).
  2. The percentiles must be calculated globally across all active artists before categorical filters (genre or country) are applied, so cutoffs remain objective standards rather than shifting relative to a niche sub-genre.

- **Code checked:**
  `backend/analysis.py`, lines 61–88:
  ```python
  @lru_cache(maxsize=32)
  def thresholds(min_baseline=5, size_pct=0.90, growth_pct=0.90):
      row = _con().cursor().execute("""
          SELECT quantile_cont(recent, ?), quantile_cont(growth, ?), count(*)
          FROM artist_metrics WHERE baseline >= ?""", [size_pct, growth_pct, min_baseline]).fetchone()
      return {"recent_cutoff": row[0], "growth_cutoff": row[1], "n_scored": row[2]}
  ```

- **What this code computes, in my own words:**
  It queries the `artist_metrics` view, filters down to artists with at least `min_baseline` listeners, and calculates continuous 90th percentiles for `recent` listeners and `growth` ratio using DuckDB's `quantile_cont` (linear interpolation).

- **Small test case and expected result:**
  Consider 5 scored artists with recent monthly listeners: `[10, 20, 30, 40, 50]`.
  * Target percentile: `size_pct = 0.90`.
  * Percentile rank index: $0.90 \times (5 - 1) = 3.6$.
  * Linear interpolation between index 3 (40) and index 4 (50):
    $$40 + 0.6 \times (50 - 40) = 46.0$$
  * Expected continuous quantile: `46.0`.

- **Actual result:**
  DuckDB's `quantile_cont(recent, 0.90)` on this small test case produces exactly `46.0`.
  On the team's canonical dataset:
  * `recent_cutoff = 87.3333` (displayed as `≤ 87.3 listeners/mo`)
  * `growth_cutoff = 0.2807` (displayed as `≥ +28%`)
  * `n_scored = 48,154` artists

- **Independent check of filter decoupling:**
  I checked whether changing the Genre or Country filter shifts the cutoffs. In `backend/analysis.py::shortlist()`:
  ```python
  t = thresholds(min_baseline, size_pct, growth_pct)
  ```
  `thresholds()` is called independently of `genre` and `country`. The categorical SQL conditions (`country = ?`, `list_contains(...)`) are applied to filter the shortlist rows afterwards.
  * Verified: Selecting `Country = KR` or `Genre = hip hop` filters the table rows without moving the p90 reference lines on the scatter plot or KPI cards.
  * This confirms Decision D8: emerging criteria remain universal and objective rather than relative to a niche market.

- **What the evidence establishes and what remains uncertain:**
  * **Established:** DuckDB continuous quantiles interpolate correctly, and the cutoffs are strictly decoupled from category filters.
  * **Uncertainty:** Whether continuous linear interpolation (`quantile_cont`) is preferable to discrete nearest-rank (`quantile_disc`) for discrete integer listener counts. For 48,154 artists, the difference between continuous and discrete quantiles is negligible ($< 0.1$ listener).

- **Recommended change:**
  None; the calculation is mathematically correct, performant, and properly cached via `@lru_cache(maxsize=32)`.

---

## 3. Additional Feature / Coverage Audit: Genre Filter Behavior

- **Feature & Intended Behavior:**
  U1 Genre filter allows narrowing emerging candidates by genre tags from MusicBrainz.
- **Finding:**
  In `backend/analysis.py`, genre matching uses:
  ```sql
  list_contains(string_split(top_genres, '; '), ?)
  ```
  * Semicolon-delimited matching correctly identifies multi-genre acts (e.g. searching "pop" correctly matches "k-pop; pop").
  * However, as noted in the UI hint, **only ~18% of shortlisted artists have genre tags** in MusicBrainz. Filtering by any genre hides the ~82% of artists with null genres. The inclusion of the UI reminder ("Only ~18% of shortlisted artists have genre tags") is essential so curators do not falsely conclude that an emerging scene has no new acts.

---

## My contribution

- **What I personally checked and concluded:**
  * Verified the Shortlist Tray deduplication, top-fan "Sounds like" resolution, and CSV formula injection escaping on the running dashboard.
  * Verified DuckDB's continuous quantile interpolation formula for `thresholds()` and confirmed filter independence.
  * Checked multi-genre tag parsing and verified coverage implications for emerging acts.
  * Wrote and executed the reproducible check script `audit/kunjesh_audit_checks.py`.
- **How AI helped:**
  Assisted with setting up the test environment, verifying API route responses, and drafting the audit documentation against the project codebase.
