/* @bruin
name: raw.uclf_oclf_trend_csv_content
type: duckdb.sql

description: |
    Deduplicated content store for the Hourly UCLF+OCLF Trend CSV. PK =
    content_hash. Merge strategy — duplicate hashes skipped.

materialization:
    type: table
    strategy: merge

depends:
    - raw.uclf_oclf_trend_csv_fetch

columns:
    - name: content_hash
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: csv_url
      type: VARCHAR
    - name: content_text
      type: VARCHAR
    - name: first_seen_at
      type: TIMESTAMP
@bruin */

SELECT
    content_hash,
    csv_url,
    content_text,
    scraped_at AS first_seen_at
FROM raw.uclf_oclf_trend_csv_fetch
WHERE content_hash IS NOT NULL
