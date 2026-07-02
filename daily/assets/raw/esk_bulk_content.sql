/* @bruin
name: raw.esk_bulk_content
type: duckdb.sql

description: |
    Deduplicated ESK bulk content store. PK = (timestamp, series); value is
    updated on merge, so when a monthly ESK re-export REVISES an hour (Eskom
    restates recent actuals), the corrected value lands here instead of being
    silently discarded — matching the INSERT OR REPLACE semantics of the
    sqlite rebuild upstream. Rows absent from the source are kept (merge never
    deletes), so history the portal no longer serves survives.

materialization:
    type: table
    strategy: merge

depends:
    - raw.esk_bulk_fetch

columns:
    - name: timestamp
      type: TIMESTAMP
      primary_key: true
      checks:
          - name: not_null
    - name: series
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: value
      type: DOUBLE
      update_on_merge: true
@bruin */

SELECT timestamp, series, value
FROM raw.esk_bulk_fetch
