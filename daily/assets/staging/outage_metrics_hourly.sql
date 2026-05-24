/* @bruin
name: staging.outage_metrics_hourly
type: duckdb.sql

description: |
    Hourly outage / demand metrics from raw.esk_bulk_content, in dashboard-ready
    units. PCLF / UCLF / OCLF are converted from MW to percentage of installed
    capacity (47,276 MW); Residual Demand is left in MW. EAF is derived as
    100 - PCLF% - UCLF% - OCLF% since Eskom doesn't publish hourly EAF directly.

    Only the bulk historical file publishes these series — the daily csv /
    powerbi / legacy feeds carry generation but not outage breakdown. So this
    table tracks raw.esk_bulk_content directly; layer in extra sources here if
    they start publishing them.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.esk_bulk_content

columns:
    - name: timestamp
      type: TIMESTAMP
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: eaf_pct
      type: DOUBLE
      description: "derived = 100 - PCLF% - UCLF% - OCLF%"
    - name: pclf_pct
      type: DOUBLE
    - name: uclf_pct
      type: DOUBLE
    - name: oclf_pct
      type: DOUBLE
    - name: residual_demand_mw
      type: DOUBLE
@bruin */

WITH src AS (
    SELECT timestamp, series, TRY_CAST(value AS DOUBLE) AS value
    FROM raw.esk_bulk_content
    WHERE series IN ('Total PCLF', 'Total UCLF', 'Total OCLF', 'Residual Demand')
      AND timestamp IS NOT NULL
),
wide AS (
    SELECT
        timestamp,
        MAX(value) FILTER (WHERE series = 'Total PCLF')      / 47276.0 * 100 AS pclf_pct,
        MAX(value) FILTER (WHERE series = 'Total UCLF')      / 47276.0 * 100 AS uclf_pct,
        MAX(value) FILTER (WHERE series = 'Total OCLF')      / 47276.0 * 100 AS oclf_pct,
        MAX(value) FILTER (WHERE series = 'Residual Demand')                  AS residual_demand_mw
    FROM src
    GROUP BY 1
)
SELECT
    timestamp,
    100 - COALESCE(pclf_pct, 0) - COALESCE(uclf_pct, 0) - COALESCE(oclf_pct, 0) AS eaf_pct,
    pclf_pct,
    uclf_pct,
    oclf_pct,
    residual_demand_mw
FROM wide
ORDER BY 1
