/* @bruin
name: raw.supply_build_up_csv_content
tags:
    - hourly
type: duckdb.sql

description: |
    Deduplicated CSV content store. PK = content_hash. Merge strategy is
    insert-if-not-exists — matching hashes are skipped. first_seen_at is
    set on insert and preserved.

    last_seen_at / times_seen are derivable from the scrapes log:
        SELECT content_hash, MAX(scraped_at), COUNT(*)
        FROM raw.supply_build_up_csv_scrapes GROUP BY content_hash

materialization:
    type: table
    strategy: merge

depends:
    - raw.supply_build_up_csv_fetch

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

SELECT
    content_hash,
    csv_url,
    http_status,
    content_text,
    scraped_at AS first_seen_at
FROM raw.supply_build_up_csv_fetch
WHERE content_hash IS NOT NULL
