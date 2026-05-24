"""Single-attempt HTTP helper. Bruin retries the asset on failure."""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
import signal

USER_AGENT = "Mozilla/5.0 eskom-weekly (+https://www.eskom.co.za/media-room/)"
TIMEOUT_SECONDS = 60
DEADLINE_SECONDS = 30


@contextmanager
def _deadline(seconds: int):
    def _handle_timeout(_signum, _frame):
        raise TimeoutError(f"request exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _quote_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        parts.scheme,
        parts.netloc,
        urllib.parse.quote(parts.path, safe="/%:@"),
        urllib.parse.quote(parts.query, safe="=&%:@/?+;,"),
        urllib.parse.quote(parts.fragment, safe="%:@/?+;,"),
    ))


def get(url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str, int]:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(_quote_url(url), headers=request_headers)
    try:
        with _deadline(DEADLINE_SECONDS):
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read(), response.geturl(), response.status
    except urllib.error.HTTPError as exc:
        return (exc.read() if exc.fp else b""), url, exc.code
    except (TimeoutError, urllib.error.URLError, OSError):
        return b"", url, 0
