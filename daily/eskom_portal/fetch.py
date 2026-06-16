"""Single-attempt HTTP helper. Bruin retries the asset on failure."""
from __future__ import annotations

import urllib.error
import urllib.request

USER_AGENT = "Mozilla/5.0 eskom-scraper-1-4 (+https://www.eskom.co.za/dataportal/)"
TIMEOUT_SECONDS = 45


def get_meta(url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str, int, dict]:
    """Like get() but also returns the response headers (lower-cased keys), so
    callers can record cheap freshness validators (ETag / Last-Modified /
    Content-Length) alongside the body for change detection."""
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            hdrs = {k.lower(): v for k, v in response.headers.items()}
            return response.read(), response.geturl(), response.status, hdrs
    except urllib.error.HTTPError as exc:
        hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return (exc.read() if exc.fp else b""), url, exc.code, hdrs


def get(url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str, int]:
    """Returns (body, final_url, http_status). HTTP errors return the error
    body and the status code instead of raising."""
    body, final_url, status, _ = get_meta(url, headers)
    return body, final_url, status


def post_json(url: str, payload: dict, headers: dict[str, str]) -> bytes:
    """Returns body bytes (caller decompresses if needed)."""
    import json
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request_headers = {"User-Agent": USER_AGENT, **headers, "Content-Type": "application/json"}
    request = urllib.request.Request(url, headers=request_headers, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()
