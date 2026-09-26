"""The single place this project talks to the network.

Every MLB Stats API call goes through `fetch_json_cached`, which writes the raw
response to disk and serves it from there on later runs.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

USER_AGENT = "college-draft-explorer/0.1 (personal portfolio data project; low-volume, cached)"
TIMEOUT_S = 30
MIN_INTERVAL_S = 0.5

_session: requests.Session | None = None
_last_request_at = 0.0


def get_session() -> requests.Session:
    """Shared session: descriptive User-Agent, exponential backoff on 429/5xx."""
    global _session
    if _session is None:
        retry = Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        _session = s
    return _session


def get(url: str, session: requests.Session | None = None) -> requests.Response:
    """GET with a polite minimum gap between calls; raises on HTTP errors."""
    global _last_request_at
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    log.info("GET %s", url)
    try:
        resp = (session or get_session()).get(url, timeout=TIMEOUT_S)
    finally:
        _last_request_at = time.monotonic()
    resp.raise_for_status()
    return resp


def fetch_json_cached(
    url: str,
    path: str | Path,
    force: bool = False,
    session: requests.Session | None = None,
) -> Any:
    """Return JSON for `url`, reading `path` if cached, else fetching and saving verbatim."""
    path = Path(path)
    if path.exists() and not force:
        return json.loads(path.read_text())
    resp = get(url, session=session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return resp.json()
