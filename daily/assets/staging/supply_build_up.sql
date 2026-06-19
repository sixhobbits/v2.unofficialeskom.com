/* @bruin
name: staging.supply_build_up
tags:
    - hourly
type: duckdb.sql

description: |
    Wide-form hourly supply-side build-up, dashboard-ready.
    Source priority per (timestamp, series_key): csv > powerbi > legacy > esk_bulk.
    The `source` column reports which sources contributed values for that hour.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.portal_csv
    - raw.supply_build_up_powerbi
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
@bruin */

-- Normalise series names consistently across all sources
WITH normalise AS (
    SELECT timestamp, series, value, 'csv'     AS src FROM raw.portal_csv             WHERE slug = 'supply-side/station-build-up-for-yesterday' AND timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
    UNION ALL
    SELECT timestamp, series, value, 'powerbi' AS src FROM raw.supply_build_up_powerbi WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
    UNION ALL
    SELECT timestamp, series, value, 'legacy'  AS src FROM raw.station_build_up_legacy_content WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
    UNION ALL
    SELECT timestamp, series, value, 'esk_bulk' AS src FROM raw.esk_bulk_content       WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
),
keyed AS (
    SELECT
        timestamp,
        TRIM(BOTH '_' FROM REGEXP_REPLACE(LOWER(series), '[^a-z0-9]+', '_', 'g')) AS series_key,
        value,
        src,
        -- lower priority number = preferred source
        CASE src WHEN 'csv' THEN 1 WHEN 'powerbi' THEN 2 WHEN 'legacy' THEN 3 ELSE 4 END AS priority
    FROM normalise
),
-- one value per (timestamp, series_key): pick highest-priority source
best AS (
    SELECT DISTINCT ON (timestamp, series_key)
        timestamp, series_key, value, src
    FROM keyed
    ORDER BY timestamp, series_key, priority
)
SELECT
    timestamp,
    MAX(value) FILTER (WHERE series_key IN ('thermal_gen_excl_pumping_and_sco',
                                            'thermal_generation'))             AS thermal_gen_excl_pumping_and_sco,
    MAX(value) FILTER (WHERE series_key = 'nuclear_generation')               AS nuclear_generation,
    MAX(value) FILTER (WHERE series_key = 'eskom_ocgt_generation')            AS eskom_ocgt_generation,
    MAX(value) FILTER (WHERE series_key = 'eskom_gas_generation')             AS eskom_gas_generation,
    MAX(value) FILTER (WHERE series_key = 'dispatchable_ipp_ocgt')            AS dispatchable_ipp_ocgt,
    MAX(value) FILTER (WHERE series_key = 'hydro_water_generation')           AS hydro_water_generation,
    MAX(value) FILTER (WHERE series_key = 'pumped_water_generation')          AS pumped_water_generation,
    MAX(value) FILTER (WHERE series_key = 'international_imports')            AS international_imports,
    MAX(value) FILTER (WHERE series_key = 'ils_usage')                        AS ils_usage,
    MAX(value) FILTER (WHERE series_key IN ('manual_load_reduction_mlr',
                                            'manual_load_reduction'))          AS manual_load_reduction_mlr,
    MAX(value) FILTER (WHERE series_key = 'ios_excl_ils_and_mlr')             AS ios_excl_ils_and_mlr,
    MAX(value) FILTER (WHERE series_key = 'wind')                             AS wind,
    MAX(value) FILTER (WHERE series_key = 'pv')                               AS pv,
    MAX(value) FILTER (WHERE series_key = 'csp')                              AS csp,
    MAX(value) FILTER (WHERE series_key = 'other_re')                         AS other_re,
    STRING_AGG(DISTINCT src, ',' ORDER BY src) AS source
FROM best
GROUP BY 1
ORDER BY 1
