# Task 7: Front-office redesign of the Explorer

## Context
Task 6 added an expected-by-pick model and outcome tiers to `draft_outcomes.parquet`, plus
`slot_expectation.parquet`. A front-office review of the app found the charts hard to read and
the takeaways easy to misread. This task redesigns the Explorer around the questions a GM or
scouting director actually asks, and uses the new slot-adjusted metrics throughout. The app is a
job-application work sample: **clarity beats features**. It's also due tonight, so follow the cut
order at the end if you run long.

New columns (from Task 6): `outcome_tier`, `outcome_tier_order` (a float in pandas because it has
nulls; cast before sorting), `became_regular`, `exp_mlb_signed`, `exp_mlb_all`,
`exp_regular_signed`, `exp_regular_all`, `mlb_minus_exp`, `regular_minus_exp`. The curve is in
`data/processed/slot_expectation.parquet` (picks 1–1,238). The quality report has new
`tables.outcome_tier_mix_by_year` and `tables.slot_model`.

Read first: `app/Explorer.py`, `app/lib/{data,metrics,charts,schema,ui,fmt}.py`, `app/pages/*`,
`tests/test_app_*.py`, `tests/app_fixture.py`, `transform/slot_model.py` (docstring),
`models/08_outcome_tiers.sql`, `README.md`.

Branch: `git switch -c task-07-app-redesign` from `main` after I've merged Task 6.

IMPORTANT: STAGE all changes (`git add -A`) but DO NOT COMMIT OR PUSH. I commit myself. No
`Co-Authored-By` or any AI/session trailers anywhere.

## Global rules (apply everywhere)
- **Color system** (define once in a new `app/lib/theme.py`, used by every chart):
  - Selected cohort = blue `#1f5fbf`; baseline / all draftees = grey `#9aa0a6`; "below baseline" highlight = orange `#d9822b`; "about the same" = grey `#9aa0a6`. **No red/green anywhere.**
  - Tier palette (ordinal, light to dark): Didn't sign `#e3e6ea`, Never reached MLB `#b8bec6`, Cup of coffee `#c6d9f1`, Role player `#8fb3e3`, Regular `#4a82cf`, Star `#1f4f99`.
- **Charts:**
  - White plot background, light horizontal gridlines only, 13–14px fonts, and direct labels instead of legends wherever possible.
  - Plotly `displayModeBar` off.
- **Headings:** every panel's heading is a **data-generated takeaway sentence**, with a small caption underneath saying what the chart shows. For example, heading: "SEC right-handers reached MLB 3 points more often than their draft slots predict"; caption: "Reached MLB vs. expected for their picks, 2012–2019 signed players, 90% intervals".
- **Significance rule:** for any difference (vs. baseline or vs. slot), if the 90% interval includes zero, show it in grey and describe it as "about the same". Only intervals clear of zero get blue (above) or orange (below). Put this rule in one helper in `metrics.py` and use it everywhere.
- **Slot-adjusted rate for a group:** mean of `mlb_minus_exp` (or `regular_minus_exp`) over outcome-eligible signed rows, in percentage points, with the interval ±1.645·sd/√n.
  - When "Count unsigned picks" is on, use outcome-eligible rows and `reached_mlb.fillna(False) - exp_mlb_all` (and the regular equivalent with `exp_regular_all`).
  - One function in `metrics.py`, unit-tested.
- **Language:** use exactly these terms everywhere (tiles, charts, table headers, tooltips). Define each once in `schema.py`.

  | Say | Instead of |
  | --- | --- |
  | "Reached the majors" | MLB % |
  | "Became a regular (5+ WAR)" | Hit % |
  | "vs. draft slot" | slot-adjusted |
  | "Signed for" | bonus |
  | "Picked at" | pick |
  | "Draft class" | draft year |
- **Remove the hit-threshold slider.** Tiers replace it; "regular" is fixed at 5+ WAR.

## Scope

### 1. Layout and sidebar
- **Above the tabs:**
  - The title
  - A "How to read this" expander (collapsed) with 4 short steps
  - **Preset chips** (`st.pills` or buttons)
  - The **cohort sentence**. Generate it from the filters, e.g. "207 signed right-handed pitchers from SEC schools, drafted 2012–2019 (439 picks, 2012–2025)."
- **Tabs:** **Overview · Rankings · Draft slot · Money · Trends · Players**. The sidebar filters drive every tab.
- **Sidebar sections:**
  - **Player:** school type, conference, school (searchable, narrowed by the choices above), position group, age at draft
  - **Draft:** draft class range, **pick range slider (1–1,238)** replacing the slot-band multiselect, signing bonus band
  - **Settings** (an expander, collapsed): "Count unsigned picks"
  - The live count and Reset stay.
- **Presets** (each sets the filters exactly as listed and clears the rest):

  | Preset | Filters |
  | --- | --- |
  | SEC college arms | 4-year college + Southeastern + RHP, LHP |
  | Prep shortstops | High school + 2B/SS |
  | JUCO bats | Junior college + all non-pitcher groups |
  | Top-100 college hitters | 4-year college + picks 1–100 + non-pitcher groups |
  | $1M+ high schoolers | High school + bonus bands $1M–$3M and $3M+ |
- **Shareable URLs:** mirror every filter to `st.query_params`, and read them on load. Round-trip must be exact.

### 2. Overview tab
- **Five tiles.** Each shows a label, a big value, and a delta line colored by the significance rule.

  | Tile | Value | Delta line |
  | --- | --- | --- |
  | Players | picks in filter | "(N with outcomes)" |
  | Signed | % | vs. all draftees, same classes |
  | Reached the majors | % | vs. all draftees |
  | vs. draft slot | ±pts | "vs. expected for their picks" |
  | Became a regular (5+ WAR) | % | vs. all draftees |
- **Outcome distribution:** two horizontal 100% stacked bars, **"This group"** above **"All draftees"** (same classes), segmented by tier with the tier palette.
  - Label a segment's percentage when it's at least 4%. Put a single tier key under the chart.
  - Show "Didn't sign" only when "Count unsigned picks" is on; otherwise renormalize without it.
  - Heading example: "12% of this group became regulars or better, vs 2.4% of all draftees."

### 3. Rankings tab (replaces Compare groups)
- **Dot plot:** a dot for the value, a thin line for the 90% interval, a dashed reference line (0 for vs-slot metrics, the all-draftee value otherwise), and the value labeled beside each dot.
- **Coloring** by the significance rule.
- **n** in a separate right-aligned column of small grey numbers.
- **Metric select:**
  - "Reached the majors vs. draft slot" (default)
  - "Became a regular vs. draft slot"
  - "Reached the majors %"
  - "Became a regular %"
  - "Median signing bonus"
- **Group-by select:** Conference (D1 only), School type, School, Position group, Age at draft, Round range, Signing bonus band.
  - When Round range is selected, disable the vs-slot metrics (they're ≈0 by construction) with a one-line note.
- **Hide "No school / unclassified"** (rename the `Unknown` group label to this) by default, with a checkbox to show it.
- **Size rules:** keep the min-sample slider (default 20) and the top-12 / bottom-12 rule when there are more than 25 groups.

### 4. Draft slot tab (two stacked panels, shared x-axis)
- **Top panel:** "Chance of reaching the majors by pick".
  - x = pick on a log axis, with ticks at 1, 3, 10, 30, 100, 300 and 1,000.
  - A grey line for the expected curve from `slot_expectation.parquet`: `exp_mlb_signed`, or `exp_mlb_all` when unsigned picks are counted.
  - Blue dots with Wilson 90% intervals for the cohort, in ranges 1–10, 11–20, 21–30, 31–50, 51–75, 76–100, 101–150, 151–200, 201–300, 301–500, 501+. Plot each dot at its range's median pick.
  - With no filters, draw the dots in grey (all draftees vs. the model, as a visible fit check).
- **Bottom panel:** "Above or below expected".
  - Bars per range showing the cohort's mean vs-slot in points, colored by the significance rule, with n under each bar.
  - Hide ranges with n < 10, and caption how many were hidden.

### 5. Money tab
- **Toggle:** "What each bonus bought" (default) / "Over or under slot".
- **What each bonus bought:** one 100% stacked tier bar per bonus band, for outcome-eligible signed rows with a known bonus.
  - Put a thin grey all-draftee reference bar under each band, with n at the right.
  - Grey out bars with n < 20.
- **Over or under slot:** the same chart by `bonus_vs_slot_band`, for 2017–2019 rounds 1–10 with both values. Caption the small sample.
- **Coverage line on both views:** "Signing bonus known for X% of this group's picks."
- **Individual players:** keep the existing scatter behind a "Show individual players" toggle, and add a player search that highlights that player's dot.

### 6. Trends tab
- **"Top 5 rounds only" toggle,** on by default. It keeps picks through the last pick of round 5 in each draft class, supplemental picks included; derive it from `round_number` and `pick_number`.
- **Rule-change markers:** vertical lines labeled at 2020 ("5-round draft") and 2021 ("20 rounds").
- **Metrics:**
  - Share of picks (2012–2025)
  - Median signing bonus (2012–2025)
  - Reached the majors % (2012–2019)
  - vs. draft slot (2012–2019)

  Outcome lines stop at 2019, with an end label "Later classes still developing".
- **Lines:** up to 4 schools or conferences, plus grey "All draftees". Label them at the line ends; no legend.

### 7. Players tab
- **Strip above the table:**
  - **Top producers:** the cohort's 5 highest career WAR.
  - **Biggest misses:** its 5 highest-bonus signed, outcome-eligible players who never reached MLB.

  Each shows name, pick, bonus and WAR.
- **Table:**
  - Default sort by career WAR, descending.
  - Columns in this order: Player (a `LinkColumn` to `https://www.mlb.com/player/{person_id}`), Draft class, Picked at, Round, Team (current name), School, Conference / school type, Position, Age at draft, Signed for, vs. slot value, Outcome tier, Debut year, Career WAR.
  - Drop Division and the raw school name from view.
  - The CSV download keeps every column.

### 8. Data Quality and About pages
- **Data Quality:**
  - Add `CHECK_LABELS` entries for the 4 new checks.
  - Add a small **calibration chart**: expected vs. observed by decile, from `tables.slot_model`, with a y = x line.
  - Add the **tier mix by class** as stacked bars.
  - Add limitation bullets: tiers are lenient for 2018–2019; the expected-by-pick model is fit on 2012–2019 and reused for later classes.
- **About:** add definitions for outcome tiers and "vs. draft slot" (one plain sentence on the model), and apply the new vocabulary throughout.

### 9. README and screenshots
- **Screenshots:** retake them into `docs/screenshots/` at 1440px wide:
  - `overview-sec-arms.png` (the SEC college arms preset): **the new README hero**
  - `rankings-default.png`
  - `draft-slot-sec-arms.png`
  - `money-default.png`
  - `trends-default.png`
  - `players-sec-arms.png`
  - `data-quality.png`
  - `about.png`

  Delete the obsolete screenshots.
- **README:** update the image references and the "What you can do in the app" bullets to match. Leave "Three findings" as written in Task 6.

## Testing (offline and deterministic; keep the suite green)
- **metrics:**
  - The vs-slot group function gives the correct mean and interval on a hand-built frame, with both signed-only and count-unsigned variants.
  - The significance helper gives the right color and label at interval edges.
  - The tier distribution sums to 100 and renormalizes without "Didn't sign".
  - The top-producers / biggest-misses selection is correct.
- **data:**
  - The pick-range filter works at its edges.
  - Each preset maps to its exact filters.
  - Query params round-trip every filter.
  - The top-5-rounds rule keeps supplemental picks inside round 5 and drops the first pick of round 6.
- **charts:** each new builder returns a figure with the expected traces on the fixture and handles an empty frame; the dot plot colors follow the significance rule.
- **AppTest:**
  - Every tab renders with default filters and with each preset.
  - The empty state shows on a no-match filter.
  - Choosing Round range disables the vs-slot metrics.
  - A URL with query params loads those filters.
- **Performance:** a cold AppTest of the Explorer finishes under 3 s. Report the time.

## Constraints
- Business definitions in `metrics.py` and `schema.py`, not scattered through page code. Keep page files readable.
- No new dependencies unless unavoidable; say why if you add one.
- Don't change the pipeline, models or processed files.

## Cut order if time runs short
Drop in this order, and report what you dropped:
1. Player-search highlight in the scatter
2. Calibration chart on Data Quality
3. Shareable URLs
4. Preset chips

Everything else is required.

## Acceptance criteria
1. `make app` runs; all tabs and pages render with real data, and every panel heading is a data-generated takeaway.
2. `make lint` and `make test` pass, offline.
3. No red/green in any chart; the "about the same" grey appears when an interval crosses zero.
4. On branch `task-07-app-redesign`: all staged, nothing committed or pushed.

## Report back with
- `git status --short` and the branch
- The takeaway headings shown on each tab for the **SEC college arms** preset
- The list of screenshots
- The cold-start time
- Anything cut from the cut order
- Deviations and why

Reminder: STAGE with `git add -A`, DO NOT COMMIT OR PUSH, and no AI attribution anywhere.
