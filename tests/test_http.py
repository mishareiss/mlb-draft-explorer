import json
from unittest.mock import MagicMock

import pytest

from ingest import http


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    monkeypatch.setattr(http, "MIN_INTERVAL_S", 0)


def fake_session(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.content = json.dumps(payload).encode()
    resp.json.return_value = payload
    session = MagicMock()
    session.get.return_value = resp
    return session


def test_cache_hit_makes_no_http_call(tmp_path):
    path = tmp_path / "cached.json"
    path.write_text('{"cached": true}')
    session = fake_session({"cached": False})
    assert http.fetch_json_cached("https://x.test", path, session=session) == {"cached": True}
    session.get.assert_not_called()


def test_force_makes_one_call_and_overwrites(tmp_path):
    path = tmp_path / "cached.json"
    path.write_text('{"cached": true}')
    session = fake_session({"fresh": 1})
    assert http.fetch_json_cached("https://x.test", path, force=True, session=session) == {
        "fresh": 1
    }
    session.get.assert_called_once()
    assert json.loads(path.read_text()) == {"fresh": 1}


def test_cache_miss_writes_response_verbatim(tmp_path):
    path = tmp_path / "sub" / "new.json"
    session = fake_session({"a": [1, 2]})
    http.fetch_json_cached("https://x.test", path, session=session)
    session.get.assert_called_once_with("https://x.test", timeout=http.TIMEOUT_S)
    assert path.read_bytes() == session.get.return_value.content


def test_shared_session_config():
    s = http.get_session()
    assert "college-draft-explorer" in s.headers["User-Agent"]
    retry = s.get_adapter("https://statsapi.mlb.com").max_retries
    assert retry.total == 5
    assert {429, 500, 502, 503, 504} <= set(retry.status_forcelist)
