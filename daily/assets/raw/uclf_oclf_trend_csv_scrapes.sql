/* @bruin
name: raw.uclf_oclf_trend_csv_scrapes
type: duckdb.sql

description: |
    Append-only log of every Hourly UCLF+OCLF Trend CSV scrape attempt. Each
    pipeline run appends this run's row from the _fetch asset. Holds only
    log-relevant columns (no content_text) — that lives in the _content store.

materialization:
    type: table
    strategy: append

depends:
    - raw.uclf_oclf_trend_csv_fetch

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
FROM raw.uclf_oclf_trend_csv_fetch
