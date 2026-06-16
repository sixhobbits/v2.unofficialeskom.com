""" @bruin
name: raw.uclf_oclf_trend_powerbi_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.uclf_oclf_trend_csv_fetch

description: |
    Fresh fetch of the PowerBI report embedded in the outage-performance
    Hourly UCLF+OCLF Trend page. Holds only THIS run's scrape; downstream
    SQL splits into the _scrapes log and the deduped _content store.

    The iframe exposes a rolling "past 14 days" window of the combined
    Hourly UCLF+OCLF (MW) series — the freshest official source for this
    metric, ~1 day behind. Sits alongside the CSV download (which carries a
    longer ~30-day window). Depends on the CSV fetch only to serialise
    DuckDB writes (single-writer).

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: visual_id
      type: VARCHAR
    - name: visual_title
      type: VARCHAR
    - name: response_hash
      type: VARCHAR
    - name: response_json
      type: VARCHAR
    - name: metadata_json
      type: VARCHAR
    - name: error
      type: VARCHAR
@bruin """

import datetime as dt
import hashlib
from typing import Any

import pandas as pd

from eskom_portal.powerbi_scrape import fetch_responses

PAGE_URL = "https://www.eskom.co.za/dataportal/outage-performance/hourly-uclfoclf-trend/"


def materialize() -> pd.DataFrame:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    fetched = fetch_responses(PAGE_URL)

    rows: list[dict[str, Any]] = []
    for v in fetched["visuals"]:
        h = (
            hashlib.sha256(v["response_json"].encode("utf-8")).hexdigest()
            if v["response_json"] else None
        )
        rows.append({
            "scraped_at":    now,
            "visual_id":     v["visual_id"],
            "visual_title":  v["visual_title"],
            "response_hash": h,
            "response_json": v["response_json"],
            "metadata_json": fetched["metadata_json"] if v["response_json"] else None,
            "error":         v["error"] or fetched.get("error"),
        })
    if not rows:
        rows.append({
            "scraped_at":    now,
            "visual_id":     None,
            "visual_title":  None,
            "response_hash": None,
            "response_json": None,
            "metadata_json": None,
            "error":         fetched.get("error") or "no visuals returned",
        })
    return pd.DataFrame(rows)
