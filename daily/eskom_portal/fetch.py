"""Single-attempt HTTP helper. Bruin retries the asset on failure."""
from __future__ import annotations

import urllib.error
import urllib.request

USER_AGENT = "Mozilla/5.0 eskom-scraper-1-4 (+https://www.eskom.co.za/dataportal/)"
TIMEOUT_SECONDS = 45


def get(url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str, int]:
    """Returns (body, final_url, http_status). HTTP errors return the error
    body and the status code instead of raising."""
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read(), response.geturl(), response.status
    except urllib.error.HTTPError as exc:
        return (exc.read() if exc.fp else b""), url, exc.code


def post_json(url: str, payload: dict, headers: dict[str, str]) -> bytes:
    """Returns body bytes (caller decompresses if needed)."""
    import json
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request_headers = {"User-Agent": USER_AGENT, **headers, "Content-Type": "application/json"}
    request = urllib.request.Request(url, headers=request_headers, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()
