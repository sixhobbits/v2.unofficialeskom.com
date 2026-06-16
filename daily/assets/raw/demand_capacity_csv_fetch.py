""" @bruin
name: raw.demand_capacity_csv_fetch
tags:
    - hourly
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

description: |
    Fresh fetch of the System Hourly Demand and Available Capacity CSV from
    the Eskom data portal demand-side page. Holds only THIS run's scrape
    result. Eskom's link to this CSV is currently stale (returns 404 since
    early March 2026); this fetcher still records the attempt so we can
    notice when the upstream feed comes back.

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: page_url
      type: VARCHAR
    - name: csv_url
      type: VARCHAR
    - name: http_status
      type: INTEGER
    - name: content_hash
      type: VARCHAR
    - name: content_text
      type: VARCHAR
    - name: error
      type: VARCHAR
@bruin """

import datetime as dt
import hashlib
import json
import os

import pandas as pd

from eskom_portal.csv_scrape import scrape_csv


def _bruin_var(name: str, default: str) -> str:
    return json.loads(os.environ.get("BRUIN_VARS", "{}")).get(name, default)


def materialize() -> pd.DataFrame:
    page_url = _bruin_var(
        "demand_capacity_page_url",
        "https://www.eskom.co.za/dataportal/demand-side/system-hourly-demand-and-available-capacity/",
    )
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    result = scrape_csv(page_url)

    content_text = result["content_text"]
    content_hash = (
        hashlib.sha256(content_text.encode("utf-8")).hexdigest()
        if content_text else None
    )
    return pd.DataFrame([{
        "scraped_at":   now,
        "page_url":     result["page_url"],
        "csv_url":      result["csv_url"],
        "http_status":  result["http_status"],
        "content_hash": content_hash,
        "content_text": content_text,
        "error":        result["error"],
    }])
