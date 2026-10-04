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

- **Branch:** `navya` | **Branch URL:** https://github.com/kunjeshgupta/dso576_project/tree/navya | **Commit ID:** [fill in after committing: `git rev-parse HEAD`]
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
