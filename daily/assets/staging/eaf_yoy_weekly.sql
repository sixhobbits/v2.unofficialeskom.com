/* @bruin
name: staging.eaf_yoy_weekly
tags:
    - hourly
type: duckdb.sql

description: |
    Weekly-averaged EAF (Energy Availability Factor, %) keyed by (year, week)
    for year-on-year comparison plotting on a shared Jan→Dec axis. Long-form;
    the dashboard pivots into per-year series and emphasises the current year.

    week = 1..52, computed as floor((dayofyear - 1) / 7) + 1 so the same week
    number lands on the same calendar position every year. The stub 53rd week
    (day 365/366) is dropped. Source is the merged daily EAF in
    staging.outage_metrics_daily (eaf_pct = 100 - PCLF - UCLF - OCLF).

materialization:
    type: table
    strategy: create+replace

depends:
    - staging.outage_metrics_daily

columns:
    - name: year
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: week
      type: INTEGER
      primary_key: true
      checks:
          - name: not_null
    - name: eaf_pct
      type: DOUBLE
@bruin */

SELECT
    strftime(day, '%Y')                              AS year,
    CAST(floor((dayofyear(day) - 1) / 7) + 1 AS INTEGER) AS week,
    AVG(eaf_pct)                                     AS eaf_pct
FROM staging.outage_metrics_daily
WHERE eaf_pct IS NOT NULL
GROUP BY 1, 2
HAVING week <= 52
ORDER BY 1, 2
