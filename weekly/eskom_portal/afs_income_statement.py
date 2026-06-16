"""Extract key income statement lines from Eskom AFS PDFs.

Uses extract_text(layout=True) which correctly handles overlapping-font PDFs
(2024+) where pdfplumber's extract_words() misses current-year columns.
"""
from __future__ import annotations
import re
from typing import Any

import pdfplumber


def _parse_rm(s: str) -> int | None:
    """Parse 'R millions' strings: '340 895' → 340895, '(55 015)' → -55015."""
    s = s.strip().replace('\xa0', ' ')
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    s = re.sub(r'[\s,]', '', s)
    if not s.lstrip('-').isdigit():
        return None
    return -int(s) if neg else int(s)


_LABEL_MAP = [
    (['revenue'], 'revenue'),
    (['primary energy'], 'primary_energy'),
    (['employee benefit expense', 'net employee benefit expense'], 'employee_costs'),
    (['other expenses', 'other operating expenses'], 'other_expenses'),
    (['ebitda', 'profit before depreciation'], 'ebitda'),
    (['depreciation and amortisation'], 'depreciation'),
    (['finance income'], 'finance_income'),
    (['finance cost'], 'finance_cost'),
    (['loss before tax', 'profit before tax', 'profit/(loss) before tax',
      'loss/(profit) before tax'], 'profit_before_tax'),
    (['income tax'], 'income_tax'),
    (['loss for the year', 'profit for the year', 'profit/(loss) for the year',
      'loss/(profit) for the year'], 'net_profit'),
]


def _first_value_from_line(line: str) -> int | None:
    """Extract Group current year (leftmost data column) from an IS text line.

    Handles:
    - Note ref (1-2d) + 2+ spaces + values: "31  295 814 ..." → 295814
    - Note ref + single space + 6-digit (3+3): "32 163 395 ..." → 163395
    - 2+3 values without note ref: "32 813 36 816 ..." → 32813
    - Column separator (2+ spaces) before next value: "888  5 151 ..." → 888
    - Negative values in parens: "(55 015) ..." → -55015
    """
    # Find first digit; back up one if preceded by '(' to include negative-number paren.
    m_start = re.search(r'\d', line)
    if not m_start:
        return None
    start = m_start.start()
    if start > 0 and line[start - 1] == '(':
        start -= 1
    data = line[start:]

    # Strip note ref (1-2 digits) when followed by 2+ spaces
    m_note = re.match(r'^(\d{1,2})\s{2,}(.*)', data)
    if m_note:
        data = m_note.group(2)

    # Value followed by column separator (2+ spaces) AND more data after it.
    # Handles "888  5 151" → 888; "4 617  200" → 4617.
    # The "remaining starts with digit/paren" guard prevents trailing-space false matches.
    m_col = re.match(r'^(\(?\d[\d ]*?\d\)?)\s{2,}', data)
    if not m_col:
        m_col = re.match(r'^(\(?\d\)?)\s{2,}', data)  # single digit before col gap
    if m_col and re.match(r'[\d(]', data[m_col.end():]):
        v = _parse_rm(m_col.group(1))
        if v is not None:
            return v

    # 6-digit value (3+3): "340 895", "(173 729)", "163 395"
    # Only matches when second group is 3 digits — so "32 163" won't be returned
    # if followed by another 3-digit group (greedy search gets leftmost 3+3 pair)
    m = re.search(r'\(?\d{3} \d{3}\)?', data)
    if m:
        return _parse_rm(m.group())

    # 5-digit value (2+3): "99 038", "(55 015)", "32 813"
    m = re.search(r'\(?\d{2} \d{3}\)?', data)
    if m:
        return _parse_rm(m.group())

    # 4-digit value (1+3): "5 137", "(3 245)"
    m = re.search(r'\(?\d{1} \d{3}\)?', data)
    if m:
        return _parse_rm(m.group())

    return None


def _find_income_stmt_page(pdf: pdfplumber.PDF) -> tuple[Any, float]:
    """Return (page, x_min) for the income statement page.

    x_min > 0 for combined balance-sheet + income-statement pages (2021-2023):
    the income statement lives in the right half of the page.
    Returns (None, 0) if no suitable page found.
    """
    for page in pdf.pages:
        text = page.extract_text() or ''
        if 'Revenue' not in text:
            continue
        if not re.search(r'\d{3} \d{3}', text):
            continue
        bs_markers = (
            'Statements of financial position' in text
            or 'STATEMENTS OF FINANCIAL POSITION' in text
            or 'STATEMENT OF FINANCIAL POSITION' in text
        )
        is_markers = (
            'Income statement' in text
            or 'INCOME STATEMENT' in text
            or 'Statement of comprehensive income' in text
            or 'STATEMENT OF COMPREHENSIVE INCOME' in text
        )
        if not is_markers and not bs_markers:
            continue
        if bs_markers:
            return page, page.width * 0.45
        return page, 0.0
    return None, 0.0


def extract_income_statement(pdf_path: str) -> dict[str, Any]:
    """Return {metric: value_rm} for Group (consolidated) current year."""
    with pdfplumber.open(pdf_path) as pdf:
        page, x_min = _find_income_stmt_page(pdf)
        if page is None:
            return {}

        if x_min > 0:
            region = page.crop((x_min, 0, page.width, page.height))
        else:
            region = page

        text = region.extract_text(layout=True) or ''
        lines = text.splitlines()

        # Skip sub-lines that would produce wrong matches
        _SKIP_PHRASES = (
            'continuing operations',
            'discontinued operations',
            'attributable to',
            'non-controlling',
            'equity holders',
            'other comprehensive',
            'total comprehensive',
            'restated',
        )

        results: dict[str, int] = {}
        for line in lines:
            lower = line.lower()
            if any(p in lower for p in _SKIP_PHRASES):
                continue
            for patterns, metric in _LABEL_MAP:
                if metric in results:
                    continue
                if not any(p in lower for p in patterns):
                    continue
                v = _first_value_from_line(line)
                if v is not None:
                    results[metric] = v
                break

        return results
