# Task 6: Expected-by-pick model, outcome tiers, and updated findings

## Context
The app is live and the repo is pushed. A front-office review found that every ranking mostly
rediscovers draft order: SEC players reach MLB more often, but they're also picked earlier. This
task adds the **data and model layer** for the v1.1 redesign: an expected-outcome-by-pick model,
slot-adjusted columns on every row, outcome tiers, the related quality checks, and refreshed
README findings. **No app/UI changes**; that's Task 7, which reads what this task produces.

Read first: `models/07_draft_outcomes.sql`, `transform/run.py`, `quality/checks.py`,
`scripts/readme_findings.py`, `app/lib/metrics.py` (`OutcomeRules`, `metric_stat`), `README.md`
("Three findings"), `tests/test_models.py`, `tests/test_quality.py`, `Makefile`.

Branch: `git switch -c task-06-slot-model` from `main`.

IMPORTANT: STAGE all changes (`git add -A`) but DO NOT COMMIT OR PUSH. I commit myself. No
`Co-Authored-By` or any AI/session trailers anywhere.

## Scope

### 1. Outcome tiers (SQL): new `models/08_outcome_tiers.sql`
Add columns to the final table, either by rebuilding `draft_outcomes` in 08 or by folding them into 07. Pick whichever keeps 07 readable, and say which you chose.
- `outcome_tier` (text), for rows with `draft_year BETWEEN 2012 AND 2019` only; null for 2020+:
  - `Didn't sign`: not the final draft, or final draft and `signed = false`
  - `Never reached MLB`: signed, no debut
  - `Cup of coffee`: debuted, `career_war < 1`
  - `Role player`: `1 <= career_war < 5`
  - `Regular`: `5 <= career_war < 15`
  - `Star`: `career_war >= 15`
- `outcome_tier_order` (int 0–5, in the order above) for sorting and stacking.
- `became_regular` (bool): `career_war >= 5`, on outcome-eligible rows only; null elsewhere.
- Comment in the SQL that career WAR favors older classes, so tiers are lenient for 2018–2019.

### 2. Expected-by-pick model: `transform/slot_model.py`
Runs after the SQL in `transform/run.py` (Python is fine here; it's a model fit, not business logic).
- **Training rows:** `outcome_eligible` (2012–2019 final drafts).
- **Two targets:** `reached_mlb` and `became_regular`.
- **Two training populations:** (a) signed players only, (b) all outcome-eligible rows including unsigned. So 4 fitted curves.
- **Model:** logistic regression on a spline of `log(pick_number)`, using `SplineTransformer` (about 4–5 knots, degree 3) + `LogisticRegression` with light regularization. Add `scikit-learn` via `uv add`, and report the resolved version. Keep it deterministic.
- **Monotonicity:** expected probability must not increase with pick number. After fitting, check that no step up exceeds 0.5 percentage points. If it does, fall back to isotonic regression for that curve and log it. Report which method each curve used.
- **Per-row output columns** (every row, all years, since the expectation depends only on pick):
  - `exp_mlb_signed`, `exp_mlb_all`, `exp_regular_signed`, `exp_regular_all` (probabilities 0–1)
  - `mlb_minus_exp`: `reached_mlb - exp_mlb_signed` for signed outcome-eligible rows, else null
  - `regular_minus_exp`: same pattern for `became_regular` vs `exp_regular_signed`

  The app will average these per group ("reached MLB X points more often than players picked where they were picked"). For the "count unsigned" setting, Task 7 will use the `_all` columns.
- **Curve table:** write `data/processed/slot_expectation.parquet` with one row per `pick_number` from 1 to the max pick in any year: `pick_number, exp_mlb_signed, exp_mlb_all, exp_regular_signed, exp_regular_all`. Commit it; the app draws the expected curve from it.
- **Model evaluation** (goes into `quality_report.json` under `tables.slot_model`):
  - Brier score and log loss vs. a constant (overall rate) baseline, for each curve
  - **Leave-one-class-out** calibration: fit on 7 classes, predict the 8th, repeat, then bin predictions into 10 deciles and report expected vs. observed rate and n per decile
  - Expected MLB % at picks 1, 10, 30, 100, 300 and 1,000

### 3. Quality checks (`quality/checks.py`)
- `slot_expectation_complete` (fail): every row has all four `exp_*` values, and each is in [0, 1].
- `slot_curve_monotone` (fail): no curve rises by more than 0.5 percentage points as pick number increases.
- `slot_model_calibrated` (warn): in the leave-one-class-out deciles for `exp_mlb_signed`, flag any decile whose observed rate falls outside its 90% Wilson interval around the expected rate. The value is the count of such deciles.
- `outcome_tiers_complete` (fail): every 2012–2019 row has exactly one tier; 2020+ rows have none. Tier counts sum to the 2012–2019 row count.
- Add the tier mix by draft year (2012–2019) to `tables` for the Data Quality page.

### 4. README findings
Update `scripts/readme_findings.py` to also print, for the same groups:
- The slot-adjusted rate: mean `mlb_minus_exp` in percentage points, with a 90% interval (±1.645 × sd / √n), for all draftees (≈0 by construction), picks 1–10, 301+, SEC, high school and 4-year college
- Each group's tier mix

Then rewrite the README's "Three findings" so **at least one uses the slot-adjusted number**, most naturally the SEC finding: does the SEC still beat its draft slot once pick position is accounted for, and by how much? **Write whatever the data says, even if the SEC edge mostly disappears.** That's a finding too. Keep each finding one sentence, with n.

## Wiring
- `transform/run.py`: SQL models, then `slot_model`, then write `draft_outcomes.parquet` + `slot_expectation.parquet`. `make build` still runs transform, then quality.
- `.gitignore`: commit `data/processed/slot_expectation.parquet`.

## Testing (offline and deterministic; keep the suite green)
- **Tier boundaries:** WAR 0.99 → Cup of coffee, 1.0 → Role player, 4.99 → Role player, 5.0 → Regular, 15.0 → Star. A non-final 2015 row → Didn't sign. A 2021 row → null tier. A signed player with no debut → Never reached MLB.
- **Slot model on synthetic data:** generate about 8,000 rows where the true P(MLB) is a known decreasing function of pick. Assert the fitted curve is within 3 points of the truth at picks 10, 100 and 500, and that the output is monotone.
- **Isotonic fallback:** a deliberately non-monotone synthetic dataset triggers the fallback and the output is monotone.
- **Column semantics:** `mlb_minus_exp` is null for unsigned, non-final and 2020+ rows. On the synthetic set, its mean over all signed eligible rows is ≈ 0 (within 1 point).
- **New checks:** each returns `fail` on a broken input (a missing `exp_*` value, a curve with a 2-point rise, a 2016 row with no tier).
- **Processed-data test:** the committed files pass every fail-level check.

## Constraints
- No UI changes; the app must still run unchanged on the new parquet (extra columns are fine).
- Tier definitions and cutoffs live in SQL only. Model code stays short and commented; this is a work sample.
- Don't change the existing columns' meanings.

## Acceptance criteria
1. `make build` succeeds; quality has no `fail`.
2. `make lint` and `make test` pass, offline.
3. `slot_expectation.parquet` exists and is monotone; `draft_outcomes.parquet` has the new columns with the documented null rules.
4. On branch `task-06-slot-model`: all staged, nothing committed or pushed.

## Report back with
- `git status --short` and the branch; the resolved scikit-learn version
- The method used for each of the 4 curves, and the expected MLB % (signed) at picks 1 / 10 / 30 / 100 / 300 / 1,000
- Brier and log loss vs. baseline, and the leave-one-class-out decile table for `exp_mlb_signed`
- The full `scripts/readme_findings.py` output, and the rewritten "Three findings"
- Tier counts for 2012–2019 overall
- The new quality check results
- Deviations and why; anything Task 7 (the app) needs to know

Reminder: STAGE with `git add -A`, DO NOT COMMIT OR PUSH, and no AI attribution anywhere.
