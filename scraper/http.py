"""Polite HTTP layer: per-host delay, retries, timeout, custom UA."""
import time
from urllib.parse import urlparse

import requests

USER_AGENT = "MorganGroupMapBot/1.0 (contact: aviparmar2313@gmail.com)"
DELAY_S = 0.5
TIMEOUT_S = 20
RETRIES = 2

_last_request: dict[str, float] = {}
_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def _throttle(host: str, now=time.monotonic, sleep=time.sleep) -> None:
    last = _last_request.get(host)
    t = now()
    if last is not None and t - last < DELAY_S:
        sleep(DELAY_S - (t - last))
    _last_request[host] = now()


def get(url: str, *, params=None, headers=None) -> requests.Response:
    host = urlparse(url).netloc
    err: Exception | None = None
    for attempt in range(RETRIES + 1):
        _throttle(host)
        try:
            resp = _session.get(url, params=params, headers=headers, timeout=TIMEOUT_S)
            if resp.status_code >= 500 and attempt < RETRIES:
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            err = e
            if attempt < RETRIES:
                time.sleep(1 + attempt)
    raise err  # type: ignore[misc]
