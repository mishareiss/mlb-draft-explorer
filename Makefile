.PHONY: setup pull pull-bbref backfill schools all-data profile test lint

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

all-data: pull pull-bbref backfill schools profile

profile:
	uv run python -m ingest.profile

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
