/* @bruin
name: staging.outage_metrics_daily
tags:
    - hourly
type: duckdb.sql

description: |
    Daily-averaged PCLF / UCLF / OCLF / EAF percentages, merged across three
    sources of varying freshness and grain:

      1. raw.esk_bulk_content (hourly, lags ~2 weeks)
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

    EAF in this table is always derived = 100 - PCLF - UCLF - OCLF.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.esk_bulk_content
    - raw.uclf_oclf_trend_csv
    - raw.weekly_capacity_breakdown_powerbi

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
    - name: pclf_src
      type: VARCHAR
    - name: uclf_src
      type: VARCHAR
    - name: oclf_src
      type: VARCHAR
@bruin */

WITH bulk_daily AS (
    SELECT
        timestamp::DATE AS day,
        AVG(TRY_CAST(value AS DOUBLE)) FILTER (WHERE series = 'Total PCLF') / 47276.0 * 100 AS pclf_pct,
        AVG(TRY_CAST(value AS DOUBLE)) FILTER (WHERE series = 'Total UCLF') / 47276.0 * 100 AS uclf_pct,
        AVG(TRY_CAST(value AS DOUBLE)) FILTER (WHERE series = 'Total OCLF') / 47276.0 * 100 AS oclf_pct
    FROM raw.esk_bulk_content
    WHERE series IN ('Total PCLF', 'Total UCLF', 'Total OCLF')
      AND timestamp IS NOT NULL
    GROUP BY 1
),
trend_daily AS (
    SELECT
        timestamp::DATE AS day,
        AVG(value) / 47276.0 * 100 AS uclf_oclf_combined_pct,
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
        -- PCLF
        COALESCE(b.pclf_pct, w.w_pclf_pct) AS pclf_pct,
        CASE
            WHEN b.pclf_pct IS NOT NULL THEN 'bulk'
            WHEN w.w_pclf_pct IS NOT NULL THEN 'weekly'
            ELSE NULL
        END AS pclf_src,
        -- OCLF
        COALESCE(b.oclf_pct, w.w_oclf_pct) AS oclf_pct,
        CASE
            WHEN b.oclf_pct IS NOT NULL THEN 'bulk'
            WHEN w.w_oclf_pct IS NOT NULL THEN 'weekly'
            ELSE NULL
        END AS oclf_src,
        -- UCLF: bulk > (trend - oclf_step) > weekly_step
        CASE
            WHEN b.uclf_pct IS NOT NULL THEN b.uclf_pct
            WHEN t.uclf_oclf_combined_pct IS NOT NULL THEN
                GREATEST(t.uclf_oclf_combined_pct - COALESCE(w.w_oclf_pct, 0), 0)
            ELSE w.w_uclf_pct
        END AS uclf_pct,
        CASE
            WHEN b.uclf_pct IS NOT NULL THEN 'bulk'
            WHEN t.uclf_oclf_combined_pct IS NOT NULL THEN 'trend_csv'
            WHEN w.w_uclf_pct IS NOT NULL THEN 'weekly'
            ELSE NULL
        END AS uclf_src
    FROM axis a
    LEFT JOIN bulk_daily b USING (day)
    LEFT JOIN trend_daily t USING (day)
    LEFT JOIN weekly_for_day w USING (day)
)
SELECT
    day,
    100 - COALESCE(pclf_pct, 0) - COALESCE(uclf_pct, 0) - COALESCE(oclf_pct, 0) AS eaf_pct,
    pclf_pct,
    uclf_pct,
    oclf_pct,
    pclf_src,
    uclf_src,
    oclf_src
FROM merged
WHERE pclf_pct IS NOT NULL OR uclf_pct IS NOT NULL OR oclf_pct IS NOT NULL
ORDER BY day
