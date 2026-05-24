/* @bruin
name: staging.eaf_monthly
type: duckdb.sql

description: |
    Monthly EAF (Energy Availability Factor) percentage with a normalised
    timestamp. Sourced from raw.eskom_metrics_eaf_monthly.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.eskom_metrics_eaf_monthly

columns:
    - name: month_start
      type: TIMESTAMP
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: eaf_pct
      type: DOUBLE
@bruin */

SELECT
    strptime(year_month::VARCHAR || '01', '%Y%m%d') AS month_start,
    eaf AS eaf_pct
FROM raw.eskom_metrics_eaf_monthly
WHERE eaf IS NOT NULL
ORDER BY 1
