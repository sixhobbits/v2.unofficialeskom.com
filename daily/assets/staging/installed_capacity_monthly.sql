/* @bruin
name: staging.installed_capacity_monthly
tags:
    - hourly
type: duckdb.sql

description: |
    Monthly-average Installed Eskom Capacity (MW) from the ESK bulk feed.
    Single source of truth for the MW ↔ % conversion used by the derived
    EAF / PCLF / UCLF / OCLF metrics. Installed capacity moved from ~44.0 GW
    (2017) to ~47.3 GW (2026) — Medupi/Kusile units commissioning, Komati
    closing — so converting all history with one fixed constant biases the
    loss factors (and therefore derived EAF) for earlier years.

    Consumers step-hold the latest month forward for timestamps beyond bulk
    coverage (the bulk feed lags a few weeks).

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.esk_bulk_content

columns:
    - name: month_start
      type: DATE
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: installed_mw
      type: DOUBLE
      checks:
          - name: not_null

custom_checks:
    - name: capacity_in_sane_range
      description: monthly installed capacity stays within 40–55 GW
      query: |
          SELECT COUNT(*) FROM staging.installed_capacity_monthly
          WHERE installed_mw < 40000 OR installed_mw > 55000
      value: 0
@bruin */

SELECT
    date_trunc('month', timestamp)::DATE AS month_start,
    AVG(TRY_CAST(value AS DOUBLE))       AS installed_mw
FROM raw.esk_bulk_content
WHERE series = 'Installed Eskom Capacity'
  AND timestamp IS NOT NULL
  AND TRY_CAST(value AS DOUBLE) > 0
GROUP BY 1
ORDER BY 1
