"""Scrape one Eskom Data Portal graph page → its CSV → parsed rows.

Returns a single result dict capturing both the raw response and the parsed
rows, suitable for direct use in a bruin Python asset's materialize().
"""
from __future__ import annotations

import csv
import datetime as dt
import html.parser
import io
import math
import re
import urllib.parse
from typing import Any

from eskom_portal.fetch import get


# ---------- HTML link extraction ----------

class _HtmlLinks(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            for k, v in attrs:
                if k.lower() == "href" and v:
                    self.links.append(v)


def _csv_links(page_url: str, body: bytes) -> list[str]:
    parser = _HtmlLinks()
    parser.feed(body.decode("utf-8", errors="replace"))
    abs_links = [urllib.parse.urljoin(page_url, l) for l in parser.links]
    return [l for l in dict.fromkeys(abs_links)
            if urllib.parse.urlparse(l).path.lower().endswith(".csv")]


# ---------- CSV parse + axis/value coercion ----------

def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:300].lower()
    return head.startswith("<!doctype") or head.startswith("<html")


def _sniff_delimiter(text: str) -> str:
    sample = "\n".join(line for line in text.splitlines()[:10] if line.strip())
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _parse_number(value: Any, delimiter: str) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", " ").replace("%", "").strip()
    if not text or re.search(r"[A-Za-z/]", text):
        return None
    compact = text.replace(" ", "")
    compact = compact.replace(",", ".") if (delimiter == ";" and "," in compact and "." not in compact) \
              else compact.replace(",", "")
    try:
        n = float(compact)
        return n if math.isfinite(n) else None
    except ValueError:
        return None


def _parse_axis(value: Any) -> dt.datetime | None:
    """Best-effort timestamp parse for the axis column. None if non-temporal."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d",
                "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    embedded = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if embedded:
        try:
            return dt.datetime.strptime(embedded.group(0), "%Y-%m-%d")
        except ValueError:
            pass
    return None


_DATE_HEADER_HINTS = ("date", "time", "week", "month", "year")


def _choose_axis_column(headers: list[str]) -> str | None:
    if not headers:
        return None
    for h in headers:
        low = h.lower()
        if any(hint in low for hint in _DATE_HEADER_HINTS):
            return h
    return headers[0]


# ---------- main entry point ----------

def scrape_csv(page_url: str) -> dict[str, Any]:
    """Fetch the graph page, find the first CSV link, fetch + parse it.

    Returns:
      {
        "scraped_at": datetime (UTC),
        "page_url": str,
        "csv_url": str | None,
        "http_status": int,
        "content_text": str | None,   # the raw CSV (or error HTML), preserved for replay
        "error": str | None,
        "rows": list[{"timestamp": datetime|None, "series": str, "value": float}],
      }
    """
    scraped_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    result: dict[str, Any] = {
        "scraped_at": scraped_at,
        "page_url": page_url,
        "csv_url": None,
        "http_status": 0,
        "content_text": None,
        "error": None,
        "rows": [],
    }

    page_body, _final, page_status = get(page_url)
    if page_status != 200:
        result["http_status"] = page_status
        result["error"] = f"page fetch HTTP {page_status}"
        result["content_text"] = page_body.decode("utf-8", errors="replace")[:200_000]
        return result

    links = _csv_links(page_url, page_body)
    if not links:
        result["error"] = "no CSV link on graph page"
        return result

    csv_url = links[0]
    result["csv_url"] = csv_url

    raw, _f, http_status = get(csv_url)
    result["http_status"] = http_status
    text = _decode(raw)
    result["content_text"] = text[:5_000_000]  # cap for very large CSVs

    if http_status != 200:
        result["error"] = f"CSV HTTP {http_status}"
        return result
    if _looks_like_html(text):
        result["error"] = "CSV link returned HTML"
        return result

    # parse
    delimiter = _sniff_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [h.strip() for h in (reader.fieldnames or []) if h is not None]
    axis_col = _choose_axis_column(headers)

    rows: list[dict[str, Any]] = []
    for raw_row in reader:
        ts = _parse_axis(raw_row.get(axis_col)) if axis_col else None
        for h in headers:
            if h == axis_col:
                continue
            v = _parse_number(raw_row.get(h), delimiter)
            if v is None:
                continue
            rows.append({"timestamp": ts, "series": h, "value": v})
    result["rows"] = rows
    return result
