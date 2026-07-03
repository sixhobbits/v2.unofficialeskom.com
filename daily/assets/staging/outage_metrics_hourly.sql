/* @bruin
name: staging.outage_metrics_hourly
tags:
    - hourly
type: duckdb.sql

description: |
    Hourly outage / demand metrics from raw.esk_bulk_content, in dashboard-ready
    units. PCLF / UCLF / OCLF are converted from MW to percentage of the hour's
    own Installed Eskom Capacity (published in the same bulk feed; ~44.0 GW in
    2017 → ~47.3 GW in 2026), so historical percentages use the fleet size of
    their day, not today's. EAF is derived as 100 - PCLF% - UCLF% - OCLF% since
    Eskom doesn't publish hourly EAF directly; it is NULL when PCLF or UCLF is
    missing (a zero-filled component would silently inflate EAF).

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
      description: "derived = 100 - PCLF% - UCLF% - OCLF%; NULL if PCLF or UCLF missing"
    - name: pclf_pct
      type: DOUBLE
    - name: uclf_pct
      type: DOUBLE
    - name: oclf_pct
      type: DOUBLE
    - name: installed_mw
      type: DOUBLE
      description: "Installed Eskom Capacity used as the MW→% denominator this hour"
    - name: residual_demand_mw
      type: DOUBLE

custom_checks:
    # The bulk feed is rebuilt from monthly ESK exports, so it routinely runs
    # weeks behind. Alarm only when it exceeds the normal monthly cadence —
    # that's how it silently went a month+ stale before (2026-06/07).
    - name: freshness_45d
      blocking: false
      description: newest bulk hour is less than 45 days old
      query: |
          SELECT CASE WHEN MAX(timestamp) > now() - INTERVAL 45 DAY THEN 1 ELSE 0 END
          FROM staging.outage_metrics_hourly
      value: 1
@bruin */

WITH src AS (
    SELECT timestamp, series, TRY_CAST(value AS DOUBLE) AS value
    FROM raw.esk_bulk_content
    WHERE series IN ('Total PCLF', 'Total UCLF', 'Total OCLF', 'Residual Demand',
                     'Installed Eskom Capacity')
      AND timestamp IS NOT NULL
),
wide AS (
    SELECT
        timestamp,
        MAX(value) FILTER (WHERE series = 'Total PCLF')                AS pclf_mw,
        MAX(value) FILTER (WHERE series = 'Total UCLF')                AS uclf_mw,
        MAX(value) FILTER (WHERE series = 'Total OCLF')                AS oclf_mw,
        MAX(value) FILTER (WHERE series = 'Installed Eskom Capacity')  AS installed_mw_raw,
        MAX(value) FILTER (WHERE series = 'Residual Demand')           AS residual_demand_mw
    FROM src
    GROUP BY 1
),
-- capacity is published for effectively every bulk hour; step-hold the last
-- known value over any stray gap so a missing denominator can't null a row
filled AS (
    SELECT
        *,
        LAST_VALUE(installed_mw_raw IGNORE NULLS)
            OVER (ORDER BY timestamp ROWS UNBOUNDED PRECEDING) AS installed_mw
    FROM wide
),
pct AS (
    SELECT
        timestamp,
        pclf_mw / installed_mw * 100 AS pclf_pct,
        uclf_mw / installed_mw * 100 AS uclf_pct,
        oclf_mw / installed_mw * 100 AS oclf_pct,
        installed_mw,
        residual_demand_mw
    FROM filled
)
SELECT
    timestamp,
    CASE
        WHEN pclf_pct IS NULL OR uclf_pct IS NULL THEN NULL
        ELSE 100 - pclf_pct - uclf_pct - COALESCE(oclf_pct, 0)
    END AS eaf_pct,
    pclf_pct,
    uclf_pct,
    oclf_pct,
    installed_mw,
    residual_demand_mw
FROM pct
ORDER BY 1
