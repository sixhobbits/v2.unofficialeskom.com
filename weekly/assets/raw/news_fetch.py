""" @bruin
name: raw.news_fetch
connection: eskom_weekly
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

description: |
    Fresh fetch of Eskom media statement articles from the paginated
    /category/news/ index. Crawls listing pages, fetches each article,
    extracts article metadata and text, and returns one row per advertised
    article for this run.

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: article_url
      type: VARCHAR
    - name: canonical_url
      type: VARCHAR
    - name: title
      type: VARCHAR
    - name: published_at
      type: TIMESTAMP
    - name: modified_at
      type: TIMESTAMP
    - name: category
      type: VARCHAR
    - name: og_image_url
      type: VARCHAR
    - name: text_content
      type: VARCHAR
    - name: text_length
      type: BIGINT
    - name: links_json
      type: VARCHAR
    - name: media_urls_json
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

import pandas as pd

from eskom_portal.news import fetch_news


def _bruin_var(name: str, default: str) -> str:
    return json.loads(os.environ.get("BRUIN_VARS", "{}")).get(name, default)


def _optional_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _load_known_urls() -> set[str]:
    """Return article URLs already in news_content (empty set if table doesn't exist yet)."""
    import duckdb
    from pathlib import Path
    db_path = Path(__file__).resolve().parents[3] / "warehouse" / "media_presentations" / "index.duckdb"
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        rows = con.execute("SELECT article_url FROM raw.news_content WHERE article_url IS NOT NULL").fetchall()
        con.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


def materialize() -> pd.DataFrame:
    page_url = _bruin_var("news_url", "https://www.eskom.co.za/category/news/")
    max_pages = _optional_int(_bruin_var("news_max_pages", ""))
    known_urls = _load_known_urls()
    if known_urls:
        print(f"  {len(known_urls)} articles already in news_content — will stop early.", flush=True)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    rows = []
    for rec in fetch_news(page_url, max_pages=max_pages, known_urls=known_urls):
        rows.append({"scraped_at": now, **rec})
    df = pd.DataFrame(rows, columns=[
        "scraped_at", "article_url", "canonical_url", "title",
        "published_at", "modified_at", "category", "og_image_url",
        "text_content", "text_length", "links_json", "media_urls_json",
        "content_hash", "byte_size", "http_status", "error",
    ])
    for column in ("published_at", "modified_at"):
        df[column] = pd.to_datetime(df[column], errors="coerce", utc=True).dt.tz_localize(None)
    return df
