""" @bruin
name: raw.esk_bulk_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

description: |
    Reads the eskom.sqlite ESK bulk export (built from monthly CSVs via
    create_sqlite_from_csvs.sh). Covers 2017-04-01 to present. Melts
    wide→long. Overwritten on every run; esk_bulk_content is the durable
    store (merge on (timestamp, series), value updated on revision).

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

ESK_DB = Path(__file__).resolve().parents[4] / "sources" / "eskom.sqlite"
TIMESTAMP_COL = "Date Time Hour Beginning"
SKIP_COLS = {TIMESTAMP_COL}


def materialize() -> pd.DataFrame:
    con = sqlite3.connect(ESK_DB)
    df = pd.read_sql("SELECT * FROM eskom", con)  # noqa: S608
    con.close()

    # Timestamps are stored as "2017-04-01 01:00:00 AM" — pandas handles this
    df["timestamp"] = pd.to_datetime(df[TIMESTAMP_COL])
    value_cols = [c for c in df.columns if c not in SKIP_COLS and c != "timestamp"]

    melted = df.melt(
        id_vars=["timestamp"], value_vars=value_cols,
        var_name="series", value_name="value",
    )
    # source sqlite stores readings as TEXT (with '' for missing) — coerce to
    # real doubles here so downstream never needs TRY_CAST
    melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
    melted = melted.dropna(subset=["value"])
    melted = melted.drop_duplicates(subset=["timestamp", "series"], keep="last")
    return melted[["timestamp", "series", "value"]]
