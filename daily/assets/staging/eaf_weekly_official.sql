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

    PowerBI: every stored response is a complete published snapshot whose
    four factors sum to 100 %. Per week, all four come from ONE response — the
    most recently observed one (later of first ingest and last logged scrape;
    ties on response hash) that carries all four for that week. Taking each
    factor's MAX across revisions built combinations Eskom never published
    (sums up to 104 %).

    The official-vs-derived drift alarm lives on staging.outage_metrics_daily,
    which consumes this table.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.weekly_capacity_breakdown_powerbi
    - raw.weekly_capacity_breakdown_powerbi_content
    - raw.weekly_capacity_breakdown_powerbi_scrapes
    - raw.eskom_metrics_weekly_breakdown

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
    - name: factors_sum_to_100
      description: |
          EAF + PCLF + UCLF + OCLF is 100 % (± 0.5 pp rounding) for every
          PowerBI week — the factors partition capacity, so any other sum
          means components from different revisions were mixed.
      query: |
          SELECT COUNT(*) FROM staging.eaf_weekly_official
          WHERE src = 'powerbi'
            AND ABS(eaf_pct + pclf_pct + uclf_pct + oclf_pct - 100) > 0.5
      blocking: false
      value: 0
@bruin */

WITH seen AS (
    SELECT visual_id, response_hash, MAX(seen_at) AS seen_at
    FROM (
        SELECT visual_id, response_hash, first_seen_at AS seen_at FROM raw.weekly_capacity_breakdown_powerbi_content
        UNION ALL
        SELECT visual_id, response_hash, scraped_at FROM raw.weekly_capacity_breakdown_powerbi_scrapes WHERE response_hash IS NOT NULL
    )
    GROUP BY ALL
),
-- one complete snapshot per (response, week)
snapshots AS (
    SELECT
        timezone('UTC', p.week_start)::DATE AS week_start,
        p.response_hash,
        s.seen_at,
        MAX(p.value) FILTER (WHERE p.series = 'Weekly EAF')  AS eaf_pct,
        MAX(p.value) FILTER (WHERE p.series = 'Weekly PCLF') AS pclf_pct,
        MAX(p.value) FILTER (WHERE p.series = 'Weekly UCLF') AS uclf_pct,
        MAX(p.value) FILTER (WHERE p.series = 'Weekly OCLF') AS oclf_pct
    FROM raw.weekly_capacity_breakdown_powerbi p
    LEFT JOIN seen s USING (visual_id, response_hash)
    WHERE p.week_start IS NOT NULL
    GROUP BY ALL
    HAVING COUNT(*) FILTER (WHERE p.series = 'Weekly EAF')  = 1
       AND COUNT(*) FILTER (WHERE p.series = 'Weekly PCLF') = 1
       AND COUNT(*) FILTER (WHERE p.series = 'Weekly UCLF') = 1
       AND COUNT(*) FILTER (WHERE p.series = 'Weekly OCLF') = 1
),
unified AS (
    SELECT week_start, eaf_pct, pclf_pct, uclf_pct, oclf_pct,
           'powerbi' AS src, 1 AS priority, seen_at, response_hash AS payload
    FROM snapshots
    UNION ALL
    SELECT
        week_start::DATE,
        eaf, pclf, uclf, oclf,
        'metrics_sqlite' AS src,
        2 AS priority,
        NULL,
        NULL
    FROM raw.eskom_metrics_weekly_breakdown
    WHERE week_start IS NOT NULL AND eaf IS NOT NULL
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY week_start
               ORDER BY priority, seen_at DESC NULLS LAST, payload DESC NULLS LAST
           ) AS rn
    FROM unified
    WHERE eaf_pct IS NOT NULL
)
SELECT week_start, eaf_pct, pclf_pct, uclf_pct, oclf_pct, src
FROM ranked
WHERE rn = 1
ORDER BY week_start
