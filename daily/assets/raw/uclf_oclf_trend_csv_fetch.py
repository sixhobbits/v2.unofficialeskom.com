""" @bruin
name: raw.uclf_oclf_trend_csv_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.weekly_capacity_breakdown_powerbi_fetch

description: |
    Fresh fetch of the Hourly UCLF+OCLF Trend CSV (combined UCLF+OCLF only,
    no PCLF). Overwritten on every run. Holds only THIS run's response;
    downstream SQL splits into the _scrapes log and the _content store.

    Depends on the weekly powerbi fetch only to serialise DuckDB writes.

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

import pandas as pd

from eskom_portal.csv_scrape import scrape_csv

PAGE_URL = "https://www.eskom.co.za/dataportal/outage-performance/hourly-uclfoclf-trend/"


def materialize() -> pd.DataFrame:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    result = scrape_csv(PAGE_URL)
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
