"""Helpers for parsing Eskom integrated-results PDFs."""
from __future__ import annotations

import re
from dataclasses import dataclass


_YEAR_RE = re.compile(r"(20\d{2})")
_GROUPED_NUMBER_RE = re.compile(r"\(?-?\d{1,3}(?: \d{3})+\)?")


@dataclass(frozen=True)
class ToplineMetric:
    metric: str
    value_rm: int | None
    source_line: str | None
    line_number: int | None
    confidence: str
    error: str | None = None


def is_annual_afs_filename(filename: str | None) -> bool:
    """Return true for Eskom group annual AFS-like PDFs.

    Excludes interim results and Nqaba Finance AFS documents because they are
    not final Eskom group annual financial statements.
    """
    if not filename:
        return False
    name = filename.lower()
    if "interim" in name or "nqaba" in name:
        return False
    return (
        "annual-financial" in name
        or "annual_financial" in name
        or "afs" in name
        or "full-afs" in name
        or "full_financials" in name
    )


def infer_financial_year(filename: str | None) -> int | None:
    if not filename:
        return None
    match = _YEAR_RE.search(filename)
    return int(match.group(1)) if match else None


def _parse_grouped_number(raw: str) -> int:
    negative = raw.startswith("(") or raw.startswith("-")
    digits = re.sub(r"[^\d]", "", raw)
    value = int(digits)
    return -value if negative else value


def extract_revenue_topline(text: str | None, filename: str | None = None) -> ToplineMetric:
    """Extract group revenue in Rm from an annual AFS text extraction."""
    if not text:
        return ToplineMetric("revenue", None, None, None, "none", "empty text")

    for idx, line in enumerate(text.splitlines(), start=1):
        if "Revenue" not in line:
            continue
        stripped = " ".join(line.split())
        lowered = stripped.lower()
        if any(skip in lowered for skip in (
            "revenue increased",
            "revenue amounted",
            "revenue is ",
            "revenue from ",
            "revenue recognition",
            "revenue management",
            "revenue not ",
            "revenue activity",
            "sales volume",
            "sales volumes",
            "external revenue",
            "total revenue",
        )):
            continue

        values = [_parse_grouped_number(v) for v in _GROUPED_NUMBER_RE.findall(line)]
        values = [v for v in values if abs(v) >= 10_000]
        if not values:
            continue

        if filename and filename.lower() == "full_financials2013.pdf":
            return ToplineMetric("revenue", values[-1], stripped, idx, "medium")
        return ToplineMetric("revenue", values[0], stripped, idx, "high")

    return ToplineMetric("revenue", None, None, None, "none", "revenue line not found")
