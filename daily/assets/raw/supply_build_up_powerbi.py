""" @bruin
name: raw.supply_build_up_powerbi
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.supply_build_up_powerbi_content

description: |
    Parsed PowerBI points, decoded from raw.supply_build_up_powerbi_content.
    Pure transform — no HTTP. One row per (response_hash, timestamp, series).

columns:
    - name: response_hash
      type: VARCHAR
    - name: visual_id
      type: VARCHAR
    - name: visual_title
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

from eskom_portal.powerbi_scrape import decode_response

DB_PATH = Path(__file__).resolve().parents[3] / "warehouse" / "eskom.duckdb"


def materialize() -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        content = conn.sql(
            "SELECT response_hash, visual_id, visual_title, response_json, metadata_json "
            "FROM raw.supply_build_up_powerbi_content"
        ).df()

    rows: list[dict] = []
    for _, r in content.iterrows():
        for d in decode_response(r["metadata_json"], r["visual_id"], r["response_json"]):
            rows.append({
                "response_hash": r["response_hash"],
                "visual_id":     r["visual_id"],
                "visual_title":  r["visual_title"],
                "timestamp":     d["timestamp"],
                "series":        d["series"],
                "value":         d["value"],
            })
    return pd.DataFrame(rows, columns=["response_hash", "visual_id", "visual_title",
                                       "timestamp", "series", "value"])
