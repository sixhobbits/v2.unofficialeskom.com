/* @bruin
name: raw.demand_capacity_csv_content
type: duckdb.sql

description: |
    Deduplicated CSV content store for the demand+capacity feed. PK =
    content_hash. Merge strategy is insert-if-not-exists.

materialization:
    type: table
    strategy: merge

depends:
    - raw.demand_capacity_csv_fetch

columns:
    - name: content_hash
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: csv_url
      type: VARCHAR
    - name: http_status
      type: INTEGER
    - name: content_text
      type: VARCHAR
    - name: first_seen_at
      type: TIMESTAMP
@bruin */

SELECT content_hash, csv_url, http_status, content_text, scraped_at AS first_seen_at
FROM raw.demand_capacity_csv_fetch
WHERE content_hash IS NOT NULL
