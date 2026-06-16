""" @bruin
name: staging.esp_loadshedding_daily
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

tags:
    - hourly

depends:
    - raw.esp_loadshedding_fetch

description: |
    Daily max loadshedding stage from the EskomSePush history.
    Forward-fills stage-change events across all days from the first
    recorded event to today, so every calendar date has an entry.
    Used for the ECharts calendar heatmap on the Heatmap page.

columns:
    - name: date
      type: DATE
    - name: max_stage
      type: INTEGER
@bruin """

import datetime
from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(__file__).resolve().parents[3] / "warehouse" / "eskom.duckdb"


def materialize() -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        rows = conn.execute(
            "SELECT event_at, stage FROM raw.esp_loadshedding_fetch ORDER BY event_at"
        ).fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "max_stage"])

    events = pd.DataFrame(rows, columns=["event_at", "stage"])
    events["event_at"] = pd.to_datetime(events["event_at"])
    events = events.sort_values("event_at").reset_index(drop=True)

    # Group events by calendar date (local — data uses SAST but stored without tz)
    events["_date"] = events["event_at"].dt.date
    events_by_date: dict = {
        d: grp.sort_values("event_at")
        for d, grp in events.groupby("_date")
    }

    first_date = events["_date"].min()
    today = datetime.date.today()
    all_dates = pd.date_range(first_date, today, freq="D").date

    records = []
    current_stage = 0
    for d in all_dates:
        day_grp = events_by_date.get(d)
        if day_grp is not None:
            day_stages = [current_stage] + list(day_grp["stage"])
            current_stage = int(day_grp.iloc[-1]["stage"])
        else:
            day_stages = [current_stage]
        records.append({"date": d, "max_stage": int(max(day_stages))})

    df = pd.DataFrame(records, columns=["date", "max_stage"])
    print(
        f"  esp_loadshedding_daily: {len(df)} days "
        f"({df['date'].min()} – {df['date'].max()}), "
        f"peak stage {df['max_stage'].max()}",
        flush=True,
    )
    return df
