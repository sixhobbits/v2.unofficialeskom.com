""" @bruin
name: raw.eskom_metrics_uclf_oclf_hourly
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

description: |
    Hourly UCLF+OCLF (megawatts) from data/eskom_metrics.sqlite. Snapshot file —
    overwritten on each run.

columns:
    - name: datetime_key
      type: VARCHAR
    - name: timestamp
      type: TIMESTAMP
    - name: uclf_oclf_mw
      type: DOUBLE
    - name: source
      type: VARCHAR
@bruin """

import sqlite3
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[4] / "sources" / "eskom_metrics.sqlite"


def materialize() -> pd.DataFrame:
    with sqlite3.connect(SRC) as con:
        df = pd.read_sql(
            'SELECT "DateTimeKey" AS datetime_key, '
            '"Date Time Hour Beginning" AS ts_raw, '
            '"Hourly UCLF+OCLF" AS uclf_oclf_mw, source '
            "FROM outage_performance_hourly_uclf_oclf",
            con,
        )
    df["timestamp"] = pd.to_datetime(df["ts_raw"], errors="coerce")
    return df[["datetime_key", "timestamp", "uclf_oclf_mw", "source"]].dropna(
        subset=["timestamp"]
    )
