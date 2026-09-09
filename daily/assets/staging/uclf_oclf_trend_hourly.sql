/* @bruin
name: staging.uclf_oclf_trend_hourly
tags:
    - hourly
type: duckdb.sql

description: |
    Combined hourly UCLF+OCLF (MW), preferring CSV for overlapping hours and
    using PowerBI for missing hours. Eskom can stop updating its CSV while
    the embedded report keeps advancing, so both sources are required.
    Shared by daily outages, the hourly chart tail and year-on-year outages.
    Duplicate observations within a source are averaged, matching the
    existing year-on-year transform. Remove the backup only if Eskom retires
    the PowerBI report or guarantees the CSV has identical coverage.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.uclf_oclf_trend_csv
    - raw.uclf_oclf_trend_powerbi

columns:
    - name: timestamp
      type: TIMESTAMP
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: uclf_oclf_mw
      type: DOUBLE
    - name: source
      type: VARCHAR
@bruin */

WITH unified AS (
    SELECT timestamp, value, 'trend_csv' AS source, 1 AS priority
    FROM raw.uclf_oclf_trend_csv
    WHERE series = 'Hourly UCLF+OCLF' AND timestamp IS NOT NULL AND value IS NOT NULL
    UNION ALL
    SELECT timestamp, value, 'trend_powerbi' AS source, 2 AS priority
    FROM raw.uclf_oclf_trend_powerbi
    WHERE series = 'Hourly UCLF+OCLF' AND timestamp IS NOT NULL AND value IS NOT NULL
), per_source AS (
    SELECT timestamp, source, priority, AVG(value) AS uclf_oclf_mw
    FROM unified
    GROUP BY timestamp, source, priority
)
SELECT timestamp, uclf_oclf_mw, source
FROM per_source
QUALIFY ROW_NUMBER() OVER (PARTITION BY timestamp ORDER BY priority) = 1
ORDER BY timestamp
