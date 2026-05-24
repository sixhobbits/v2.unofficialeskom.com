/* @bruin
name: raw.demand_capacity_csv_scrapes
type: duckdb.sql

description: |
    Append-only log of every demand+capacity CSV scrape attempt. One row per
    pipeline run. content_text is NOT carried — that lives in
    raw.demand_capacity_csv_content keyed by content_hash.

materialization:
    type: table
    strategy: append

depends:
    - raw.demand_capacity_csv_fetch

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

SELECT scraped_at, page_url, csv_url, http_status, content_hash, error
FROM raw.demand_capacity_csv_fetch
