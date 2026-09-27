# Task 3: Build `draft_outcomes` with SQL models and quality checks

## Context
Tasks 1–2 produced the interim sources in `data/interim/` (`draft_picks`, `people`, `war_bat`,
`war_pitch`, `bbref_draft`, `bonus_backfill`) and `reference/schools.csv`. This task turns them
into **one analysis table the dashboard reads**, `data/processed/draft_outcomes.parquet`, with one
row per draft pick, and adds the pipeline's quality checks. There's no Streamlit yet (Task 4).

The whole transform is **SQL run in DuckDB**. The hiring team wants "SQL for data work, Python for
analysis", so keep business logic in `.sql` files, not pandas.

Read first: `docs/DATA_PROFILE.md` (all "Notes" sections), `reference/schools.csv`,
`reference/conference_moves_2024.csv`, `ingest/build_bonus_backfill.py`, `ingest/paths.py`, `Makefile`.

Branch: `git switch -c task-03-models` from `main` after I've merged Task 2. If `main` doesn't
contain `reference/schools.csv`, stop and tell me.

IMPORTANT: STAGE all changes (`git add -A`) but DO NOT COMMIT. I commit myself. No
`Co-Authored-By` or any AI/session trailers anywhere.

## Scope

### 1. Layout and runner
- `models/` holds numbered SQL files run in order: `01_stg_picks.sql`, `02_stg_people.sql`, `03_stg_war.sql`, `04_stg_bonus.sql`, `05_int_schools.sql`, `06_int_final_draft.sql`, `07_draft_outcomes.sql`. Each creates one view or table. Use CTEs. Comment the header of each file with its grain and purpose.
- `transform/run.py`: open an in-memory DuckDB, register the interim parquet files and reference CSVs as views, execute `models/*.sql` in order, write `data/processed/draft_outcomes.parquet`. Keep it short.
- `reference/draft_dates.csv`: `draft_year, draft_start_date, source_url`. Take each date from the Wikipedia page "{year} Major League Baseball draft" (fetch via `ingest/http.py`, cached). Don't fill dates from memory.
- `.gitignore`: **commit** `data/processed/draft_outcomes.parquet` and `data/processed/quality_report.json`. Streamlit Cloud needs them, and they're small. Raw and interim stay ignored.
- Makefile: `transform`, `quality`, and `build` (= transform, then quality).

### 2. Business rules (implement exactly; each goes in the SQL file it belongs to)
**Bonus** (`04_stg_bonus.sql`)
- 2012–2016: Baseball-Reference bonus. Accept rows where `name_mismatch = false`, **or** `same_last_name_initial = true` (the ~60 nickname cases, which I reviewed).
- 2017+: MLB `signing_bonus_usd`. **Treat MLB `0` as missing** (placeholders concentrated in rounds 35–40). If the MLB value is missing in 2017, fall back to Baseball-Reference.
- `$125,000` is **real**, not a placeholder: it's the CBA cap for picks after round 10 before a bonus counts against the pool. Keep it. Say so in a SQL comment.
- `bonus_source`: `mlb` | `bbref` | null.
- Slot value = MLB `pick_value` cast to number, with `0` → null. `bonus_vs_slot = bonus / slot`, only where both exist. Bands: `under slot` (<0.95), `at slot` (0.95–1.05), `over slot` (>1.05).

**Signed and final draft** (`06_int_final_draft.sql`)
- `is_final_draft`: the row with the latest `draft_year` for that `person_id`.
- `signed`: false if not the final draft (the player went back to school and was redrafted). Otherwise true if any of: Baseball-Reference `signed = true` (2012–2017); bonus > 0; an MLB debut exists. Else false.
- Outcomes (below) are credited **only on final-draft rows**; earlier rows get null outcomes.

**School** (`05_int_schools.sql`)
- `school_type`: `High school` when the school name matches the HS rules from Task 2 (name regex, school-class prefix `HS`, or Baseball-Reference `from_type = HS`). Else from `schools.csv` (`4YR` → `4-year college`, `JC` → `Junior college`, `OTHER` → `Unknown`). Else `Unknown`.
- `school` = `school_canonical` for colleges; the raw name for high schools.
- `conference`: for draft years ≤ 2024 use `conference_pre2024`; for 2025 use `conference_2024`. That column pair is really the spring-2024 vs. spring-2025 alignments, and draftees play the spring before the draft. Comment this in the SQL.
- `conference_group` for filters: the D1 conference name; else `Non-D1 4-year`, `Junior college`, `High school`, `Unknown`.
- `division` passed through.

**Player dimensions** (`07_draft_outcomes.sql`)
- `age_at_draft` = years between `birth_date` and `draft_start_date` (1 decimal). Band: `≤18`, `19`, `20`, `21`, `22`, `23+`.
- `position_group`: `P` split into `RHP`/`LHP` by pitch hand; `C`; `1B/3B`; `2B/SS`; `OF` (LF/CF/RF/OF); else `Other`. Keep the raw position.
- `slot_band` by overall pick: `1–10`, `11–30`, `31–100`, `101–300`, `301+`.
- `round_band`: `1–5`, `6–10`, `11–20`, `21+`, `Supplemental` (match `profile.py`'s definition).
- `bonus_band`: `<$100k`, `$100k–$500k`, `$500k–$1M`, `$1M–$3M`, `$3M+`, `Unsigned`, `Unknown`.

**Outcomes** (final-draft rows only)
- `reached_mlb` = `mlb_debut_date` is not null. `years_to_debut` = (debut − draft start date) in years, 1 decimal.
- `career_war` = sum of `WAR` from `war_bat` + sum of `WAR` from `war_pitch` by `mlb_ID`, through 2026. Verify the column names first. A player who never debuted gets 0.0 WAR, with `reached_mlb = false`.
- `outcome_eligible` = `draft_year BETWEEN 2012 AND 2019 AND is_final_draft`. The app uses this to keep young classes out of outcome views.

Keep all identifying columns: `draft_year`, `pick_number`, `round_label`, `team_name`, `person_id`, `player_name`, `school_name_raw`.

### 3. Quality checks: `quality/checks.py` → `data/processed/quality_report.json`
Each check returns `{name, category, status: pass|warn|fail, value, threshold, detail}`. `make quality` exits non-zero if any **fail**.

| Check | Rule | Level |
|---|---|---|
| Row count | equals the `draft_picks` row count (no rows gained or lost in joins) | fail |
| Uniqueness | `(draft_year, pick_number)` unique; exactly one `is_final_draft` row per `person_id` | fail |
| Year completeness | every year 2012–2025 present; max numeric round 40 / 5 (2020) / 20 (2021+) | fail |
| People join | 100% of rows have `birth_date` | fail below 99% |
| WAR join | ≥99% of debuted players have a WAR match | fail |
| Valid ranges | `age_at_draft` 16–26; bonus 0–15M; debut after draft date | warn, and list offending rows (≤20) |
| Bonus coverage | % with bonus by year × round band | warn if rounds 1–10 < 90% in any year |
| School mapping | % of college picks with a D1 conference; `Unknown` school type share | warn if `Unknown` > 5% |
| Signed logic | no non-final-draft row is `signed`; every debuted player is `signed` | fail |

Also store the tables the Data Quality page will show in `quality_report.json`: bonus coverage by year × round band, and the school-type mix by year.

## Testing (offline and deterministic)
- **Model tests on a tiny synthetic dataset:** build ~15 handcrafted rows as parquet/CSV fixtures under `tests/fixtures/models/` and run the real SQL files against them. Assert:
  - A redrafted player: only the final row is `is_final_draft`, the earlier row is unsigned with null outcomes, and outcomes appear once.
  - Bonus: MLB 0 → null; a 2017 missing MLB value falls back to Baseball-Reference; a nickname mismatch with `same_last_name_initial` is accepted; a real mismatch is rejected; $125,000 is kept.
  - Conference switch: an Oregon row drafted in 2024 gets `Pac-12`, and the same school in 2025 gets `Big Ten`.
  - HS detection and `conference_group` values; position group for an LHP and a CF; age at draft using `draft_dates.csv`; band edges (pick 10 vs. 11, bonus exactly $100k).
  - `career_war` sums bat + pitch; a non-debuted player gets 0.0 and `reached_mlb = false`.
- **Check tests:** each check returns `fail` on a deliberately broken input (a duplicate pick, a lost row, a signed non-final row).
- **Processed-data test:** if `data/processed/draft_outcomes.parquet` exists (it's committed, so CI has it), run the checks against it and assert no `fail`.
- Keep all existing tests green.

## Constraints
- Business logic in SQL. Python only for orchestration and checks.
- No new heavy dependencies (DuckDB and pandas are enough).
- Don't change `ingest/` outputs or `schools.csv`. If you find a reference-data error, list it in the report instead of editing.
- Never invent data: draft dates come from cached Wikipedia pages with the source URL recorded.

## Acceptance criteria
1. `make build` succeeds from existing interim data and writes both processed files. `make quality` reports no `fail`.
2. `make lint` and `make test` pass, with no network in tests.
3. `draft_outcomes.parquet` row count equals `draft_picks`.
4. On branch `task-03-models`: all staged, nothing committed. The processed parquet and JSON are staged; nothing from `data/raw` or `data/interim` is.

## Report back with
- `git status --short` and the branch
- The full `quality_report.json` check list (name, status, value)
- A sanity table for **outcome-eligible final-draft rows (2012–2019)**, grouped by `school_type`: n, signed %, MLB %, median years to debut, WAR per player
- The same grouped by `slot_band`
- Top 10 D1 conferences by MLB % (with n)
- Computed `career_war`, `reached_mlb`, `age_at_draft` and `bonus` for: Aaron Judge (2013), Carlos Correa (2012), Alex Bregman (2015), Paul Skenes (2023)
- `draft_dates.csv` contents
- Deviations and why; anything to flag for Task 4 (the app)

Reminder: STAGE with `git add -A`, DO NOT COMMIT, and no AI attribution anywhere.
