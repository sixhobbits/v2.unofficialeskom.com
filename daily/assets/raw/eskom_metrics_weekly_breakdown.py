""" @bruin
name: raw.eskom_metrics_weekly_breakdown
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

description: |
    Eskom's own published weekly generation capacity breakdown (Weekly EAF /
    PCLF / UCLF / OCLF, all %) sourced from sources/eskom_metrics.sqlite —
    the frozen historical snapshot (2019-04 → ~2026-05). The live continuation
    of the same portal graph is raw.weekly_capacity_breakdown_powerbi;
    staging.eaf_weekly_official merges the two. Snapshot file — overwritten
    on each run.

columns:
    - name: week_start
      type: DATE
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
            'SELECT "Week Start Date" AS week_start, "Weekly EAF" AS eaf, '
            '"Weekly PCLF" AS pclf, "Weekly UCLF" AS uclf, "Weekly OCLF" AS oclf, '
            "source FROM outage_performance_weekly_eskom_generation_capacity_breakdown",
            con,
        )
    df["week_start"] = pd.to_datetime(df["week_start"]).dt.date
    return df
