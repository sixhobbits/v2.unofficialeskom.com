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

    Uses the shared CSV/PowerBI hourly series, backed by the static historical
    SQLite snapshot for hours neither live source covers.

materialization:
    type: table
    strategy: create+replace

depends:
    - staging.uclf_oclf_trend_hourly
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
    SELECT timestamp AS ts, uclf_oclf_mw, 1 AS priority
    FROM staging.uclf_oclf_trend_hourly
    UNION ALL
    -- raw TIMESTAMPTZ carries SAST wall-clock as UTC; staging is naive SAST
    SELECT timezone('UTC', timestamp) AS ts, uclf_oclf_mw, 3 AS priority
    FROM raw.eskom_metrics_uclf_oclf_hourly
    WHERE uclf_oclf_mw IS NOT NULL AND timestamp IS NOT NULL
),
-- both inputs hold one value per hour (the trend table already resolved
-- revisions), so ranking by source priority alone is deterministic
ranked AS (
    SELECT ts, uclf_oclf_mw,
           ROW_NUMBER() OVER (PARTITION BY ts ORDER BY priority, uclf_oclf_mw DESC) AS rn
    FROM unified
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
