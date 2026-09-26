# Task 1: Scaffold the repo and pull the raw data

## Context
`college-draft-explorer` is a portfolio project: a Streamlit dashboard showing how MLB draftees'
outcomes (reached MLB, years to debut, career WAR) vary by school, conference, school type,
position, age at draft, draft slot and signing bonus. It covers draft classes 2012–2025.

This task builds **only the foundation**: repo scaffold, three ingestion scripts that cache raw
data, and a data-profile report. The report tells us which fields actually exist and how complete
they are, so Task 2 (SQL models + quality checks) can be designed from real data rather than guesses.
No SQL models, no dashboard yet.

The repo directory already exists at `~/Documents/Portfolio/college-draft-explorer` and contains
only `docs/prompts/` (this file). Run `git init -b main` there.

IMPORTANT: STAGE all changes (`git add -A`) but DO NOT COMMIT. I commit myself. Never add
`Co-Authored-By` or any AI/session trailers anywhere.

## Stack (use exactly these)
- Python 3.12, dependency management with **uv** (`pyproject.toml` + `uv.lock`)
- Runtime deps: `requests`, `pandas`, `pyarrow`, `duckdb`, `pybaseball`
- Dev deps: `pytest`, `ruff`
- No Streamlit/Plotly yet (Task 3)

## Scope

1. **Scaffold**
   - Layout: `ingest/` (package), `tests/` (with `fixtures/`), `data/raw/`, `data/interim/`, `docs/`
   - `.gitignore`: ignore `data/raw/` and `data/interim/`, `.venv`, caches. Add a `.gitkeep` in each data dir.
   - `Makefile` targets: `setup` (uv sync), `pull` (all three pulls in order), `profile`, `test`, `lint` (ruff check + format --check).
   - A short `README.md`: one-paragraph purpose, setup, `make pull && make profile`.

2. **`ingest/http.py`**: shared helper, one place for all network access
   - A `requests.Session` with a descriptive User-Agent, 30 s timeout, retry with exponential backoff on 429/5xx (max 5), and a polite delay (≥0.5 s between calls).
   - `fetch_json_cached(url, path, force=False)`: if `path` exists and not `force`, load it and make **no** HTTP call; otherwise fetch, write the response verbatim, return it.

3. **`ingest/pull_draft.py`**: MLB Stats API draft endpoint
   - For each year 2012–2025: `GET https://statsapi.mlb.com/api/v1/draft/{year}` → `data/raw/draft/{year}.json` (verbatim, cached).
   - Flatten `drafts.rounds[].picks[]` to **one row per pick** in `data/interim/draft_picks.parquet`. Use `pd.json_normalize` and **keep every field** (dotted names → snake_case). Also add `draft_year`.
   - Add a parsed numeric `signing_bonus_usd` (float, NaN if missing). The raw value may be a number or a string like `"$1,250,000"`; handle both and keep the raw column.
   - Do not drop any picks (compensatory, competitive-balance, unsigned). Keep `pickType`-style fields as-is.
   - CLI: `--years 2012-2025` (default), `--force`.

4. **`ingest/pull_people.py`**: bios and debut dates
   - Unique person IDs from `draft_picks.parquet` → `GET https://statsapi.mlb.com/api/v1/people?personIds=<comma list>` in batches of 100 → raw batches in `data/raw/people/batch_NNN.json` (cached).
   - Flatten to `data/interim/people.parquet`, keeping every field. At minimum confirm `id`, `fullName`, `birthDate`, `mlbDebutDate`, `primaryPosition`, `birthCountry`, `batSide`, `pitchHand` when present.
   - Log (don't fail) any IDs the endpoint didn't return, and write them to `data/interim/people_missing_ids.csv`.

5. **`ingest/pull_war.py`**: Baseball-Reference WAR via pybaseball
   - `pybaseball.bwar_bat(return_all=True)` and `bwar_pitch(return_all=True)` → raw CSVs in `data/raw/war/` (cached) → `data/interim/war_bat.parquet`, `war_pitch.parquet`.
   - Confirm the MLBAM ID column (expected `mlb_ID`) exists and say so in the report. If the download fails (403/rate limit), exit non-zero with a clear message. **Do not** substitute another source without telling me.

6. **`ingest/profile.py`** → writes `docs/DATA_PROFILE.md`. This is the key output. Include:
   - Picks per year and max round per year (2020 should be 5 rounds; 2021+ should be 20).
   - For each flattened draft column: overall % non-null, and per-year % non-null for the fields that matter (`signing_bonus_usd`, any pick/slot value field, any birth-date field, school name, school class/level, school state, position).
   - Bonus coverage by round band (1–5, 6–10, 11–20, 21+) × year.
   - Distinct values + counts for school class/level and position fields; 25 sample school names.
   - People: % with `birthDate` and % with `mlbDebutDate`, by draft year.
   - WAR: of people with an `mlbDebutDate`, % found in WAR data by MLBAM ID.
   - **Repeat draftees:** count of person IDs drafted more than once (e.g. drafted from high school, went to college, drafted again), with 5 examples. Task 2 has to decide which draft row counts.
   - A 10-line "Notes for Task 2" section listing surprises (missing fields, odd encodings, gaps).

## Landmines
- **Network:** all MLB and bbref calls must run from this Mac's normal network. If `statsapi.mlb.com` or baseball-reference.com is unreachable, **stop and report the exact error**. Never fabricate or hand-write data to fill gaps.
- Field names in the draft JSON are not fully documented. Discover them from the real response; don't assume `signingBonus`, `pickValue` or `person.birthDate` exist.
- The same person can appear in several draft years. Don't dedupe in this task; just measure it.

## Testing
- Offline and deterministic: no network in the default test run. Any live test gets `@pytest.mark.live`, deselected by default in `pyproject.toml`.
- Fixtures: after the first real pull, save small trimmed real samples: 1 draft-year JSON cut to ~4 picks (include one with no bonus if one exists), 1 people batch cut to ~3 people (include one with no `mlbDebutDate`), and ~10 rows of each WAR CSV.
- Tests to write:
  - Draft flatten: one row per pick, `draft_year` set, `signing_bonus_usd` parsed for numeric, `"$1,250,000"`-style and missing inputs.
  - A pick missing optional nested fields flattens without error.
  - People batching: 250 IDs → 3 requests of ≤100 (mock the session).
  - Cache: when the raw file exists, `fetch_json_cached` makes zero HTTP calls; `force=True` makes one.
  - Profile runs end-to-end on fixtures and writes a Markdown file containing the expected section headers.
- CI: `.github/workflows/ci.yml` running `make lint` and `make test` on push and PR. Pin action versions only after checking the real published tags (`git ls-remote --tags https://github.com/actions/checkout` and the same for `astral-sh/setup-uv`). Don't guess at versions.

## Constraints
- All HTTP goes through `ingest/http.py`. Don't create other sessions.
- No secrets and no `.env` are needed.
- Raw data never gets committed; only code, fixtures and `docs/DATA_PROFILE.md`.
- Keep it small and readable: this repo is a work sample a hiring manager will open.

## Acceptance criteria
1. `make setup && make pull && make profile` runs cleanly on this Mac. The second `make pull` makes no network calls because everything is cached.
2. `data/interim/` holds `draft_picks.parquet`, `people.parquet`, `war_bat.parquet`, `war_pitch.parquet`.
3. `docs/DATA_PROFILE.md` exists with every section listed in scope item 6.
4. `make test` and `make lint` pass, with no network during tests.
5. `git status` shows everything staged, nothing committed, and no files under `data/raw` or `data/interim` staged.

## Report back with
- File tree (excluding `data/` and `.venv`) and `git status --short`, confirming staged, not committed
- The full contents of `docs/DATA_PROFILE.md`
- One flattened draft pick row as JSON (a first-rounder from a college)
- Picks per year, people coverage %, WAR match %, repeat-draftee count
- The action versions you pinned and how you verified them
- Any deviations from this brief and why
- Anything you'd flag for Task 2

Reminder: STAGE with `git add -A`, DO NOT COMMIT, and no AI attribution anywhere.
