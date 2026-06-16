/* @bruin
name: staging.rooftop_pv_monthly
tags:
    - hourly
type: duckdb.sql

description: |
    Provincial rooftop PV installed capacity (monthly). Drops the "Total" row
    so the dashboard can stack provinces without double-counting.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.rooftop_pv_monthly

columns:
    - name: observation_date
      type: DATE
      primary_key: true
      checks:
          - name: not_null
    - name: province
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: installed_mw
      type: DOUBLE
@bruin */

SELECT
    observation_date,
    province,
    installed_mw
FROM raw.rooftop_pv_monthly
WHERE province <> 'Total'
ORDER BY 1, 2
