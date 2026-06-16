/* @bruin
name: raw.supply_build_up_csv_scrapes
tags:
    - hourly
type: duckdb.sql

description: |
    Append-only log of every CSV scrape attempt. Each pipeline run appends
    one row from raw.supply_build_up_csv_fetch. content_text is NOT carried
    — that lives in raw.supply_build_up_csv_content keyed by content_hash.

materialization:
    type: table
    strategy: append

depends:
    - raw.supply_build_up_csv_fetch

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
    - name: error
      type: VARCHAR
@bruin */

SELECT
    scraped_at,
    page_url,
    csv_url,
    http_status,
    content_hash,
    error
FROM raw.supply_build_up_csv_fetch
