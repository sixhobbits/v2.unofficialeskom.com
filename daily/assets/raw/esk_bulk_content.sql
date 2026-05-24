/* @bruin
name: raw.esk_bulk_content
type: duckdb.sql

description: |
    Deduplicated ESK bulk content store. PK = row_hash (SHA-256 of
    timestamp|series). Insert-only — replacing the source SQLite and
    re-running only adds rows whose hashes don't already exist.

materialization:
    type: table
    strategy: merge

depends:
    - raw.esk_bulk_fetch

columns:
    - name: row_hash
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: timestamp
      type: TIMESTAMP
    - name: series
      type: VARCHAR
    - name: value
      type: DOUBLE
@bruin */

SELECT row_hash, timestamp, series, value
FROM raw.esk_bulk_fetch
