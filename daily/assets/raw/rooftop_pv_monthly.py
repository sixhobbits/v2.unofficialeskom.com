""" @bruin
name: raw.rooftop_pv_monthly
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

depends:
    - raw.weekly_system_status_pdf_content

description: |
    Provincial rooftop PV installed capacity (monthly), parsed from each NTCSA
    Weekly System Status Report's page-5 table. When multiple reports cover the
    same observation month, the report with the latest post_date wins for that
    month — newer reports may revise older figures.

columns:
    - name: observation_date
      type: DATE
    - name: province
      type: VARCHAR
    - name: installed_mw
      type: DOUBLE
    - name: source_report
      type: VARCHAR
@bruin """

from pathlib import Path

import duckdb
import pandas as pd

from eskom_portal.weekly_status_report import parse_rooftop_section

DB_PATH = Path(__file__).resolve().parents[3] / "warehouse" / "eskom.duckdb"


def materialize() -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # Order: newest report first — first parse wins for each (date, province)
        df = conn.sql(
            "SELECT report_name, post_date, text_content "
            "FROM raw.weekly_system_status_pdf_content "
            "WHERE text_content IS NOT NULL "
            "ORDER BY post_date DESC, report_name DESC"
        ).df()

    seen: set[tuple] = set()
    rows: list[dict] = []
    for _, r in df.iterrows():
        try:
            parsed = parse_rooftop_section(r["text_content"])
        except RuntimeError:
            continue
        for obs_date, province, mw in parsed:
            key = (obs_date, province)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "observation_date": obs_date,
                "province":         province,
                "installed_mw":     mw,
                "source_report":    r["report_name"],
            })
    return pd.DataFrame(rows, columns=["observation_date", "province",
                                       "installed_mw", "source_report"])
