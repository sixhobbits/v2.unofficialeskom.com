/* @bruin
name: staging.uclf_oclf_yoy_daily
type: duckdb.sql

description: |
    Daily average UCLF+OCLF as percentage of installed capacity (47,276 MW),
    keyed by (year, mmdd) for year-on-year comparison plotting. Long-form;
    the dashboard pivots into per-year series.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.eskom_metrics_uclf_oclf_hourly

columns:
    - name: year
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: mmdd
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: daily_avg_pct
      type: DOUBLE
@bruin */

SELECT
    strftime(timestamp, '%Y')   AS year,
    strftime(timestamp, '%m-%d') AS mmdd,
    AVG(uclf_oclf_mw) / 47276.0 * 100 AS daily_avg_pct
FROM raw.eskom_metrics_uclf_oclf_hourly
WHERE uclf_oclf_mw IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2
