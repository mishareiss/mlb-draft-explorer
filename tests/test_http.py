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


def test_user_agent_has_contact_url():
    assert "https://github.com/mishareiss/college-draft-explorer" in http.USER_AGENT


# --- fetch_text_cached (Baseball-Reference / Wikipedia) ----------------------------------


def text_session(status: int = 200, body: bytes = b"<html>ok</html>") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.content = body
    resp.raise_for_status.side_effect = None if status < 400 else RuntimeError(status)
    session = MagicMock()
    session.get.return_value = resp
    return session


def fetch_text(path, session, **kw):
    kw = {"min_interval_s": 0, "retry_429": False, **kw}
    return http.fetch_text_cached("https://bbref.test/p", path, session=session, **kw)


def test_text_cache_hit_makes_no_http_call(tmp_path):
    path = tmp_path / "page.html"
    path.write_bytes("<p>cached é</p>".encode())
    session = text_session()
    assert fetch_text(path, session) == "<p>cached é</p>"
    session.get.assert_not_called()


def test_text_cache_miss_writes_bytes_verbatim(tmp_path):
    body = "<p>Rodón</p>".encode()
    path = tmp_path / "sub" / "page.html"
    session = text_session(body=body)
    assert fetch_text(path, session) == "<p>Rodón</p>"
    assert path.read_bytes() == body
    session.get.assert_called_once_with("https://bbref.test/p", timeout=http.TIMEOUT_S)


def test_text_min_interval_respected(tmp_path, monkeypatch):
    clock = {"t": 100.0}
    sleeps = []
    monkeypatch.setattr(http.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(http.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(http, "_last_request_at", 0.0)
    session = text_session()

    fetch_text(tmp_path / "a.html", session, min_interval_s=7)  # long after last call: no wait
    clock["t"] += 2.0
    fetch_text(tmp_path / "b.html", session, min_interval_s=7)  # 2 s later: wait the other 5 s
    assert sleeps == [pytest.approx(5.0)]
    assert session.get.call_count == 2


@pytest.mark.parametrize("status", [429, 403])
def test_rate_limit_raises_after_exactly_one_request(tmp_path, status):
    session = text_session(status=status)
    path = tmp_path / "page.html"
    with pytest.raises(http.RateLimitedError, match="wait an hour"):
        fetch_text(path, session)
    assert session.get.call_count == 1
    assert not path.exists()  # nothing cached on failure


def test_no_retry_session_has_no_automatic_retries():
    s = http.get_session(retry_429=False)
    retry = s.get_adapter("https://www.baseball-reference.com").max_retries
    assert retry.total == 0
    assert 429 not in (retry.status_forcelist or ())
    assert s is not http.get_session()  # MLB session keeps its retries
    assert http.get_session().get_adapter("https://x").max_retries.total == 5


def test_json_path_still_uses_retrying_session(tmp_path, monkeypatch):
    used = []

    def spy(retry_429=True):
        used.append(retry_429)
        return fake_session({"ok": 1})

    monkeypatch.setattr(http, "get_session", spy)
    assert http.fetch_json_cached("https://statsapi.test", tmp_path / "x.json") == {"ok": 1}
    assert used == [True]
