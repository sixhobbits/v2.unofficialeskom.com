/* @bruin
name: staging.supply_build_up
tags:
    - hourly
type: duckdb.sql

description: |
    Wide-form hourly supply-side build-up, dashboard-ready.
    Source priority per (timestamp, series_key): csv > powerbi > legacy > esk_bulk.
    Within a source, the most recently observed payload wins: Eskom revises
    recent hours, and every stored CSV/PowerBI revision stays in raw. Payload
    observation time is the later of its first ingest (*_content) and its last
    logged scrape (*_scrapes); ties break on payload hash, so row order and
    repeated collection cannot change the result.
    The `source` column reports which sources contributed values for that hour.

    timestamp is the SAST (UTC+2, no DST) wall-clock hour beginning, as a
    naive TIMESTAMP. Every Eskom source publishes SAST wall-clock times; the
    raw TIMESTAMPTZ columns carry them as UTC wall-clock, so they convert with
    timezone('UTC', …) — never a bare cast, which applies the session zone.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.portal_csv
    - raw.portal_csv_content
    - raw.portal_csv_scrapes
    - raw.supply_build_up_powerbi
    - raw.supply_build_up_powerbi_content
    - raw.supply_build_up_powerbi_scrapes
    - raw.station_build_up_legacy_content
    - raw.esk_bulk_content

columns:
    - name: timestamp
      type: TIMESTAMP
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: thermal_gen_excl_pumping_and_sco
      type: DOUBLE
    - name: nuclear_generation
      type: DOUBLE
    - name: eskom_ocgt_generation
      type: DOUBLE
    - name: eskom_gas_generation
      type: DOUBLE
    - name: dispatchable_ipp_ocgt
      type: DOUBLE
    - name: hydro_water_generation
      type: DOUBLE
    - name: pumped_water_generation
      type: DOUBLE
    - name: international_imports
      type: DOUBLE
    - name: ils_usage
      type: DOUBLE
    - name: manual_load_reduction_mlr
      type: DOUBLE
    - name: ios_excl_ils_and_mlr
      type: DOUBLE
    - name: wind
      type: DOUBLE
    - name: pv
      type: DOUBLE
    - name: csp
      type: DOUBLE
    - name: other_re
      type: DOUBLE
    - name: source
      type: VARCHAR
      description: "which sources supplied values this hour (csv/powerbi/legacy/esk_bulk)"

custom_checks:
    - name: at_least_24_rows
      query: SELECT CASE WHEN COUNT(*) >= 24 THEN 1 ELSE 0 END FROM staging.supply_build_up
      value: 1
    - name: freshness_72h
      description: latest hour must be within 72h of pipeline run
      blocking: false
      query: |
          SELECT CASE
              WHEN (EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 3600) < 72
              THEN 1 ELSE 0
          END
          FROM staging.supply_build_up
      value: 1
    # BLOCKING tripwire: actuals can never be in the future. Exists because
    # bruin v0.11.663's DataFrame→DuckDB load scrambled row/column alignment
    # (rows got other rows' timestamps, some years away — 2026-07-03 incident,
    # charts plotted "generation" into 2027). A scrambled load must fail here,
    # before dashboard.generate_beta can deploy it. Pin bruin v0.11.574.
    - name: no_future_rows
      description: no rows stamped more than 2 days in the future
      query: |
          SELECT COUNT(*) FROM staging.supply_build_up
          WHERE timestamp > NOW() + INTERVAL 2 DAY
      value: 0
@bruin */

WITH csv_seen AS (
    SELECT slug, content_hash, MAX(seen_at) AS seen_at
    FROM (
        SELECT slug, content_hash, first_seen_at AS seen_at FROM raw.portal_csv_content
        UNION ALL
        SELECT slug, content_hash, scraped_at FROM raw.portal_csv_scrapes WHERE content_hash IS NOT NULL
    )
    GROUP BY ALL
),
powerbi_seen AS (
    SELECT visual_id, response_hash, MAX(seen_at) AS seen_at
    FROM (
        SELECT visual_id, response_hash, first_seen_at AS seen_at FROM raw.supply_build_up_powerbi_content
        UNION ALL
        SELECT visual_id, response_hash, scraped_at FROM raw.supply_build_up_powerbi_scrapes WHERE response_hash IS NOT NULL
    )
    GROUP BY ALL
),
-- Normalise series names consistently across all sources
normalise AS (
    SELECT timezone('UTC', p.timestamp) AS timestamp, p.series, p.value, 'csv' AS src,
           s.seen_at, p.content_hash AS payload
    FROM raw.portal_csv p
    LEFT JOIN csv_seen s USING (slug, content_hash)
    WHERE p.slug = 'supply-side/station-build-up-for-yesterday' AND p.timestamp IS NOT NULL AND p.series IS NOT NULL AND p.value IS NOT NULL
    UNION ALL
    SELECT timezone('UTC', p.timestamp), p.series, p.value, 'powerbi',
           s.seen_at, p.response_hash
    FROM raw.supply_build_up_powerbi p
    LEFT JOIN powerbi_seen s USING (visual_id, response_hash)
    WHERE p.timestamp IS NOT NULL AND p.series IS NOT NULL AND p.value IS NOT NULL
    UNION ALL
    SELECT timezone('UTC', timestamp), series, value, 'legacy', NULL, row_hash
    FROM raw.station_build_up_legacy_content WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
    UNION ALL
    -- esk_bulk_content already holds naive SAST wall-clock, one value per key
    SELECT timestamp, series, value, 'esk_bulk', NULL, NULL
    FROM raw.esk_bulk_content WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
),
keyed AS (
    SELECT
        timestamp,
        TRIM(BOTH '_' FROM REGEXP_REPLACE(LOWER(series), '[^a-z0-9]+', '_', 'g')) AS series_key,
        value,
        src,
        seen_at,
        payload,
        -- lower priority number = preferred source
        CASE src WHEN 'csv' THEN 1 WHEN 'powerbi' THEN 2 WHEN 'legacy' THEN 3 ELSE 4 END AS priority
    FROM normalise
),
-- one value per (timestamp, series_key): highest-priority source, then that
-- source's most recently observed payload
best AS (
    SELECT DISTINCT ON (timestamp, series_key)
        timestamp, series_key, value, src
    FROM keyed
    ORDER BY timestamp, series_key, priority, seen_at DESC NULLS LAST, payload DESC NULLS LAST, value DESC
)
SELECT
    timestamp,
    COALESCE(
        MAX(value) FILTER (WHERE series_key = 'thermal_gen_excl_pumping_and_sco'),
        MAX(value) FILTER (WHERE series_key = 'thermal_generation')
    )                                                                           AS thermal_gen_excl_pumping_and_sco,
    MAX(value) FILTER (WHERE series_key = 'nuclear_generation')               AS nuclear_generation,
    MAX(value) FILTER (WHERE series_key = 'eskom_ocgt_generation')            AS eskom_ocgt_generation,
    MAX(value) FILTER (WHERE series_key = 'eskom_gas_generation')             AS eskom_gas_generation,
    MAX(value) FILTER (WHERE series_key = 'dispatchable_ipp_ocgt')            AS dispatchable_ipp_ocgt,
    MAX(value) FILTER (WHERE series_key = 'hydro_water_generation')           AS hydro_water_generation,
    MAX(value) FILTER (WHERE series_key = 'pumped_water_generation')          AS pumped_water_generation,
    MAX(value) FILTER (WHERE series_key = 'international_imports')            AS international_imports,
    MAX(value) FILTER (WHERE series_key = 'ils_usage')                        AS ils_usage,
    COALESCE(
        MAX(value) FILTER (WHERE series_key = 'manual_load_reduction_mlr'),
        MAX(value) FILTER (WHERE series_key = 'manual_load_reduction')
    )                                                                           AS manual_load_reduction_mlr,
    MAX(value) FILTER (WHERE series_key = 'ios_excl_ils_and_mlr')             AS ios_excl_ils_and_mlr,
    MAX(value) FILTER (WHERE series_key = 'wind')                             AS wind,
    MAX(value) FILTER (WHERE series_key = 'pv')                               AS pv,
    MAX(value) FILTER (WHERE series_key = 'csp')                              AS csp,
    MAX(value) FILTER (WHERE series_key = 'other_re')                         AS other_re,
    STRING_AGG(DISTINCT src, ',' ORDER BY src) AS source
FROM best
GROUP BY 1
ORDER BY 1
