""" @bruin
name: raw.demand_capacity_legacy_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

depends:
    - raw.demand_capacity_csv_fetch

description: |
    Reads demand_side_hourly_demand_and_available_capacity from the legacy
    eskom_metrics_extra.sqlite (built once-off from local CSV snapshots by
    scripts/build_eskom_metrics_extra.py). Coverage is hourly from
    2022-10-12 through 2026-03-01 (the day Eskom's CSV link broke).
    Overwritten on every run.

    Depends on the demand_capacity_csv fetch only to serialise DuckDB writes.

columns:
    - name: timestamp
      type: TIMESTAMP
    - name: series
      type: VARCHAR
    - name: value
      type: DOUBLE
@bruin """

import sqlite3
from pathlib import Path

import pandas as pd

LEGACY_DB = (
    Path(__file__).resolve().parents[4]
    / "sources" / "eskom_metrics_extra.sqlite"
)
TABLE = "demand_side_hourly_demand_and_available_capacity"
TIMESTAMP_COL = "DateTimeKey"


def materialize() -> pd.DataFrame:
    con = sqlite3.connect(LEGACY_DB)
    df = pd.read_sql(f"SELECT * FROM {TABLE}", con)  # noqa: S608
    con.close()
    df = df.rename(columns={TIMESTAMP_COL: "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    value_cols = [c for c in df.columns if c != "timestamp"]
    out = df.melt(
        id_vars=["timestamp"], value_vars=value_cols,
        var_name="series", value_name="value",
    )
    out = out.dropna(subset=["value", "timestamp"])
    return out[["timestamp", "series", "value"]]
