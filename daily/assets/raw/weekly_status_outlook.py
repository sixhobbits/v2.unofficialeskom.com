""" @bruin
name: raw.weekly_status_outlook
connection: eskom_warehouse
tags:
    - hourly
materialization:
    type: table
    strategy: create+replace

depends:
    - raw.weekly_system_status_pdf_content

description: |
    The "52 Week Outlook" adequacy table from the LATEST NTCSA Weekly System
    Status Report — one row per forecast week, with a green/yellow/orange/red
    status derived from the Likely Risk Scenario MW margin (the PDF's cell
    colours are lost by pdftotext). Re-parsed cheaply from the stored report
    text, so it can run on the hourly cadence even though a new report only
    lands weekly.

columns:
    - name: report_name
      type: VARCHAR
    - name: report_week
      type: INTEGER
    - name: report_period
      type: VARCHAR
    - name: week_start
      type: DATE
    - name: week_num
      type: INTEGER
    - name: rsa_contracted_mw
      type: INTEGER
    - name: residual_forecast_mw
      type: INTEGER
    - name: available_dispatchable_mw
      type: INTEGER
    - name: available_less_or_ua_mw
      type: INTEGER
    - name: planned_maint_mw
      type: INTEGER
    - name: unplanned_assumption_mw
      type: INTEGER
    - name: planned_risk_mw
      type: INTEGER
    - name: likely_risk_mw
      type: INTEGER
    - name: status
      type: VARCHAR
@bruin """

from pathlib import Path

import duckdb
import pandas as pd

from eskom_portal.weekly_status_report import parse_report_meta, parse_status_outlook

DB_PATH = Path(__file__).resolve().parents[3] / "warehouse" / "eskom.duckdb"

_COLUMNS = [
    "report_name", "report_week", "report_period", "week_start", "week_num",
    "rsa_contracted_mw", "residual_forecast_mw", "available_dispatchable_mw",
    "available_less_or_ua_mw", "planned_maint_mw", "unplanned_assumption_mw",
    "planned_risk_mw", "likely_risk_mw", "status",
]


def materialize() -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        latest = conn.sql(
            "SELECT report_name, text_content FROM raw.weekly_system_status_pdf_content "
            "WHERE text_content IS NOT NULL "
            "ORDER BY post_date DESC, report_name DESC LIMIT 1"
        ).fetchone()

    rows: list[dict] = []
    if latest:
        report_name, txt = latest
        meta = parse_report_meta(txt) or {}
        for wk in parse_status_outlook(txt):
            rows.append({
                "report_name":   report_name,
                "report_week":   meta.get("week"),
                "report_period": meta.get("period"),
                **wk,
            })
    return pd.DataFrame(rows, columns=_COLUMNS)
