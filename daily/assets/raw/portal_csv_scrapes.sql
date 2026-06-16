/* @bruin
name: raw.portal_csv_scrapes
tags:
    - hourly
type: duckdb.sql

description: |
    Append-only log of every generic portal CSV scrape attempt, one row per
    (graph, run). Holds only log-relevant columns (no content_text) — the body
    lives in raw.portal_csv_content keyed by (slug, content_hash).

materialization:
    type: table
    strategy: append

depends:
    - raw.portal_csv_fetch

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: slug
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
    - name: error
      type: VARCHAR
@bruin */

SELECT scraped_at, slug, page_url, csv_url, http_status, content_hash,
       etag, last_modified, content_length, error
FROM raw.portal_csv_fetch
