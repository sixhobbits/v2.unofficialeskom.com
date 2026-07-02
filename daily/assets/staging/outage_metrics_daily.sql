/* @bruin
name: staging.outage_metrics_daily
tags:
    - hourly
type: duckdb.sql

description: |
    Daily-averaged PCLF / UCLF / OCLF / EAF percentages, merged across three
    sources of varying freshness and grain:

      1. raw.esk_bulk_content (hourly, lags weeks — rebuilt monthly)
         - publishes Total PCLF / UCLF / OCLF in MW, all hourly.
         - highest fidelity; preferred wherever it has data.
      2. raw.uclf_oclf_trend_csv (hourly, ~1 day behind)
         - publishes combined UCLF+OCLF only, in MW. No PCLF.
         - used to refine UCLF for the recent tail (UCLF = combined - OCLF_weekly).
      3. raw.weekly_capacity_breakdown_powerbi (weekly, ~1 week behind)
         - publishes Weekly EAF / PCLF / UCLF / OCLF as percentages.
         - step-held forward to backfill PCLF / OCLF when only the trend csv has
           UCLF data, and to fill the freshest end where neither hourly source
           has anything.

    MW→% conversion uses the day's own Installed Eskom Capacity (bulk feed's
    daily average, via staging.installed_capacity_monthly for days beyond bulk
    coverage) — NOT a fixed constant; the fleet moved ~44.0→47.3 GW 2017→2026.

    EAF in this table is always derived = 100 - PCLF - UCLF - OCLF, and is NULL
    when PCLF or UCLF is missing (zero-filling a missing component would
    silently inflate EAF). installed_mw records the denominator used, so the
    dashboard's %→MW back-conversion is exactly inverse.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.esk_bulk_content
    - raw.uclf_oclf_trend_csv
    - raw.weekly_capacity_breakdown_powerbi
    - staging.installed_capacity_monthly

columns:
    - name: day
      type: DATE
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: eaf_pct
      type: DOUBLE
    - name: pclf_pct
      type: DOUBLE
    - name: uclf_pct
      type: DOUBLE
    - name: oclf_pct
      type: DOUBLE
    - name: installed_mw
      type: DOUBLE
      description: "Installed Eskom Capacity used as the MW↔% denominator this day"
    - name: pclf_src
      type: VARCHAR
    - name: uclf_src
      type: VARCHAR
    - name: oclf_src
      type: VARCHAR

custom_checks:
    # This table's tail rides the trend CSV (~1 day behind), so unlike the
    # bulk-only hourly table a tight threshold is correct here.
    - name: freshness_7d
      blocking: false
      description: newest day is less than 7 days old
      query: |
          SELECT CASE WHEN MAX(day) > (now() - INTERVAL 7 DAY)::DATE THEN 1 ELSE 0 END
          FROM staging.outage_metrics_daily
      value: 1
@bruin */

WITH cap_latest AS (
    SELECT installed_mw
    FROM staging.installed_capacity_monthly
    ORDER BY month_start DESC
    LIMIT 1
),
bulk_daily AS (
    SELECT
        timestamp::DATE AS day,
        AVG(TRY_CAST(value AS DOUBLE)) FILTER (WHERE series = 'Total PCLF') AS pclf_mw,
        AVG(TRY_CAST(value AS DOUBLE)) FILTER (WHERE series = 'Total UCLF') AS uclf_mw,
        AVG(TRY_CAST(value AS DOUBLE)) FILTER (WHERE series = 'Total OCLF') AS oclf_mw,
        AVG(TRY_CAST(value AS DOUBLE)) FILTER (WHERE series = 'Installed Eskom Capacity') AS cap_mw
    FROM raw.esk_bulk_content
    WHERE series IN ('Total PCLF', 'Total UCLF', 'Total OCLF', 'Installed Eskom Capacity')
      AND timestamp IS NOT NULL
    GROUP BY 1
),
trend_daily AS (
    SELECT
        timestamp::DATE AS day,
        AVG(value) AS uclf_oclf_combined_mw,
        COUNT(*) AS hours_covered
    FROM raw.uclf_oclf_trend_csv
    WHERE series = 'Hourly UCLF+OCLF' AND timestamp IS NOT NULL
    GROUP BY 1
    HAVING COUNT(*) >= 20  -- drop partial days (latest partial hour is incomplete)
),
weekly_long AS (
    -- one row per week-start with all four series pivoted wide
    SELECT
        week_start::DATE AS week_start,
        MAX(value) FILTER (WHERE series = 'Weekly PCLF') AS pclf_pct,
        MAX(value) FILTER (WHERE series = 'Weekly UCLF') AS uclf_pct,
        MAX(value) FILTER (WHERE series = 'Weekly OCLF') AS oclf_pct
    FROM raw.weekly_capacity_breakdown_powerbi
    GROUP BY 1
),
-- Axis = only days where at least one *hourly* source has real data. Weekly
-- snapshots are step-held to fill component gaps within this range, but they
-- can't extend the axis on their own — otherwise we'd flat-line the chart
-- forward into days where nothing measured has actually happened yet.
axis AS (
    SELECT day FROM bulk_daily
    UNION
    SELECT day FROM trend_daily
),
-- per-day MW↔% denominator: the bulk day's own capacity where bulk covers the
-- day; else the day's month from installed_capacity_monthly; else the latest
-- known month (recent tail beyond bulk coverage)
cap_for_day AS (
    SELECT
        a.day,
        COALESCE(b.cap_mw, m.installed_mw, (SELECT installed_mw FROM cap_latest)) AS installed_mw
    FROM axis a
    LEFT JOIN bulk_daily b USING (day)
    LEFT JOIN staging.installed_capacity_monthly m
           ON m.month_start = date_trunc('month', a.day)::DATE
),
-- for each day, attach the weekly snapshot whose week_start <= day, closest
weekly_for_day AS (
    SELECT a.day,
           w.pclf_pct AS w_pclf_pct,
           w.uclf_pct AS w_uclf_pct,
           w.oclf_pct AS w_oclf_pct
    FROM axis a
    LEFT JOIN LATERAL (
        SELECT pclf_pct, uclf_pct, oclf_pct
        FROM weekly_long
        WHERE week_start <= a.day
        ORDER BY week_start DESC
        LIMIT 1
    ) w ON TRUE
),
-- For UCLF: prefer bulk; else (trend_combined - weekly_oclf_step_held); else weekly_uclf_step_held
merged AS (
    SELECT
        a.day,
        c.installed_mw,
        -- PCLF
        COALESCE(b.pclf_mw / c.installed_mw * 100, w.w_pclf_pct) AS pclf_pct,
        CASE
            WHEN b.pclf_mw IS NOT NULL THEN 'bulk'
            WHEN w.w_pclf_pct IS NOT NULL THEN 'weekly'
            ELSE NULL
        END AS pclf_src,
        -- OCLF
        COALESCE(b.oclf_mw / c.installed_mw * 100, w.w_oclf_pct) AS oclf_pct,
        CASE
            WHEN b.oclf_mw IS NOT NULL THEN 'bulk'
            WHEN w.w_oclf_pct IS NOT NULL THEN 'weekly'
            ELSE NULL
        END AS oclf_src,
        -- UCLF: bulk > (trend - oclf_step) > weekly_step
        CASE
            WHEN b.uclf_mw IS NOT NULL THEN b.uclf_mw / c.installed_mw * 100
            WHEN t.uclf_oclf_combined_mw IS NOT NULL THEN
                GREATEST(t.uclf_oclf_combined_mw / c.installed_mw * 100 - COALESCE(w.w_oclf_pct, 0), 0)
            ELSE w.w_uclf_pct
        END AS uclf_pct,
        CASE
            WHEN b.uclf_mw IS NOT NULL THEN 'bulk'
            WHEN t.uclf_oclf_combined_mw IS NOT NULL THEN 'trend_csv'
            WHEN w.w_uclf_pct IS NOT NULL THEN 'weekly'
            ELSE NULL
        END AS uclf_src
    FROM axis a
    LEFT JOIN bulk_daily b USING (day)
    LEFT JOIN trend_daily t USING (day)
    LEFT JOIN weekly_for_day w USING (day)
    LEFT JOIN cap_for_day c USING (day)
)
SELECT
    day,
    CASE
        WHEN pclf_pct IS NULL OR uclf_pct IS NULL THEN NULL
        ELSE 100 - pclf_pct - uclf_pct - COALESCE(oclf_pct, 0)
    END AS eaf_pct,
    pclf_pct,
    uclf_pct,
    oclf_pct,
    installed_mw,
    pclf_src,
    uclf_src,
    oclf_src
FROM merged
WHERE pclf_pct IS NOT NULL OR uclf_pct IS NOT NULL OR oclf_pct IS NOT NULL
ORDER BY day
