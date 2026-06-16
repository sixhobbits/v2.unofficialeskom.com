""" @bruin
name: raw.uclf_oclf_trend_csv
tags:
    - hourly
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.uclf_oclf_trend_csv_content

description: |
    Parsed Hourly UCLF+OCLF Trend points, decoded from
    raw.uclf_oclf_trend_csv_content. Series: 'Hourly UCLF+OCLF' (combined, MW).
    One row per (content_hash, timestamp, series).

columns:
    - name: content_hash
      type: VARCHAR
    - name: timestamp
      type: TIMESTAMP
    - name: series
      type: VARCHAR
    - name: value
      type: DOUBLE
@bruin """

import csv
import io
from pathlib import Path

import duckdb
import pandas as pd

from eskom_portal.csv_scrape import (  # noqa: F401 — pure-Python parser helpers
    _choose_axis_column, _looks_like_html, _parse_axis, _parse_number,
    _sniff_delimiter,
)

DB_PATH = Path(__file__).resolve().parents[3] / "warehouse" / "eskom.duckdb"


def _parse_one(content_text: str) -> list[dict]:
    if not content_text or _looks_like_html(content_text):
        return []
    delimiter = _sniff_delimiter(content_text)
    reader = csv.DictReader(io.StringIO(content_text), delimiter=delimiter)
    headers = [h.strip() for h in (reader.fieldnames or []) if h is not None]
    axis_col = _choose_axis_column(headers)
    rows = []
    for raw_row in reader:
        ts = _parse_axis(raw_row.get(axis_col)) if axis_col else None
        for h in headers:
            if h == axis_col:
                continue
            v = _parse_number(raw_row.get(h), delimiter)
            if v is None:
                continue
            rows.append({"timestamp": ts, "series": h, "value": v})
    return rows


def materialize() -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        content = conn.sql(
            "SELECT content_hash, content_text FROM raw.uclf_oclf_trend_csv_content"
        ).df()

    out = []
    for _, r in content.iterrows():
        for parsed in _parse_one(r["content_text"]):
            out.append({"content_hash": r["content_hash"], **parsed})
    return pd.DataFrame(out, columns=["content_hash", "timestamp", "series", "value"])
