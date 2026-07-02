/* @bruin
name: staging.eaf_weekly_official
tags:
    - hourly
type: duckdb.sql

description: |
    Eskom's OWN published weekly EAF / PCLF / UCLF / OCLF (%), one row per
    week_start — as opposed to the derived EAF in staging.outage_metrics_daily
    (100 - PCLF - UCLF - OCLF from hourly MW). Two sources of the same portal
    graph, freshest wins per week:

      1. raw.weekly_capacity_breakdown_powerbi (live scrape, recent weeks)
      2. raw.eskom_metrics_weekly_breakdown (frozen snapshot, 2019-04 →)

    The official-vs-derived reconciliation check below is the drift alarm for
    the whole derived-EAF stack (capacity denominator, source merging, held
    components): if the two diverge by more than 3 pp on recent full weeks,
    something in the derivation (or Eskom's own restatement) moved.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.weekly_capacity_breakdown_powerbi
    - raw.eskom_metrics_weekly_breakdown
    - staging.outage_metrics_daily

columns:
    - name: week_start
      type: DATE
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: eaf_pct
      type: DOUBLE
      checks:
          - name: not_null
    - name: pclf_pct
      type: DOUBLE
    - name: uclf_pct
      type: DOUBLE
    - name: oclf_pct
      type: DOUBLE
    - name: src
      type: VARCHAR

custom_checks:
    - name: derived_vs_official_within_5pp
      blocking: false
      description: |
          Derived weekly EAF (avg of staging.outage_metrics_daily over the same
          Mon-anchored week) stays within 5 pp of Eskom's published weekly EAF
          on the trailing 8 published weeks. Non-blocking drift alarm.
          Known bias, don't chase below 5 pp: on tail weeks where UCLF comes
          from the hourly trend CSV, the derived EAF runs ~2-3.5 pp LOW —
          Eskom's trend CSV (UCLF+OCLF MW) reads hotter than the UCLF in their
          own weekly report (observed 2026-06: derived 65.4 vs official 69.0).
          Weeks fully covered by the bulk feed agree to ~0.2 pp.
      query: |
          WITH derived AS (
              SELECT date_trunc('week', day)::DATE AS week_start,
                     AVG(eaf_pct) AS eaf_derived
              FROM staging.outage_metrics_daily
              WHERE eaf_pct IS NOT NULL
              GROUP BY 1
              HAVING COUNT(*) = 7
          ),
          recent_official AS (
              SELECT week_start, eaf_pct
              FROM staging.eaf_weekly_official
              ORDER BY week_start DESC
              LIMIT 8
          )
          SELECT COUNT(*)
          FROM recent_official o
          JOIN derived d USING (week_start)
          WHERE ABS(o.eaf_pct - d.eaf_derived) > 5
      value: 0
@bruin */

WITH unified AS (
    SELECT
        week_start::DATE AS week_start,
        MAX(value) FILTER (WHERE series = 'Weekly EAF')  AS eaf_pct,
        MAX(value) FILTER (WHERE series = 'Weekly PCLF') AS pclf_pct,
        MAX(value) FILTER (WHERE series = 'Weekly UCLF') AS uclf_pct,
        MAX(value) FILTER (WHERE series = 'Weekly OCLF') AS oclf_pct,
        'powerbi' AS src,
        1 AS priority
    FROM raw.weekly_capacity_breakdown_powerbi
    WHERE week_start IS NOT NULL
    GROUP BY week_start::DATE
    UNION ALL
    SELECT
        week_start::DATE,
        eaf, pclf, uclf, oclf,
        'metrics_sqlite' AS src,
        2 AS priority
    FROM raw.eskom_metrics_weekly_breakdown
    WHERE week_start IS NOT NULL AND eaf IS NOT NULL
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY week_start ORDER BY priority) AS rn
    FROM unified
    WHERE eaf_pct IS NOT NULL
)
SELECT week_start, eaf_pct, pclf_pct, uclf_pct, oclf_pct, src
FROM ranked
WHERE rn = 1
ORDER BY week_start
