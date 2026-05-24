""" @bruin
name: raw.integrated_results_afs_topline
connection: eskom_weekly
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.integrated_results

description: |
    Extracts the group revenue top line from final annual Eskom group AFS-like
    PDFs discovered on the integrated-results page. Pure transform — no HTTP.
    Interim PDFs and Nqaba Finance PDFs are excluded by filename.

columns:
    - name: content_hash
      type: VARCHAR
    - name: pdf_url
      type: VARCHAR
    - name: filename
      type: VARCHAR
    - name: financial_year
      type: INTEGER
    - name: period_end
      type: DATE
    - name: metric
      type: VARCHAR
    - name: value_rm
      type: BIGINT
    - name: source_line
      type: VARCHAR
    - name: line_number
      type: BIGINT
    - name: confidence
      type: VARCHAR
    - name: error
      type: VARCHAR
@bruin """

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from eskom_portal.integrated_results import (
    extract_revenue_topline,
    infer_financial_year,
    is_annual_afs_filename,
)

DB_PATH = (
    Path(__file__).resolve().parents[3]
    / "warehouse" / "media_presentations" / "index.duckdb"
)


def materialize() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT content_hash, pdf_url, filename, text_content
            FROM raw.integrated_results
        """).fetchall()
    finally:
        con.close()

    out = []
    for content_hash, pdf_url, filename, text_content in rows:
        if not is_annual_afs_filename(filename):
            continue

        financial_year = infer_financial_year(filename)
        metric = extract_revenue_topline(text_content, filename)
        out.append({
            "content_hash": content_hash,
            "pdf_url": pdf_url,
            "filename": filename,
            "financial_year": financial_year,
            "period_end": date(financial_year, 3, 31) if financial_year else None,
            "metric": metric.metric,
            "value_rm": metric.value_rm,
            "source_line": metric.source_line,
            "line_number": metric.line_number,
            "confidence": metric.confidence,
            "error": metric.error,
        })

    return pd.DataFrame(out, columns=[
        "content_hash", "pdf_url", "filename", "financial_year", "period_end",
        "metric", "value_rm", "source_line", "line_number", "confidence",
        "error",
    ])
