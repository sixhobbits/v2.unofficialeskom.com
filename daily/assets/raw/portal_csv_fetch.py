""" @bruin
name: raw.portal_csv_fetch
tags:
    - hourly
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.uclf_oclf_trend_powerbi_fetch

description: |
    Generic CSV scrape across EVERY graph in eskom_portal.catalog.PORTAL_GRAPHS
    — one row per graph, holding THIS run's response. Re-discovers each page's
    CSV download URL (those move over time) and stores the raw body for replay.
    Downstream SQL splits this into the _scrapes log and the deduped _content
    store; raw.portal_csv parses it.

    Sits alongside the hand-tuned per-graph chains (demand_capacity, supply_
    build_up, uclf_oclf_trend, …) which stay authoritative for the dashboard.
    This one exists to give the Eskom Source Data catalogue fresh links + a
    freshness signal for every graph, charted or not. Depends on an existing
    fetch only to serialise DuckDB writes (single-writer).

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: slug
      type: VARCHAR
    - name: section
      type: VARCHAR
    - name: name
      type: VARCHAR
    - name: page_url
      type: VARCHAR
    - name: csv_url
      type: VARCHAR
    - name: http_status
      type: INTEGER
    - name: content_hash
      type: VARCHAR
    - name: etag
      type: VARCHAR
    - name: last_modified
      type: VARCHAR
    - name: content_length
      type: VARCHAR
    - name: content_text
      type: VARCHAR
    - name: error
      type: VARCHAR
@bruin """

import datetime as dt
import hashlib

import pandas as pd

from eskom_portal.catalog import PORTAL_GRAPHS
from eskom_portal.csv_scrape import scrape_csv


def materialize() -> pd.DataFrame:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    rows: list[dict] = []
    for g in PORTAL_GRAPHS:
        etag = last_modified = content_length = None
        try:
            r = scrape_csv(g["page_url"])
            csv_url, http_status = r["csv_url"], r["http_status"]
            content_text, error = r["content_text"], r["error"]
            etag, last_modified, content_length = r["etag"], r["last_modified"], r["content_length"]
        except Exception as exc:  # never let one page kill the whole sweep
            csv_url, http_status, content_text, error = None, 0, None, f"{type(exc).__name__}: {exc}"
        content_hash = (
            hashlib.sha256(content_text.encode("utf-8")).hexdigest()
            if content_text else None
        )
        rows.append({
            "scraped_at":     now,
            "slug":           g["slug"],
            "section":        g["section"],
            "name":           g["name"],
            "page_url":       g["page_url"],
            "csv_url":        csv_url,
            "http_status":    http_status,
            "content_hash":   content_hash,
            "etag":           etag,
            "last_modified":  last_modified,
            "content_length": content_length,
            "content_text":   content_text,
            "error":          error,
        })
    return pd.DataFrame(rows)
