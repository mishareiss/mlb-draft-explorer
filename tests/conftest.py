import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def draft_payload() -> dict:
    return json.loads((FIXTURES / "draft_2023_sample.json").read_text())


@pytest.fixture
def people_payload() -> dict:
    return json.loads((FIXTURES / "people_batch_sample.json").read_text())
