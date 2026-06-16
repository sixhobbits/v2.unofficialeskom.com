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


def parse_report_meta(txt: str) -> dict | None:
    """Pull the report's week number + covered date range from the title line,
    e.g. 'Weekly System Status Report – 2026 Week 22 (25/05/2026 – 31/05/2026)'."""
    m = re.search(
        r"Week\s+(\d+)\s*\((\d{2}/\d{2}/\d{4})\s*[–-]\s*(\d{2}/\d{2}/\d{4})\)", txt
    )
    if not m:
        return None
    return {
        "week": int(m.group(1)),
        "period_start": m.group(2),
        "period_end": m.group(3),
        "period": f"{m.group(2)} – {m.group(3)}",
    }


# A "52 Week Outlook" row: 'DD-Mon-YY  WW  <8 MW columns>  [free-text notes]'.
# The historic daily table on page 1 uses 'Mon 25/May/2026' instead, so it never
# matches. Note Eskom writes September as 'Sept'.
_OUTLOOK_ROW_RE = re.compile(r"^\s*(\d{1,2})-([A-Za-z]{3,4})-(\d{2})\s+(\d{1,3})\s+(.*)$")
_OUTLOOK_COLS = [
    "rsa_contracted_mw", "residual_forecast_mw", "available_dispatchable_mw",
    "available_less_or_ua_mw", "planned_maint_mw", "unplanned_assumption_mw",
    "planned_risk_mw", "likely_risk_mw",
]


def status_from_margin(likely_risk_mw: int) -> str:
    """Map the 'Likely Risk Scenario' MW margin to the report's colour key:
    Green = adequate; Yellow = short <1000 MW of reserves; Orange = 1001–2000;
    Red = >2001 (short to meet demand + reserves). A positive margin is surplus."""
    if likely_risk_mw >= 0:
        return "green"
    short = -likely_risk_mw
    if short <= 1000:
        return "yellow"
    if short <= 2000:
        return "orange"
    return "red"


def parse_status_outlook(txt: str) -> list[dict[str, Any]]:
    """Parse the '52 Week Outlook' table into one dict per forecast week, with a
    derived green/yellow/orange/red ``status`` (the PDF's cell colours are lost
    by pdftotext, so they're re-derived from the Likely Risk Scenario margin)."""
    out: list[dict[str, Any]] = []
    for line in txt.split("\n"):
        m = _OUTLOOK_ROW_RE.match(line)
        if not m:
            continue
        dd, mon, yy, wk, rest = m.groups()
        mon = mon.lower()
        if mon not in _MONTHS:
            continue
        nums = re.findall(r"-?\d{3,6}", rest)
        if len(nums) < 8:
            continue
        vals = [int(x) for x in nums[:8]]
        try:
            week_start = date(2000 + int(yy), _MONTHS[mon], int(dd))
        except ValueError:
            continue
        row = {"week_start": week_start, "week_num": int(wk)}
        row.update(dict(zip(_OUTLOOK_COLS, vals)))
        row["status"] = status_from_margin(vals[7])
        out.append(row)
    return out


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
