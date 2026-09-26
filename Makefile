.PHONY: setup pull profile test lint

setup:
	uv sync

pull:
	uv run python -m ingest.pull_draft
	uv run python -m ingest.pull_people
	uv run python -m ingest.pull_war

profile:
	uv run python -m ingest.profile

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
