/* @bruin
name: staging.capacity_yoy_weekly
tags:
    - hourly
type: duckdb.sql

description: |
    Weekly-averaged available capacity (MW) keyed by (year, week) for
    year-on-year comparison on a shared Jan→Dec axis. week = 1..52, computed
    as floor((dayofyear - 1) / 7) + 1 so the same week number lands on the
    same calendar position every year; the stub 53rd week is dropped. Weeks
    with fewer than 84 hours (half a week — e.g. the broken-CSV gap or the
    current partial week) are dropped rather than averaged from a stub.

materialization:
    type: table
    strategy: create+replace

depends:
    - staging.demand_capacity_hourly

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
    - name: capacity_mw
      type: DOUBLE
@bruin */

SELECT
    strftime(timestamp, '%Y')                              AS year,
    CAST(floor((dayofyear(timestamp) - 1) / 7) + 1 AS INTEGER) AS week,
    AVG(available_capacity)                               AS capacity_mw
FROM staging.demand_capacity_hourly
WHERE available_capacity IS NOT NULL
GROUP BY 1, 2
HAVING week <= 52 AND COUNT(available_capacity) >= 84
ORDER BY 1, 2
