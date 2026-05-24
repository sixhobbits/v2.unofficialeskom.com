/* @bruin
name: raw.station_build_up_legacy_content
type: duckdb.sql

description: |
    Deduplicated legacy content store. PK = row_hash (SHA-256 of
    timestamp|series). Insert-only — re-running after a SQLite update
    only adds new rows; existing hashes are skipped.

materialization:
    type: table
    strategy: merge

depends:
    - raw.station_build_up_legacy_fetch

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
FROM raw.station_build_up_legacy_fetch
