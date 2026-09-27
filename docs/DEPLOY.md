# Deploying to Streamlit Community Cloud

The app reads only committed files (`data/processed/draft_outcomes.parquet` and
`quality_report.json`), so the deploy needs no network access to the data sources and no secrets.
Dependencies come from `uv.lock`; there is deliberately no `requirements.txt` (Community Cloud
gets confused when it finds two dependency files).

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with the GitHub account that owns
   the repo, and allow access to `mishareiss/mlb-draft-explorer` if asked.
2. Click **Create app**, then **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `mishareiss/mlb-draft-explorer`
   - **Branch:** `main`
   - **Main file path:** `app/Explorer.py`
   - **App URL:** optional, for example `mlb-draft-explorer`
4. Open **Advanced settings**:
   - **Python version:** `3.12` (the project requires `>=3.12,<3.13`)
   - **Secrets:** leave empty
5. Click **Deploy**. The first build installs the locked dependencies and takes a few minutes.
6. Check that all three pages load (Explorer, Data Quality, About).
7. Copy the app URL and replace `STREAMLIT_URL` in `README.md` with it.

## Updating

Every push to `main` redeploys the app. To refresh the data, run `make all-data && make build`
locally, then commit `data/processed/` and push.

## If the build fails

- Open **Manage app** (bottom right of the app) to read the build log.
- If dependencies fail to resolve, run `uv lock` locally, commit `uv.lock` and push.
- A Python version can't be changed on an existing app. To switch versions, delete the app and
  deploy it again.
