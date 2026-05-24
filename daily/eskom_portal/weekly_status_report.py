"""Fetch and parse the NTCSA Weekly System Status Report PDFs.

The WP REST feed lists the most recent reports with embedded PDF links.
Each report's page-5 table holds rooftop PV installed capacity by province
and month — we extract that section and return long-form rows.

This module wraps everything as one ``fetch_reports()`` helper that yields
a dict per available report, suitable for direct use in a bruin Python
asset's ``materialize()``.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Iterable

FEED_URL = "https://www.ntcsa.co.za/?rest_route=/wp/v2/systemstatus&_embed&per_page=10"

ROOFTOP_PROVINCES = [
    "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
    "Mpumalanga", "Northern Cape", "North-West", "Western Cape", "Total",
]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_RE = re.compile(
    r"^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)-(\d{2})\s+(.+)$",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"(?:\d{1,3}(?:[, ]\d{3})+|\d+)(?:\.\d+)?")


def list_feed_pdfs() -> list[dict[str, str]]:
    """Return [{name, url, post_date}, ...] for PDFs advertised in the feed."""
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as fh:
        data = json.load(fh)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for post in data:
        content = post.get("content", {}).get("rendered", "")
        post_date = post.get("date") or ""
        for url in re.findall(r'href="(https?://[^"]+\.pdf)"', content):
            name = os.path.basename(url)
            if name in seen:
                continue
            seen.add(name)
            out.append({"name": name, "url": url, "post_date": post_date})
    return out


def download_pdf(url: str, dest_dir: Path) -> Path:
    """Download (if not cached) and return local path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / os.path.basename(url)
    if not path.exists():
        subprocess.run(
            ["curl", "-sS", "-A", "Mozilla/5.0", "-o", str(path), url], check=True
        )
    return path


def pdf_to_text(pdf_path: Path) -> str:
    """Run pdftotext -layout and return text. Caches alongside the PDF."""
    txt_path = pdf_path.with_suffix(".txt")
    if not txt_path.exists():
        subprocess.run(["pdftotext", "-layout", str(pdf_path)], check=True)
    return txt_path.read_text()


def parse_rooftop_section(txt: str) -> list[tuple[date, str, float]]:
    """Return [(observation_date, province, installed_mw), ...] from a report's text.

    Raises RuntimeError if the rooftop PV section can't be located.
    """
    parts = re.split(r"\n\s*Estimated Rooftop PV\s*\n", txt)
    if len(parts) < 2:
        raise RuntimeError("'Estimated Rooftop PV' section not found in PDF text")
    section = parts[-1].split("*Rooftop PV")[0]

    rows: list[tuple[date, str, float]] = []
    for line in section.split("\n"):
        m = _MONTH_RE.match(line)
        if not m:
            continue
        mon, yy, rest = m.groups()
        nums = _NUM_RE.findall(rest)
        cleaned = [float(n.replace(",", "").replace(" ", "")) for n in nums]
        if len(cleaned) != len(ROOFTOP_PROVINCES):
            # Skip malformed rows silently — the parser sometimes catches table headers
            continue
        obs = date(2000 + int(yy), _MONTHS[mon.lower()], 1)
        for prov, val in zip(ROOFTOP_PROVINCES, cleaned):
            rows.append((obs, prov, val))
    return rows


def fetch_reports(cache_dir: Path) -> Iterable[dict[str, Any]]:
    """Yield one dict per report advertised in the WP feed.

    Each yielded dict has: name, url, post_date, pdf_path, text_content,
    content_hash, error (None on success).
    """
    for entry in list_feed_pdfs():
        try:
            pdf_path = download_pdf(entry["url"], cache_dir)
            text = pdf_to_text(pdf_path)
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            yield {
                "name":         entry["name"],
                "url":          entry["url"],
                "post_date":    entry["post_date"],
                "pdf_path":     str(pdf_path),
                "text_content": text,
                "content_hash": content_hash,
                "error":        None,
            }
        except Exception as e:
            yield {
                "name":         entry["name"],
                "url":          entry["url"],
                "post_date":    entry["post_date"],
                "pdf_path":     None,
                "text_content": None,
                "content_hash": None,
                "error":        f"{type(e).__name__}: {e}",
            }
