""" @bruin
name: raw.station_build_up_legacy_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

description: |
    Reads station_build_up and station_build_up_yesterday from the legacy
    eskom_metrics.sqlite (built by the old daily dataportal scraper on thet).
    Unions both tables, melts wide→long, and hashes each (timestamp, series)
    pair. Overwritten on every run; the content table downstream is the
    durable insert-only store.

columns:
    - name: row_hash
      type: VARCHAR
    - name: timestamp
      type: TIMESTAMP
    - name: series
      type: VARCHAR
    - name: value
      type: DOUBLE
@bruin """

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

LEGACY_DB = Path(__file__).resolve().parents[4] / "sources" / "eskom_metrics.sqlite"
SKIP_COLS = {"source", "Formatted_Date"}
TIMESTAMP_COL = "Date_Time_Hour_Beginning"


def materialize() -> pd.DataFrame:
    con = sqlite3.connect(LEGACY_DB)
    dfs = []
    for table in ("station_build_up", "station_build_up_yesterday"):
        df = pd.read_sql(f"SELECT * FROM {table}", con)  # noqa: S608
        df = df.rename(columns={TIMESTAMP_COL: "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        value_cols = [c for c in df.columns if c not in {"timestamp"} | SKIP_COLS]
        melted = df.melt(
            id_vars=["timestamp"], value_vars=value_cols,
            var_name="series", value_name="value",
        )
        dfs.append(melted)
    con.close()

    out = pd.concat(dfs, ignore_index=True)
    out = out.dropna(subset=["value"])
    out = out.drop_duplicates(subset=["timestamp", "series"], keep="last")
    out["row_hash"] = out.apply(
        lambda r: hashlib.sha256(f"{r['timestamp']}|{r['series']}".encode()).hexdigest(),
        axis=1,
    )
    return out[["row_hash", "timestamp", "series", "value"]]
