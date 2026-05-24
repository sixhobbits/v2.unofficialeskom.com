""" @bruin
name: raw.weekly_system_status_pdf_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.weekly_capacity_breakdown_powerbi_fetch

description: |
    Fresh fetch of NTCSA Weekly System Status Reports advertised in their WP
    REST feed. For each PDF: downloads it to _rooftop_pdf_cache/ (skipped if
    cached), runs pdftotext, hashes the text, returns one row per advertised
    report. The deduped _content store keys on content_hash.

    Depends on the weekly powerbi fetch only to serialise DuckDB writes.

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: report_name
      type: VARCHAR
    - name: pdf_url
      type: VARCHAR
    - name: post_date
      type: VARCHAR
    - name: content_hash
      type: VARCHAR
    - name: text_content
      type: VARCHAR
    - name: error
      type: VARCHAR
@bruin """

import datetime as dt
from pathlib import Path

import pandas as pd

from eskom_portal.weekly_status_report import fetch_reports

# _rooftop_pdf_cache/ lives at the project root (one level above eskom_scraper_1-4)
CACHE_DIR = Path(__file__).resolve().parents[3] / "_rooftop_pdf_cache"


def materialize() -> pd.DataFrame:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    rows = []
    for rep in fetch_reports(CACHE_DIR):
        rows.append({
            "scraped_at":   now,
            "report_name":  rep["name"],
            "pdf_url":      rep["url"],
            "post_date":    rep["post_date"],
            "content_hash": rep["content_hash"],
            "text_content": rep["text_content"],
            "error":        rep["error"],
        })
    return pd.DataFrame(rows, columns=[
        "scraped_at", "report_name", "pdf_url", "post_date",
        "content_hash", "text_content", "error",
    ])
