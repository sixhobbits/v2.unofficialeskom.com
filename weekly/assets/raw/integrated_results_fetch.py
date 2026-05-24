""" @bruin
name: raw.integrated_results_fetch
connection: eskom_weekly
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

description: |
    Fresh fetch of the Eskom investor integrated-results page. Lists every
    PDF link on the page, downloads each (cached on disk under
    warehouse/integrated_results/pdfs/), hashes the bytes, and returns one
    row per advertised PDF. Holds only THIS run's results. Downstream SQL
    splits into the _scrapes log and the deduped _content store keyed by
    content_hash.

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: pdf_url
      type: VARCHAR
    - name: filename
      type: VARCHAR
    - name: pdf_path
      type: VARCHAR
    - name: content_hash
      type: VARCHAR
    - name: byte_size
      type: BIGINT
    - name: http_status
      type: INTEGER
    - name: error
      type: VARCHAR
@bruin """

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd

from eskom_portal.media_room import fetch_pdfs

# PDFs cached in the project warehouse.
# parents[0]=raw, [1]=assets, [2]=weekly, [3]=unofficialeskom_v2
PDF_DIR = (
    Path(__file__).resolve().parents[3]
    / "warehouse" / "integrated_results" / "pdfs"
)


def _bruin_var(name: str, default: str) -> str:
    return json.loads(os.environ.get("BRUIN_VARS", "{}")).get(name, default)


def materialize() -> pd.DataFrame:
    page_url = _bruin_var(
        "integrated_results_url",
        "https://www.eskom.co.za/investors/integrated-results/",
    )
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    rows = []
    for rec in fetch_pdfs(page_url, PDF_DIR):
        rows.append({"scraped_at": now, **rec})
    return pd.DataFrame(rows, columns=[
        "scraped_at", "pdf_url", "filename", "pdf_path",
        "content_hash", "byte_size", "http_status", "error",
    ])
