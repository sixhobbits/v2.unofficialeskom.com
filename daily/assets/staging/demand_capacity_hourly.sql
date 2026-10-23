/* @bruin
name: staging.demand_capacity_hourly
tags:
    - hourly
type: duckdb.sql

description: |
    Hourly demand + available capacity, dashboard-ready. Unions three
    sources, prefers the freshest where they overlap.

    Source coverage:
      - legacy       2022-10-12 → 2026-03-01 (CSV snapshots from the old
                     scraper, ingested via scripts/build_eskom_metrics_extra.py)
      - eskom_sqlite 2017-04-01 → ~latest bulk-CSV refresh (currently
                     2026-04-30). Available Capacity is *derived* from
                     Installed - PCLF - UCLF - OCLF + Non Comm Sentout.
      - csv          empty while Eskom's CSV link is 404 (since Mar 2026)
      - powerbi      last ~5–7 days (rolling window the iframe exposes)

    Source priority per (timestamp, metric):
        csv > powerbi > eskom_sqlite > legacy
    csv first because it's authoritative when available; powerbi second
    because it's the freshest official source; eskom_sqlite third because
    it fills the broken-CSV gap with derived values; legacy last because
    it stops mid-Feb-2026 and overlaps everything else. Within csv and
    powerbi the most recently observed payload wins (later of first ingest
    and last logged scrape; ties on payload hash).

    timestamp is the SAST wall-clock hour beginning (naive TIMESTAMP). The
    raw TIMESTAMPTZ columns carry SAST wall-clock as UTC, so they convert
    with timezone('UTC', …); a bare ::TIMESTAMP cast would apply the
    session zone (Europe/Berlin on thet) and shift every hour by 1–2 h.

    Series mapping (canonical → upstream variations):
      - available_capacity        ← "Available Capacity Incl Non Comm Units"
      - available_capacity_re     ← "Available_Capacity_Incl_Non_Comm_Units_Incl_Total_RE"
                                     (CSV underscored) or "...Incl Total RE" (PowerBI)
      - residual_demand           ← "Residual Demand"
      - contracted_demand         ← "RSA Contracted Demand"

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.demand_capacity_csv
    - raw.demand_capacity_csv_content
    - raw.demand_capacity_csv_scrapes
    - raw.demand_capacity_powerbi
    - raw.demand_capacity_powerbi_content
    - raw.demand_capacity_powerbi_scrapes
    - raw.demand_capacity_eskom_sqlite_fetch
    - raw.demand_capacity_legacy_fetch

columns:
    - name: timestamp
      type: TIMESTAMP
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: available_capacity
      type: DOUBLE
    - name: available_capacity_re
      type: DOUBLE
    - name: residual_demand
      type: DOUBLE
    - name: contracted_demand
      type: DOUBLE
    - name: headroom
      type: DOUBLE
    - name: source
      type: VARCHAR
@bruin */

WITH csv_seen AS (
    SELECT content_hash, MAX(seen_at) AS seen_at
    FROM (
        SELECT content_hash, first_seen_at AS seen_at FROM raw.demand_capacity_csv_content
        UNION ALL
        SELECT content_hash, scraped_at FROM raw.demand_capacity_csv_scrapes WHERE content_hash IS NOT NULL
    )
    GROUP BY ALL
),
powerbi_seen AS (
    SELECT visual_id, response_hash, MAX(seen_at) AS seen_at
    FROM (
        SELECT visual_id, response_hash, first_seen_at AS seen_at FROM raw.demand_capacity_powerbi_content
        UNION ALL
        SELECT visual_id, response_hash, scraped_at FROM raw.demand_capacity_powerbi_scrapes WHERE response_hash IS NOT NULL
    )
    GROUP BY ALL
),
unified AS (
    SELECT
        timezone('UTC', timestamp) AS ts,
        CASE
            WHEN series ILIKE 'Available Capacity Incl Non Comm Units' THEN 'available_capacity'
            WHEN series ILIKE 'Available_Capacity_Incl_Non_Comm_Units_Incl_Total_RE'
              OR series ILIKE 'Available Capacity Incl Non Comm Units Incl Total RE' THEN 'available_capacity_re'
            WHEN series ILIKE 'Residual Demand' THEN 'residual_demand'
            WHEN series ILIKE 'RSA Contracted Demand' THEN 'contracted_demand'
            ELSE NULL
        END AS metric,
        value,
        'csv' AS source,
        1 AS priority,
        s.seen_at,
        content_hash AS payload
    FROM raw.demand_capacity_csv
    LEFT JOIN csv_seen s USING (content_hash)
    UNION ALL
    SELECT
        timezone('UTC', timestamp) AS ts,
        CASE
            WHEN series = 'Available Capacity Incl Non Comm Units' THEN 'available_capacity'
            WHEN series = 'Available Capacity Incl Non Comm Units Incl Total RE' THEN 'available_capacity_re'
            WHEN series = 'Residual Demand' THEN 'residual_demand'
            WHEN series = 'RSA Contracted Demand' THEN 'contracted_demand'
            WHEN series = 'Headroom (derived)' THEN 'headroom'
            ELSE NULL
        END AS metric,
        value,
        'powerbi' AS source,
        2 AS priority,
        s.seen_at,
        response_hash
    FROM raw.demand_capacity_powerbi
    LEFT JOIN powerbi_seen s USING (visual_id, response_hash)
    UNION ALL
    SELECT
        timezone('UTC', timestamp) AS ts,
        CASE
            WHEN series = 'Available Capacity Incl Non Comm Units' THEN 'available_capacity'
            WHEN series = 'Residual Demand' THEN 'residual_demand'
            WHEN series = 'RSA Contracted Demand' THEN 'contracted_demand'
            WHEN series = 'Headroom (derived)' THEN 'headroom'
            ELSE NULL
        END AS metric,
        value,
        'eskom_sqlite' AS source,
        3 AS priority,
        NULL,
        NULL
    FROM raw.demand_capacity_eskom_sqlite_fetch
    UNION ALL
    SELECT
        timezone('UTC', timestamp) AS ts,
        CASE
            WHEN series = 'Available Capacity Incl Non Comm Units' THEN 'available_capacity'
            WHEN series = 'Available_Capacity_Incl_Non_Comm_Units_Incl_Total_RE' THEN 'available_capacity_re'
            WHEN series = 'Residual Demand' THEN 'residual_demand'
            WHEN series = 'RSA Contracted Demand' THEN 'contracted_demand'
            WHEN series = 'Headroom (derived)' THEN 'headroom'
            ELSE NULL
        END AS metric,
        value,
        'legacy' AS source,
        4 AS priority,
        NULL,
        NULL
    FROM raw.demand_capacity_legacy_fetch
),
ranked AS (
    SELECT
        ts, metric, value, source,
        ROW_NUMBER() OVER (
            PARTITION BY ts, metric
            ORDER BY priority, seen_at DESC NULLS LAST, payload DESC NULLS LAST, value DESC
        ) AS rn
    FROM unified
    WHERE metric IS NOT NULL AND value IS NOT NULL
),
picked AS (
    SELECT ts, metric, value, source FROM ranked WHERE rn = 1
)
SELECT
    ts AS timestamp,
    MAX(value) FILTER (WHERE metric = 'available_capacity')    AS available_capacity,
    MAX(value) FILTER (WHERE metric = 'available_capacity_re') AS available_capacity_re,
    MAX(value) FILTER (WHERE metric = 'residual_demand')       AS residual_demand,
    MAX(value) FILTER (WHERE metric = 'contracted_demand')     AS contracted_demand,
    -- Prefer the eskom_sqlite-derived headroom (matches the legacy
    -- formula: Installed - PCLF - UCLF - OCLF - Demand, no non-comm).
    -- Otherwise derive it from available_capacity - residual_demand;
    -- that's a few hundred MW more optimistic because PowerBI/legacy's
    -- available_capacity includes non-comm sentout, but it lets the line
    -- keep going through the PowerBI window after eskom.sqlite runs out.
    COALESCE(
        MAX(value) FILTER (WHERE metric = 'headroom'),
        MAX(value) FILTER (WHERE metric = 'available_capacity')
            - MAX(value) FILTER (WHERE metric = 'residual_demand')
    )                                                          AS headroom,
    STRING_AGG(DISTINCT source, ',' ORDER BY source)           AS source
FROM picked
GROUP BY ts
ORDER BY ts
