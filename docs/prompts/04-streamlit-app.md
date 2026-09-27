# Task 4: The Streamlit app (Explorer, Data Quality, About)

## Context
`data/processed/draft_outcomes.parquet` (12,974 rows × 35 columns, one row per pick) and
`data/processed/quality_report.json` are built and committed. This task builds the **public,
self-serve dashboard** a scout or coordinator uses to ask "what's the track record of players like
this?", filtering by school, conference, school type, position, age at draft, draft slot and bonus.
It's the centerpiece of a job application: clarity and correctness beat features.

Read first: `models/07_draft_outcomes.sql` (column meanings), `data/processed/quality_report.json`
(structure), `quality/checks.py`, `reference/schools.csv`, `Makefile`, `pyproject.toml`.

Branch: `git switch -c task-04-app` from `main` after I've merged Task 3. If `main` doesn't
contain `data/processed/draft_outcomes.parquet`, stop and tell me.

IMPORTANT: STAGE all changes (`git add -A`) but DO NOT COMMIT. I commit myself. No
`Co-Authored-By` or any AI/session trailers anywhere.

## Scope

### A. Small reference-data fixes first (from Task 3's findings)
In `reference/schools.csv`, set these rows' `type_source="manual"` so they survive re-runs:
- Junior colleges wrongly aliased to universities: `Mercer County CC`, `Oakland CC`, `Lewis and Clark CC` (and any other `CC`/`Community College` raw name whose canonical is a 4-year school). Give each its own canonical name, `school_type=JC`, `division=JUCO`, blank conferences.
- Siena College and Wagner College: same canonical, type and division as `Siena` and `Wagner` (D1, 4YR, same conferences).
- Groups split between 4YR and OTHER (Eckerd, Rollins, Florida Southern, Menlo, Catawba, Belmont Abbey, Ramapo, Georgia Gwinnett): set every row in each group to `4YR`, keep `division=UNKNOWN`, blank conferences.

In `models/05_int_schools.sql`, rename the `conference_group` value `Non-D1 4-year` to `Other 4-year`. It also contains a few D1 schools the lookup missed, so "Non-D1" would be a false claim. Then run `make build` and confirm no quality check fails.

### B. App structure
- Deps: add `streamlit` and `plotly` with `uv add`. Record the resolved versions in the report.
- `app/Explorer.py` (entry point), `app/pages/1_Data_Quality.py`, `app/pages/2_About.py`.
- `app/lib/data.py`: `load_outcomes()` / `load_quality()` with `st.cache_data`; a pure `apply_filters(df, filters) -> df`, where `filters` is a small dataclass.
- `app/lib/metrics.py`: pure functions. `cohort_summary(df)`, `group_stats(df, by, metric, min_n)`, `wilson_interval(k, n, z=1.645)`, and `takeaway_*()` helpers that return one plain-English sentence.
- `app/lib/charts.py`: Plotly figure builders, one per panel. No Streamlit calls inside, so they're testable.
- `.streamlit/config.toml`: light theme, one accent color (a clear blue such as `#1f5fbf`) for the selected cohort, grey `#9aa0a6` for the baseline. No team logos or trademarks.
- Makefile: `app` = `uv run streamlit run app/Explorer.py`.

### C. Explorer page
**Sidebar filters** (every panel uses them):
- Draft years (range slider, 2012–2025)
- School type, conference group, and school. School is a searchable multiselect whose options narrow to the chosen conference groups.
- Position group, age band, slot band, bonus band
- Toggle "Count unsigned picks" (default **off**; outcome metrics use signed players only)
- Slider "Hit = career WAR of at least ___" (default 5)
- A live count ("1,284 picks match") and a Reset button

**Outcome rule (important):** outcome metrics (MLB %, years to debut, WAR per player, hit rate) use only rows where `outcome_eligible = true`, meaning final-draft rows from 2012–2019. When the year filter includes 2020+, show a small note: "Outcomes use 2012–2019 classes; newer players haven't had time to develop." Draft-side metrics (pick counts, bonus) use every row in the filter.

**Panels, in order.** Each panel gets a one-line dynamic takeaway underneath (e.g. "SEC draftees reached MLB at 29%, vs 18% for all draftees.").
1. **Summary tiles:** picks, signed %, MLB %, median years to debut, WAR per player, and hit %. Show the cohort value with the all-draftee baseline under it.
2. **Compare groups:** horizontal bars, with a *Group by* select (conference group, school, school type, position group, age band, slot band, bonus band) and a *Metric* select (MLB %, WAR per player, hit %, median years to debut, median bonus).
   - Rates get Wilson 90% intervals as error bars. WAR per player gets mean ± 1.645 × standard error.
   - A min-sample slider (default n ≥ 20) hides small groups, with a caption saying how many groups are hidden.
   - Label n on each bar and draw a dashed line at the baseline. Sort by value and show at most 25 bars.
3. **Draft slot curve:** MLB % by `slot_band` for the cohort vs. all draftees (two lines, with intervals on the cohort).
4. **Bonus vs. outcome:** scatter of `bonus_usd` (log x) against `career_war` for outcome-eligible signed rows with a bonus, colored by school type. Hover shows player, school, year, pick, bonus and WAR. Caption: "Bonus data is thin after round 10 for 2012–2016 and 2018–2019."
5. **Trend by draft class:** metric by `draft_year`, one line per selected school or conference (up to 4, chosen in the panel) plus the all-draftee line.
   - Metric options: *Share of picks* (the % of each class matching the selection, all years), *Median bonus* (all years), *MLB %* (2012–2019 only).
6. **Player table:** filtered rows with readable column names, sortable, and a "Download CSV" button.

**Empty state:** if filters match 0 rows (or fewer than 5 outcome-eligible rows), show a friendly message instead of empty or erroring charts.

### D. Data Quality page
- Intro: "Every build runs these checks; a failure stops the pipeline."
- The checks table from `quality_report.json`: name (humanized), status as a colored label, value, threshold, and a detail expander with examples.
- Bonus coverage by year × round band as a heatmap, and school-type mix by year as stacked bars. Use the tables stored in the report.
- A "Known limitations" list. Use exactly these facts, reworded plainly:
  - Conferences use the spring-2024 alignment for 2012–2024 drafts, and earlier realignment isn't modeled.
  - Division reflects current membership.
  - Bonuses after round 10 are sparse for 2012–2016 (Baseball-Reference) and 2018–2019 (MLB $0 placeholders are treated as missing).
  - "Unsigned" in 2018–2019 late rounds really means unsigned or unknown.
  - Position is the player's current listed position, not necessarily his position at the draft.
  - "Other 4-year" mixes D2/D3/NAIA schools and a few unmatched D1 schools.

### E. About page
Short and readable: the question the tool answers; how to use it (3 bullets); definitions (signed, final draft, MLB %, WAR, hit, outcome-eligible); data sources with credit (MLB Stats API; Baseball-Reference for WAR and 2012–2016 bonuses; Wikipedia for conferences and draft dates); the pipeline in one line (Python ingest → DuckDB SQL models → quality checks → Streamlit); the GitHub link `https://github.com/mishareiss/college-draft-explorer`; and "Built by Misha Reiss".

### F. Style rules
Plain-English labels everywhere (never raw column names), percentages with 1 decimal, dollars as `$1.2M` / `$350k`, and consistent colors (accent = selected cohort, grey = baseline). No emojis. Wide layout. Plotly `config={"displayModeBar": False}`.

## Testing (offline and deterministic; keep the suite green)
- `metrics.py`:
  - `wilson_interval` matches known values (e.g. k=18, n=100, z=1.645 → about (0.126, 0.251); verify your expected numbers independently in the test comment).
  - `group_stats` respects `min_n` and returns hidden-group counts.
  - Outcome metrics ignore non-eligible rows even when they're in the filtered frame.
  - The "Count unsigned picks" toggle changes denominators as intended.
  - The takeaway text for a known small frame.
- `data.apply_filters`: each filter narrows correctly; an empty selection means "all"; school options narrow by conference.
- `charts.py`: each builder returns a `go.Figure` with the expected number of traces on a small frame, and handles an empty frame without raising.
- **Page smoke tests with `streamlit.testing.v1.AppTest`:** each of the 3 pages runs without exceptions with default filters; the Explorer with a filter that matches nothing shows the empty-state message and no exception.
- Use a small fixture parquet (~40 rows) via an env var or parameter, so tests don't depend on the full file.

## Constraints
- Charts read only `draft_outcomes.parquet` and `quality_report.json`. No network, no DuckDB at runtime (pandas is fine).
- Keep business definitions in `metrics.py`, not scattered through page code.
- Page load under ~2 s locally (cache the load; no per-rerun heavy work).
- Don't change the SQL beyond the one rename in scope A.

## Acceptance criteria
1. `make build` then `make app` runs locally, and all 3 pages render with real data.
2. Changing any filter updates every Explorer panel. The empty state works.
3. `make lint` and `make test` pass, with no network in tests.
4. On branch `task-04-app`: all staged, nothing committed. `reference/schools.csv` and the rebuilt processed files are staged.

## Report back with
- `git status --short` and the branch; resolved `streamlit` / `plotly` versions
- The quality check list after the rebuild (any status changes vs. Task 3)
- **Screenshots** of the Explorer (default filters), the Explorer filtered to SEC + 4-year college + RHP, the Data Quality page, and the About page, saved to `docs/screenshots/` (staged)
- The takeaway sentences shown under each panel for the SEC + RHP filter
- The Wilson test values and how you verified them
- Deviations and why; anything to fix before deploy (Task 5)

Reminder: STAGE with `git add -A`, DO NOT COMMIT, and no AI attribution anywhere.
