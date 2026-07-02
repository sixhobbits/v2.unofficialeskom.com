/* @bruin
name: staging.uclf_oclf_yoy_daily
tags:
    - hourly
type: duckdb.sql

description: |
    Daily average UCLF+OCLF as percentage of installed capacity (the day's
    month from staging.installed_capacity_monthly, latest month step-held for
    the recent tail), keyed by (year, mmdd) for year-on-year comparison
    plotting. Long-form; the dashboard pivots into per-year series.

    Unions three sources of the combined Hourly UCLF+OCLF (MW) series and
    prefers the freshest per hour:

      1. raw.uclf_oclf_trend_csv     (priority 1) — CSV download off the portal,
         rolling ~30-day window, ~1 day behind. Authoritative when present.
      2. raw.uclf_oclf_trend_powerbi (priority 2) — embedded PowerBI iframe,
         rolling 14-day window, ~1 day behind. Agrees with the CSV to the
         decimal where they overlap; backs it up if the CSV link breaks.
      3. raw.eskom_metrics_uclf_oclf_hourly (priority 3) — static snapshot
         sqlite carrying the full back-history (2022 →), frozen ~2-3 weeks
         behind. Supplies every historical year the live feeds don't reach.

    Before the CSV/PowerBI scrapers were wired in, this table read source 3
    alone and the latest year flat-lined wherever that snapshot stopped.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.uclf_oclf_trend_csv
    - raw.uclf_oclf_trend_powerbi
    - raw.eskom_metrics_uclf_oclf_hourly
    - staging.installed_capacity_monthly

columns:
    - name: year
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: mmdd
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: daily_avg_pct
      type: DOUBLE
@bruin */

WITH unified AS (
    SELECT timestamp AS ts, value AS uclf_oclf_mw, 1 AS priority
    FROM raw.uclf_oclf_trend_csv
    WHERE series = 'Hourly UCLF+OCLF' AND value IS NOT NULL AND timestamp IS NOT NULL
    UNION ALL
    SELECT timestamp AS ts, value AS uclf_oclf_mw, 2 AS priority
    FROM raw.uclf_oclf_trend_powerbi
    WHERE series = 'Hourly UCLF+OCLF' AND value IS NOT NULL AND timestamp IS NOT NULL
    UNION ALL
    SELECT timestamp AS ts, uclf_oclf_mw, 3 AS priority
    FROM raw.eskom_metrics_uclf_oclf_hourly
    WHERE uclf_oclf_mw IS NOT NULL AND timestamp IS NOT NULL
),
-- a source can carry the same hour more than once (multiple scraped content
-- versions); collapse to one value per (priority, hour) before ranking
per_source AS (
    SELECT priority, ts, AVG(uclf_oclf_mw) AS uclf_oclf_mw
    FROM unified
    GROUP BY priority, ts
),
ranked AS (
    SELECT ts, uclf_oclf_mw,
           ROW_NUMBER() OVER (PARTITION BY ts ORDER BY priority) AS rn
    FROM per_source
),
hourly AS (
    SELECT ts, uclf_oclf_mw FROM ranked WHERE rn = 1
),
daily AS (
    SELECT
        strftime(ts, '%Y')   AS year,
        strftime(ts, '%m-%d') AS mmdd,
        AVG(h.uclf_oclf_mw) / AVG(COALESCE(
            m.installed_mw,
            (SELECT installed_mw FROM staging.installed_capacity_monthly
             ORDER BY month_start DESC LIMIT 1)
        )) * 100 AS daily_avg_pct,
        COUNT(*) AS hours_covered
    FROM hourly h
    LEFT JOIN staging.installed_capacity_monthly m
           ON m.month_start = date_trunc('month', h.ts)::DATE
    GROUP BY 1, 2
)
SELECT year, mmdd, daily_avg_pct
FROM daily
WHERE hours_covered >= 20  -- drop partial days (e.g. the latest incomplete hour)
ORDER BY year, mmdd
