"""The single place this project talks to the network.

MLB Stats API calls go through `fetch_json_cached`; HTML pages (Baseball-Reference,
Wikipedia) go through `fetch_text_cached`. Both write the raw response to disk and
serve it from there on later runs.

Baseball-Reference temporarily bans IPs that exceed its rate limit, and retrying a
429 makes that worse, so its calls use `retry_429=False`: a 429 or 403 stops the run
with `RateLimitedError` after a single request.
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

USER_AGENT = (
    "college-draft-explorer/0.1 (personal portfolio data project; low-volume, cached; "
    "+https://github.com/mishareiss/college-draft-explorer)"
)
TIMEOUT_S = 30
MIN_INTERVAL_S = 0.5

_session: requests.Session | None = None
_no_retry_session: requests.Session | None = None
_last_request_at = 0.0


class RateLimitedError(RuntimeError):
    """The server refused us (429/403). Stop now; do not retry."""


def _new_session(retry: Retry | int) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def get_session(retry_429: bool = True) -> requests.Session:
    """Shared session with a descriptive User-Agent.

    retry_429=True (MLB): exponential backoff on 429/5xx.
    retry_429=False (Baseball-Reference, Wikipedia): no automatic retries at all.
    """
    global _session, _no_retry_session
    if not retry_429:
        if _no_retry_session is None:
            _no_retry_session = _new_session(Retry(total=0, redirect=5, raise_on_status=False))
        return _no_retry_session
    if _session is None:
        _session = _new_session(
            Retry(
                total=5,
                backoff_factor=1.0,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=("GET",),
                respect_retry_after_header=True,
            )
        )
    return _session


def get(
    url: str,
    session: requests.Session | None = None,
    min_interval_s: float | None = None,
    retry_429: bool = True,
) -> requests.Response:
    """GET with a polite minimum gap between calls; raises on HTTP errors.

    With retry_429=False, a 429 or 403 raises `RateLimitedError`.
    """
    global _last_request_at
    gap = MIN_INTERVAL_S if min_interval_s is None else min_interval_s
    wait = gap - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    log.info("GET %s", url)
    try:
        resp = (session or get_session(retry_429)).get(url, timeout=TIMEOUT_S)
    finally:
        _last_request_at = time.monotonic()
    if not retry_429 and resp.status_code in (403, 429):
        raise RateLimitedError(
            f"HTTP {resp.status_code} from {url}. The site is rate-limiting us: stop and wait "
            "an hour. Cached pages are kept; re-run the same command to resume."
        )
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


def fetch_text_cached(
    url: str,
    path: str | Path,
    force: bool = False,
    *,
    min_interval_s: float,
    retry_429: bool,
    session: requests.Session | None = None,
) -> str:
    """Return the body of `url` as text, reading `path` if cached, else fetching and saving
    the raw bytes verbatim. Bodies are decoded as UTF-8 both ways so cache hits match."""
    path = Path(path)
    if path.exists() and not force:
        return path.read_bytes().decode("utf-8", errors="replace")
    resp = get(url, session=session, min_interval_s=min_interval_s, retry_429=retry_429)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return resp.content.decode("utf-8", errors="replace")
