""" @bruin
name: raw.eskom_metrics_eaf_monthly
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

description: |
    Monthly generation capacity breakdown (EAF, PCLF, UCLF, OCLF) sourced
    from data/eskom_metrics.sqlite. Snapshot file — overwritten on each run.

columns:
    - name: year_month
      type: INTEGER
    - name: eaf
      type: DOUBLE
    - name: pclf
      type: DOUBLE
    - name: uclf
      type: DOUBLE
    - name: oclf
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
            'SELECT "YEAR_MONTH" AS year_month, "EAF" AS eaf, "PCLF" AS pclf, '
            '"UCLF" AS uclf, "OCLF" AS oclf, source '
            "FROM monthly_generation_capacity_breakdown",
            con,
        )
    return df
