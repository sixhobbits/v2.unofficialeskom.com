""" @bruin
name: raw.portal_powerbi_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.portal_csv_fetch

description: |
    Generic PowerBI scrape across EVERY graph in eskom_portal.catalog.
    PORTAL_GRAPHS — one row per (graph, visual), holding THIS run's responses.
    Re-discovers each page's embedded PowerBI report and queries its visuals.
    Downstream SQL splits into the _scrapes log and the deduped _content store;
    raw.portal_powerbi parses it.

    Companion to raw.portal_csv_fetch — together they back the Eskom Source Data
    catalogue (fresh links + freshness for every graph). The hand-tuned per-graph
    chains stay authoritative for the dashboard. Depends on the CSV sweep only
    to serialise DuckDB writes.

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
    - name: embed_url
      type: VARCHAR
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

import pandas as pd

from eskom_portal.catalog import PORTAL_GRAPHS
from eskom_portal.powerbi_scrape import fetch_responses


def materialize() -> pd.DataFrame:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    rows: list[dict] = []
    for g in PORTAL_GRAPHS:
        try:
            fetched = fetch_responses(g["page_url"])
            visuals = fetched.get("visuals", [])
            metadata_json = fetched.get("metadata_json")
            embed_url = fetched.get("embed_url")
            page_error = fetched.get("error")
        except Exception as exc:  # never let one page kill the whole sweep
            visuals, metadata_json, embed_url, page_error = [], None, None, f"{type(exc).__name__}: {exc}"

        emitted = False
        for v in visuals:
            rj = v.get("response_json")
            h = hashlib.sha256(rj.encode("utf-8")).hexdigest() if rj else None
            rows.append({
                "scraped_at":    now,
                "slug":          g["slug"],
                "section":       g["section"],
                "name":          g["name"],
                "page_url":      g["page_url"],
                "embed_url":     embed_url,
                "visual_id":     v.get("visual_id"),
                "visual_title":  v.get("visual_title"),
                "response_hash": h,
                "response_json": rj,
                "metadata_json": metadata_json if rj else None,
                "error":         v.get("error") or page_error,
            })
            emitted = True
        if not emitted:
            rows.append({
                "scraped_at":    now,
                "slug":          g["slug"],
                "section":       g["section"],
                "name":          g["name"],
                "page_url":      g["page_url"],
                "embed_url":     embed_url,
                "visual_id":     None,
                "visual_title":  None,
                "response_hash": None,
                "response_json": None,
                "metadata_json": None,
                "error":         page_error or "no visuals returned",
            })
    return pd.DataFrame(rows)
