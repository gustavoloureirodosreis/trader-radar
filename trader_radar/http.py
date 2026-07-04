from __future__ import annotations

import time

import requests

_session = requests.Session()
_session.headers["User-Agent"] = "trader-radar/0.1"


def request_json(
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
    headers: dict | None = None,
    max_retries: int = 4,
    timeout: int = 30,
):
    """HTTP with exponential backoff; 429s honor Retry-After when present."""
    delay = 2.0
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = _session.request(
                method, url, json=json_body, params=params, headers=headers, timeout=timeout
            )
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", delay))
                time.sleep(min(wait, 65))
                delay *= 2
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as err:
            last_err = err
            if attempt == max_retries:
                break
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"request failed after retries: {method} {url}: {last_err}")
