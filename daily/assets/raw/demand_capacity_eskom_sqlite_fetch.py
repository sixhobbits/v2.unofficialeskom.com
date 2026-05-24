""" @bruin
name: raw.demand_capacity_eskom_sqlite_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

depends:
    - raw.demand_capacity_csv_fetch

description: |
    Derives Available Capacity from eskom.sqlite (built from the ESK*.csv
    bulk exports). Eskom doesn't publish "available capacity" in the bulk
    CSV directly, but it's derivable from columns that are present:

        Available Capacity Incl Non Comm Units
          = Installed Eskom Capacity
            - (Total PCLF + Total UCLF + Total OCLF)
            + Non Comm Sentout

    Covers ~2017-04 through to the bulk file's last refresh date (currently
    2026-04-30), which fills the March–April 2026 gap left by the broken
    demand-side CSV scrape.

    Depends on the demand_capacity_csv fetch only to serialise DuckDB
    writes (single-writer).

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


def _to_float(series: pd.Series) -> pd.Series:
    """eskom.sqlite stores numeric columns as strings ('5577.0', '014', etc).
    Coerce; invalid → NaN."""
    return pd.to_numeric(series, errors="coerce")


def materialize() -> pd.DataFrame:
    con = sqlite3.connect(ESK_DB)
    df = pd.read_sql(
        'SELECT "Date Time Hour Beginning" AS ts, '
        '       "Installed Eskom Capacity" AS installed, '
        '       "Total PCLF" AS pclf, '
        '       "Total UCLF" AS uclf, '
        '       "Total OCLF" AS oclf, '
        '       "Non Comm Sentout" AS non_comm, '
        '       "Residual Demand" AS demand, '
        '       "RSA Contracted Demand" AS contracted '
        "FROM eskom",
        con,
    )
    con.close()

    df["timestamp"] = pd.to_datetime(df["ts"], errors="coerce")
    for col in ("installed", "pclf", "uclf", "oclf", "non_comm", "demand", "contracted"):
        df[col] = _to_float(df[col])

    available = (
        df["installed"].fillna(0)
        - df["pclf"].fillna(0)
        - df["uclf"].fillna(0)
        - df["oclf"].fillna(0)
        + df["non_comm"].fillna(0)
    )
    # Only emit available where the inputs are mostly present (installed +
    # at least one outage column non-null). Otherwise the subtraction would
    # be meaningless.
    has_inputs = df["installed"].notna() & (
        df["pclf"].notna() | df["uclf"].notna() | df["oclf"].notna()
    )
    available = available.where(has_inputs)

    # Headroom = Installed - PCLF - UCLF - OCLF - Residual Demand (no
    # non-comm). Matches the legacy formula from the old project's
    # Metabase queries — defines "spare MW above current demand".
    headroom = (
        df["installed"].fillna(0)
        - df["pclf"].fillna(0)
        - df["uclf"].fillna(0)
        - df["oclf"].fillna(0)
        - df["demand"].fillna(0)
    )
    has_headroom_inputs = has_inputs & df["demand"].notna()
    headroom = headroom.where(has_headroom_inputs)

    long_rows = []
    long_rows.append(pd.DataFrame({
        "timestamp": df["timestamp"],
        "series": "Available Capacity Incl Non Comm Units",
        "value": available,
    }))
    long_rows.append(pd.DataFrame({
        "timestamp": df["timestamp"],
        "series": "Residual Demand",
        "value": df["demand"],
    }))
    long_rows.append(pd.DataFrame({
        "timestamp": df["timestamp"],
        "series": "RSA Contracted Demand",
        "value": df["contracted"],
    }))
    long_rows.append(pd.DataFrame({
        "timestamp": df["timestamp"],
        "series": "Headroom (derived)",
        "value": headroom,
    }))
    out = pd.concat(long_rows, ignore_index=True)
    out = out.dropna(subset=["timestamp", "value"])
    return out[["timestamp", "series", "value"]]
