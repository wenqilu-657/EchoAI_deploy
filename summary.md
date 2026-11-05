# DSO 576 Emerging Artist Discovery: Restart Summary

2026-11-04

## What the project is

A dashboard that helps a streaming or indie playlist curator find emerging artists and build a shortlist. This summary is built from the project's past chats and has not been checked against the repo, so confirm the current state there.

- **Course project:** DSO 576 at USC Marshall, team EchoAI (Navya, Hosung, Lorelei, Tony, Kunjesh). Repo: `kunjeshgupta/dso576_project`. Everybody works on their own name branch. 
- **Data:** MusicBrainz plus ListenBrainz (Spark dump 2722), covering March to August 2026.
- **Stack:** Python and DuckDB/Parquet backend (`backend/analysis.py`), FastAPI (`api/app.py`), and a plain HTML/vanilla JS frontend (`web/`).

## How the vision evolved

The project moved from three candidate concepts to one emerging-artist tool, and from demographic segments to taste communities.

1. **Three candidate concepts:** Breakout Radar (rank by expected 90-day retention), Adjacency Map (co-listening graph vs. MusicBrainz metadata), and Taste Trajectory (listener taste evolution plus churn risk). The team chose the emerging-artist direction.
2. **Stakeholder:** first framed at Spotify, then made platform-agnostic after instructor feedback. The stakeholder is now a generic streaming or indie playlist curator.
3. **Phase 1 feedback:** the demographic "listener segment" panel (age, gender, markets) could not be supported by the data. It was replaced by **taste communities**, based on co-listening overlap.
4. **Definition of "emerging":** a small but growing audience, using percentile-based thresholds. The growth window was extended to 6 months.

## Key data and metric decisions

All metrics are computed in one module, `backend/analysis.py`, and never recomputed elsewhere.

- **Decisions log:** `DATA_DECISIONS.md` reconciles all five teammates' cleaning branches into ten numbered decisions (source, bot rules, emerging definition, growth formula, and so on).
- **Scale:** 610,423 artists in the canonical tables. The default emerging shortlist has 1,131 artists.
- **Genre tags are sparse:** only about 18% of artists have them, which is why taste-based discovery matters.
- **Storage:** the cleaned dataset (about 1.5 GB) lives outside Git on a team Google Drive folder. Its link is documented in `DATA_DECISIONS.md`.

## Phase-by-phase history

The team finished the vision, the spec plus data, and a working build, then audited the build and found two definition problems.

- **Phase 1 (vision):** wrote three vision docs, picked one, and revised it after feedback (see "How the vision evolved").
- **Phase 2 (spec + data):** deliverables were `BUILD_SPEC.md`, `DATA_DECISIONS.md` with extraction scripts, and `backend/analysis.py`, merged to `main` via PR #12.
    - Reviewer feedback led to five fixes: a metric-definition table tied to the real code, traceable canonical-data documentation (filenames, join keys, checksums), verification of all three deliverables, resolution of two spec conflicts (e.g. "every number from analysis" vs. a row-count KPI), and confirmation that the files were committed.
    - Every claimed number was re-verified against live data before it went into the spec.
    - A thread-safety fix was added to the backend (one DuckDB cursor per call, plus a lock).
    - The spec includes a `BUILD_NOTES.md` rule: any agent building from it must log every guess. This was applied using the prompt-engineer skill.
- **Phase 3 (build):** FastAPI backend wrapping `analysis.py`, plus a frontend with filters, a scatter chart, a sortable table, an artist detail panel, and a CSV-exportable shortlist tray.
    - Tested in a headless browser against the real data and the spec's seven acceptance checks.
    - Fixed two layout bugs (horizontal overflow at narrow widths) and a Python 3.9 type-hint incompatibility.
    - Logged undocumented design choices in `BUILD_NOTES.md`.
- **Module 9 audit (Navya's):** audited the "First release on/after" filter and the growth percentage, using an independent pandas recomputation (`audit/navya_audit_checks.py`) across all 1,131 shortlisted artists. Two issues were logged:
    - **AUDIT-01:** 23 artists had MusicBrainz "first release" dates that postdate when listening data shows an audience, so the field does not reflect true debuts.
    - **AUDIT-02:** the "baseline ≥ 5 listeners" threshold is applied to a 3-month average, so artists with mostly zero months (e.g. 0, 0, 22) can qualify with inflated growth. This affected 53 of 1,131 artists and 10 of the top 25 rows.

## Latest feedback and ideas (Nov 4)

The reviewer found the workflow strong and coherent, and suggested more ways of getting user input. They said metrics, filter scopes, API boundaries and real-data checks are clearly specified.

**Improvement ideas**

- Curator feedback controls ("Not for me / Already know / Interesting" plus reasons).
- Start from seed artists the curator already loves.
- Run 3 to 5 curator walk-throughs.
- A confidence flag for tiny-audience growth, and a "still rising / peaked" tag.
- Junk-name flagging, and real track titles in the detail panel.
- Taste communities as a first-class filter.

**Exploratory-analysis features, in user-friendly form**

- Presets (Breaking out, Steady climbers, Fresh debuts, Hidden gems) with a "Customize" option, plus plain-language sliders.
- A "what changed" toast and an "almost made it" row.
- A "why is this artist here?" sentence in the detail panel.
- Search by an artist you love.
- Lasso a group on the chart and add it all to the shortlist.
- Polish: hover names on the chart, shortlist count in the header, "Unknown" replaced with a dash.

**Suggested priority:** presets plus the "why is this artist here" sentence, because they need no new backend work. Open question: whether any of these were built after Nov 4.

## Lessons to carry into a restart

1. **Ground every claim in verified data.** Check numbers against the live data before writing them into a spec.
2. **Run the fresh-agent test early.** Give a new agent the repo with "Follow BUILD_SPEC.md" and treat every logged guess as a spec gap.
3. **Keep one source of truth for metrics** (`analysis.py`) and a metric-definition table that matches it.
4. **Audit definitions, not just code.** Both audit issues were definition problems.
5. **Check data against the vision before committing to it.** The demographics idea failed because the data could not support it.
6. **Set up the environment first.** The pipeline needed Python 3.13 (not the system 3.9 or 3.15), and the large data download had to be run in your own terminal.



