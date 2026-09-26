"""Opt-in smoke test against the real API: `uv run pytest -m live`."""

import pytest

from ingest.http import get
from ingest.pull_draft import DRAFT_URL


@pytest.mark.live
def test_draft_endpoint_shape():
    payload = get(DRAFT_URL.format(year=2023)).json()
    pick = payload["drafts"]["rounds"][0]["picks"][0]
    assert {"pickRound", "pickNumber", "person", "school"} <= pick.keys()
