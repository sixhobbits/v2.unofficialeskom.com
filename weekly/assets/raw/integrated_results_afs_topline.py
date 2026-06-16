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
    Extracts key income statement lines (revenue, EBITDA, net profit, etc.)
    from final annual Eskom group AFS PDFs using pdfplumber structured
    extraction. One row per metric per PDF. Interim and Nqaba Finance PDFs
    are excluded.

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
    - name: error
      type: VARCHAR
@bruin """

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from eskom_portal.afs_income_statement import extract_income_statement
from eskom_portal.integrated_results import infer_financial_year, is_annual_afs_filename

DB_PATH = (
    Path(__file__).resolve().parents[3]
    / "warehouse" / "media_presentations" / "index.duckdb"
)


def materialize() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT content_hash, pdf_url, filename, pdf_path
            FROM raw.integrated_results
            WHERE pdf_path IS NOT NULL
        """).fetchall()
    finally:
        con.close()

    out = []
    for content_hash, pdf_url, filename, pdf_path in rows:
        if not is_annual_afs_filename(filename):
            continue

        financial_year = infer_financial_year(filename)
        period_end = date(financial_year, 3, 31) if financial_year else None

        if not Path(pdf_path).exists():
            out.append({
                "content_hash": content_hash,
                "pdf_url": pdf_url,
                "filename": filename,
                "financial_year": financial_year,
                "period_end": period_end,
                "metric": None,
                "value_rm": None,
                "error": "pdf_path not found on disk",
            })
            continue

        try:
            metrics = extract_income_statement(pdf_path)
        except Exception as exc:
            out.append({
                "content_hash": content_hash,
                "pdf_url": pdf_url,
                "filename": filename,
                "financial_year": financial_year,
                "period_end": period_end,
                "metric": None,
                "value_rm": None,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        if not metrics:
            out.append({
                "content_hash": content_hash,
                "pdf_url": pdf_url,
                "filename": filename,
                "financial_year": financial_year,
                "period_end": period_end,
                "metric": None,
                "value_rm": None,
                "error": "no income statement found",
            })
            continue

        for metric_name, value in metrics.items():
            out.append({
                "content_hash": content_hash,
                "pdf_url": pdf_url,
                "filename": filename,
                "financial_year": financial_year,
                "period_end": period_end,
                "metric": metric_name,
                "value_rm": value,
                "error": None,
            })

    return pd.DataFrame(out, columns=[
        "content_hash", "pdf_url", "filename", "financial_year", "period_end",
        "metric", "value_rm", "error",
    ])
