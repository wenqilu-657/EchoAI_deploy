# EchoAI — Emerging Artist Discovery Dashboard (USC MSBA DSO 576)

[![Tests](https://img.shields.io/badge/tests-11%20passed-10b981?style=flat-square)](file:///Users/kunjeshgupta/Documents/USC%20MSBA/dso576/dso576_project/tests/test_analysis_and_api.py)
[![Data Cleaning](https://img.shields.io/badge/cleaning%20audit-verified-10b981?style=flat-square)](file:///Users/kunjeshgupta/Documents/USC%20MSBA/dso576/dso576_project/output/cleaning_replication_report.json)
[![UI Design](https://img.shields.io/badge/design-swiss%20minimalist-0b0d10?style=flat-square)](file:///Users/kunjeshgupta/Documents/USC%20MSBA/dso576/dso576_project/web/styles.css)

An intelligence suite designed for editorial playlist curators at streaming platforms (Spotify, Apple Music) and independent tastemakers. Built on **MusicBrainz metadata** and **ListenBrainz scrobbles (March–August 2026)** to identify breakout talent before mainstream algorithmic saturation.

---

## ⚡ 1-Command Local Startup

Clone the repository and run:

```bash
# Option A: Native Python (recommended)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py

# Option B: Node / npm
npm start
```

The application will automatically initialize the DuckDB in-memory analytical engine and open `http://localhost:8000` in your default browser.

---

## 🎯 What is an "Emerging Artist"?

Traditional discovery relies solely on raw stream counts, which biases toward established viral hits. EchoAI identifies emerging acts using a rigorous, multi-factor analytical gate:

1. **Size Ceiling ($p_{90}$ Percentile):** Monthly listeners must remain below the 90th percentile of scored acts ($\le 87.3$ listeners/month canonical; $\le 298.0$ in sample), filtering out established stars.
2. **Growth Velocity ($p_{90}$ Percentile):** Audience growth between the baseline window (Mar–May 2026) and recent window (Jun–Aug 2026) must exceed the 90th percentile ($\ge +28.1\%$ canonical; $\ge +407.1\%$ in sample).
3. **Activity Floor:** Minimum $\ge 5$ average monthly listeners during the baseline window, with verified active listening in at least 2 distinct baseline months (eliminating "one-month flash" anomalies).

### Key Advanced Telemetry & Analytics:
* **Stickiness Ratio (`listens / listeners`):** Measures repeat listening depth. High stickiness ($>3.0\times$) indicates fan loyalty rather than passive autoplay.
* **Audience Retention (`avg_months_active / 6`):** How consistently scrobblers return across the 6-month observation window.
* **Catalog Depth / Track Dependency (`top_track / total`):** Identifies whether growth is concentrated in a single viral track ($>65\%$) or spread across an artist's full discography (deep catalog).
* **Taste Community Overlap (`share_of_fans`):** Solves cold-start sparse genre tags by calculating co-listening overlap with established benchmark acts (e.g. *BTS, Radiohead, Taylor Swift*).

---

## 🛠️ Reproducibility & Auditing

The grading instructor can verify the entire data cleaning and analytical engine with zero external setup:

```bash
# 1. Run the canonical data cleaning replication audit (Rules R1-R12)
python scripts/clean_data.py

# 2. Run the feature & threshold audit checks
python audit/kunjesh_audit_checks.py

# 3. Run the automated unit & integration test suite (11 tests)
python -m unittest discover tests
```

---

## ☁️ Deploy to Vercel

The project includes serverless Python handlers (`api/index.py` and `vercel.json`) ready for one-click deployment:

```bash
# Deploy with Vercel CLI
npx vercel
```

---

# Module 3 Project Starter

Use this repository to investigate two candidate project Visions, combine the
team's evidence, and record a provisional starting point. The files are
scaffolds: replace the bracketed prompts with your team's own checked work.

## Start here

1. Choose one project area as a team.
2. Write two distinct candidate Vision statements in `project-start.md`.
3. Copy the same area and candidate statements to the top of every assigned
   role file.
4. Assign one role file to each teammate:

   - `objectives.md`
   - `alternatives.md`
   - `data-fit.md`
   - `auxiliary.md`
   - `technical.md`
   - `objections.md` - only for teams of six

5. Each teammate investigates both candidate Visions in their assigned file.
6. Reconvene and synthesize the team's evidence in `project-start.md`.
7. Put every teammate's GitHub username on its own line in `members.md`.

Do not force a final project choice in Module 3. Preserve the real questions
that the team still needs to answer.

## Required files

| File | Owner | Main question |
|---|---|---|
| `members.md` | coordinator | Who needs access to the private team repository? |
| `project-start.md` | coordinator, reviewed by everyone | What provisional starting point did the team establish? |
| `objectives.md` | Role 1 | What matters when this person makes the decision? |
| `alternatives.md` | Role 2 | How might the person make the decision today? |
| `data-fit.md` | Role 3 | What can the core data honestly support? |
| `auxiliary.md` | Role 4 | What decision-important input is missing? |
| `technical.md` | Role 5 | Can the team access and work with a promising source? |
| `objections.md` | Role 6, teams of six only | What could block trust, adoption, or action? |

## Evidence rules

- Separate sourced facts from AI-generated hypotheses.
- Link original sources for factual claims.
- Record what you checked and what remains uncertain.
- Do not claim the actual organization follows a process unless you verified it.
- Do not claim the data supports something that was not observed.
- Do not commit downloaded data, credentials, `.env` files, or private data.

## Safe Git contribution sequence

1. Pull the latest team work before beginning.
2. Edit only your assigned Markdown file.
3. Review `git status` and your file diff.
4. Commit with a clear message.
5. Pull again if a teammate may have pushed.
6. Resolve any conflict deliberately, then push one person at a time.

The coordinator commits `project-start.md` once. Other teammates should review
and contribute to its wording without creating competing copies.

## Pandas quiz tutor

Open a coding-agent session in this repository and say:

> Read `tutor.md` and tutor me for the Module 3 Pandas quiz.

The tutor generates difficult, one-at-a-time tracing questions covering the
Module 1–3 Pandas vocabulary, including `.loc`, `.iloc`, filtering, sorting,
cleaning, summaries, typed functions, and `.map()`. It deliberately excludes
`groupby` and later-course shortcuts.

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
