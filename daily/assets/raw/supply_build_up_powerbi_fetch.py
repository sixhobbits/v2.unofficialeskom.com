""" @bruin
name: raw.supply_build_up_powerbi_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.supply_build_up_csv_fetch

description: |
    Fresh fetch of the PowerBI report — overwritten on every run. Holds
    only THIS run's scrape data; downstream SQL splits it into the
    historical _scrapes log and the deduped _content store.

    One HTTP call per pipeline run. Depends on the CSV fetch only to
    serialize DuckDB writes (single-writer).

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
import json
import os
from typing import Any

import pandas as pd

from eskom_portal.powerbi_scrape import fetch_responses


def _bruin_var(name: str, default: str) -> str:
    return json.loads(os.environ.get("BRUIN_VARS", "{}")).get(name, default)


def materialize() -> pd.DataFrame:
    page_url = _bruin_var(
        "supply_build_up_page_url",
        "https://www.eskom.co.za/dataportal/supply-side/station-build-up-for-yesterday/",
    )
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    fetched = fetch_responses(page_url)

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
        # report-level failure (no iframe etc.)
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
