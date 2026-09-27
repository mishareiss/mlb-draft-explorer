# Task 5: Rename to MLB Draft Explorer, final app polish, README, and deploy prep

## Context
The app (Task 4) works and is about to be merged. The GitHub repo is named **`mlb-draft-explorer`**
(`https://github.com/mishareiss/mlb-draft-explorer`), and it will be deployed on **Streamlit Community
Cloud** today for a job application due tonight. This task is small and must stay small: rename,
three app fixes, a portfolio-quality README, and a clean-clone check. No new features.

Read first: `README.md`, `app/Explorer.py`, `app/lib/charts.py`, `app/lib/metrics.py`,
`app/pages/1_Data_Quality.py`, `app/pages/2_About.py`, `ingest/http.py`, `tests/test_http.py`,
`pyproject.toml`, `.github/workflows/ci.yml`, `docs/screenshots/`.

Branch: `git switch -c task-05-polish` from `main` after I've merged Task 4.

IMPORTANT: STAGE all changes (`git add -A`) but DO NOT COMMIT OR PUSH. I commit and push myself.
No `Co-Authored-By` or any AI/session trailers anywhere.

## Scope

### 1. Rename `college-draft-explorer` → `mlb-draft-explorer`, "College Draft Explorer" → "MLB Draft Explorer"
- `pyproject.toml` name (then `uv lock`), the User-Agent in `ingest/http.py` and its tests, the About page link, the README title, the app title and page title (`st.set_page_config`), and any other visible string. Don't edit `docs/prompts/*`.
- The app covers high school and junior college draftees too, so avoid "college-only" wording anywhere in the UI.
- Run `grep -ri "college-draft\|College Draft" --exclude-dir=.venv --exclude-dir=docs/prompts .` and confirm it returns nothing.

### 2. App fixes
1. **Compare groups hides the extremes.** With more than 25 groups the chart shows only the top 25, so the default takeaway names SWAC (the lowest group) while SWAC isn't on the chart. Fix: when groups exceed 25, show the **top 12 and bottom 12** with a thin visual gap between them, and caption "Showing the 12 highest and 12 lowest of N groups." The takeaway must only name groups that are visible. Add a test.
2. **Team names are current franchise names** (a 2012 Indians pick shows "Cleveland Guardians"). Don't change the data. Rename the table column to "Team (current name)", and add a limitation bullet on the Data Quality page: "Team shows the franchise's current name."
3. **Scatter x-axis:** start the log axis at $1k. Keep bonuses under $1k in the data and table, but clip them to the axis edge in the chart, and add to the caption: "Bonuses under $1k are shown at $1k."

### 3. README (the first thing a hiring manager opens; make it scannable)
Structure:
1. Title, then one sentence: what it answers. Then a **Live app** link placeholder: `**[Open the live app](STREAMLIT_URL)**`, with the literal token `STREAMLIT_URL` so I can replace it after deploying. Add a CI badge for the new repo path.
2. Hero image: `docs/screenshots/explorer-sec-4yr-rhp.png`.
3. **Why this exists** (2–3 sentences): scouts and coordinators need self-serve answers to "what's the track record of players like this?" without a notebook.
4. **Three findings**, each one sentence with numbers **computed from `draft_outcomes.parquet` by a script you run now, not copied from this prompt**. Use outcome-eligible signed players, 2012–2019. Candidates:
   - MLB rate by slot band (top 10 picks vs. 301+)
   - SEC vs. all draftees
   - High school vs. 4-year college: MLB %, WAR per player, and median years to debut
   Put the script in `scripts/readme_findings.py` so the numbers are reproducible, and print its output in your report.
5. **What you can do in the app**: 4–5 bullets, with the Data Quality screenshot below them.
6. **How it's built**: a small ASCII or Mermaid diagram (MLB Stats API / Baseball-Reference / Wikipedia → Python ingest (cached raw) → DuckDB SQL models → quality checks → parquet → Streamlit), then one line each on the ingest, models, quality checks and app folders.
7. **Data quality**: the checks in 3–4 bullets (row reconciliation, uniqueness, join coverage, signed logic). Mention the Baseball-Reference vs. MLB 2017 bonus cross-check (99.8% exact).
8. **Limitations**: the same bullets as the Data Quality page.
9. **Run it locally**: `uv sync`, `make app` (runs from committed data), and `make all-data && make build` to rebuild from sources (about 30 minutes the first time because of polite Baseball-Reference throttling).
10. **Data sources and credit**: MLB Stats API, Baseball-Reference, Wikipedia. Then: "Built by Misha Reiss."
Keep it under ~150 lines. No emojis. No claims that aren't backed by the code or data.

### 4. Deploy readiness
- Streamlit Community Cloud installs from `uv.lock` first when one exists, so **don't add a `requirements.txt`**; two dependency files confuse it. Confirm `uv.lock` is current.
- **Clean-clone check:** export only the tracked and staged files to a temp dir (`git checkout-index -a --prefix=/tmp/mde-check/`), then run `uv sync` there and start the Explorer (`AppTest`, or `streamlit run --server.headless true` for ~10 s). This proves the app starts from committed files alone, without `data/raw`, `data/interim` or `.venv`. Report the result.
- Add `docs/DEPLOY.md` with the exact Streamlit Community Cloud steps: repo `mishareiss/mlb-draft-explorer`, branch `main`, main file `app/Explorer.py`, Python 3.12 under advanced settings, no secrets.

## Testing
- Keep the full suite green (`make lint`, `make test`), offline.
- New tests: the top/bottom split (30 groups → 24 shown, extremes included, the takeaway only names visible groups); the scatter clip leaves the underlying frame unchanged; the renamed title appears in the Explorer AppTest.

## Acceptance criteria
1. The grep in scope 1 returns nothing (outside `docs/prompts`).
2. `make test` and `make lint` pass. The clean-clone app start succeeds.
3. The README renders on GitHub (check relative image paths) and contains `STREAMLIT_URL` exactly once.
4. On branch `task-05-polish`: all staged, nothing committed, nothing pushed.

## Report back with
- `git status --short` and the branch
- The output of `scripts/readme_findings.py`, plus the three finding sentences as written
- The full README text
- The clean-clone result
- A new screenshot of Compare groups with default filters, saved over `docs/screenshots/explorer-default.png`
- Deviations and why

Reminder: STAGE with `git add -A`, DO NOT COMMIT OR PUSH, and no AI attribution anywhere.
