""" @bruin
name: raw.portal_csv
connection: eskom_warehouse
tags:
    - hourly
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.portal_csv_content

description: |
    Parsed generic portal CSV points, decoded from raw.portal_csv_content.
    Pure transform — no HTTP. One row per (slug, content_hash, timestamp,
    series). timestamp is NULL for non-temporal datasets (e.g. installed-
    capacity snapshots) — the series/value still land in the table.

columns:
    - name: slug
      type: VARCHAR
    - name: content_hash
      type: VARCHAR
    - name: timestamp
      type: TIMESTAMP
    - name: series
      type: VARCHAR
    - name: value
      type: DOUBLE
@bruin """

from pathlib import Path

import duckdb
import pandas as pd

from eskom_portal.csv_scrape import parse_csv_text, parse_ocgt_fy_csv, OCGT_FY_SLUG

DB_PATH = Path(__file__).resolve().parents[3] / "warehouse" / "eskom.duckdb"


def materialize() -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        content = conn.sql(
            "SELECT slug, content_hash, content_text FROM raw.portal_csv_content"
        ).df()

    rows: list[dict] = []
    for _, r in content.iterrows():
        # One graph's CSV encodes fiscal-year month pairs that the generic
        # parser mis-dates — give it a dedicated parser.
        parser = parse_ocgt_fy_csv if r["slug"] == OCGT_FY_SLUG else parse_csv_text
        for parsed in parser(r["content_text"]):
            rows.append({
                "slug":         r["slug"],
                "content_hash": r["content_hash"],
                "timestamp":    parsed["timestamp"],
                "series":       parsed["series"],
                "value":        parsed["value"],
            })
    return pd.DataFrame(rows, columns=["slug", "content_hash", "timestamp", "series", "value"])
