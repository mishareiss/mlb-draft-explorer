.PHONY: setup pull pull-bbref backfill schools draft-dates all-data profile transform quality build app test lint

setup:
	uv sync

# MLB Stats API + WAR only (fast)
pull:
	uv run python -m ingest.pull_draft
	uv run python -m ingest.pull_people
	uv run python -m ingest.pull_war

# Baseball-Reference draft pages, 2012-2017: ~240 pages at 7 s each (~30 min on first run)
pull-bbref:
	uv run python -m ingest.pull_bbref_draft

backfill:
	uv run python -m ingest.build_bonus_backfill

schools:
	uv run python -m ingest.build_school_ref

# First day of each draft, from cached Wikipedia pages -> reference/draft_dates.csv
draft-dates:
	uv run python -m ingest.build_draft_dates

all-data: pull pull-bbref backfill schools draft-dates profile

profile:
	uv run python -m ingest.profile

# models/*.sql in DuckDB -> data/processed/draft_outcomes.parquet
transform:
	uv run python -m transform.run

# checks -> data/processed/quality_report.json; fails the build on any "fail"
quality:
	uv run python -m quality.checks

build: transform quality

# Explorer, Data Quality and About pages on http://localhost:8501
app:
	uv run streamlit run app/Explorer.py

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
