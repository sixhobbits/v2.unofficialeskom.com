/* @bruin
name: staging.peak_demand_yoy_weekly
tags:
    - hourly
type: duckdb.sql

description: |
    Weekly PEAK demand (MW) keyed by (year, week) for year-on-year comparison
    on a shared Jan→Dec axis. peak = the highest hourly residual demand in the
    week (Eskom's "weekly peak demand" notion). week = 1..52, same scheme as
    the other *_yoy_weekly tables; the stub 53rd week is dropped, as are weeks
    with fewer than 84 hours of data.

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
    - name: peak_demand_mw
      type: DOUBLE
@bruin */

SELECT
    strftime(timestamp, '%Y')                              AS year,
    CAST(floor((dayofyear(timestamp) - 1) / 7) + 1 AS INTEGER) AS week,
    MAX(residual_demand)                                  AS peak_demand_mw
FROM staging.demand_capacity_hourly
WHERE residual_demand IS NOT NULL
GROUP BY 1, 2
HAVING week <= 52 AND COUNT(residual_demand) >= 84
ORDER BY 1, 2
