/* @bruin
name: staging.international_trade_hourly
type: duckdb.sql

description: |
    Hourly cross-border power flows: imports from neighbouring grids,
    exports to them. Imports are pulled with the same csv > powerbi >
    legacy > esk_bulk priority as the supply build-up (so they track the
    freshest source); exports only ever come from esk_bulk because that's
    the only raw source that publishes them.

    Imports values are duplicated with staging.supply_build_up.international_imports
    by design — supply_build_up models the supply mix, this table models the
    trade subject, and the trade chart should consume a single table.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.supply_build_up_csv
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
    - name: imports_mw
      type: DOUBLE
    - name: exports_mw
      type: DOUBLE
    - name: imports_source
      type: VARCHAR
      description: "winning raw source for imports this hour (csv/powerbi/legacy/esk_bulk)"
    - name: exports_source
      type: VARCHAR
      description: "winning raw source for exports this hour (only esk_bulk publishes it today)"

custom_checks:
    - name: imports_freshness_72h
      description: latest imports hour within 72h of pipeline run
      blocking: false
      query: |
          SELECT CASE
              WHEN (EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 3600) < 72
              THEN 1 ELSE 0
          END
          FROM staging.international_trade_hourly
          WHERE imports_mw IS NOT NULL
      value: 1
@bruin */

WITH normalise AS (
    SELECT timestamp, series, TRY_CAST(value AS DOUBLE) AS value, 'csv'     AS src FROM raw.supply_build_up_csv     WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
    UNION ALL
    SELECT timestamp, series, TRY_CAST(value AS DOUBLE) AS value, 'powerbi' AS src FROM raw.supply_build_up_powerbi WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
    UNION ALL
    SELECT timestamp, series, TRY_CAST(value AS DOUBLE) AS value, 'legacy'  AS src FROM raw.station_build_up_legacy_content WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
    UNION ALL
    SELECT timestamp, series, TRY_CAST(value AS DOUBLE) AS value, 'esk_bulk' AS src FROM raw.esk_bulk_content       WHERE timestamp IS NOT NULL AND series IS NOT NULL AND value IS NOT NULL
),
keyed AS (
    SELECT
        timestamp,
        TRIM(BOTH '_' FROM REGEXP_REPLACE(LOWER(series), '[^a-z0-9]+', '_', 'g')) AS series_key,
        value,
        src,
        CASE src WHEN 'csv' THEN 1 WHEN 'powerbi' THEN 2 WHEN 'legacy' THEN 3 ELSE 4 END AS priority
    FROM normalise
    WHERE value IS NOT NULL
),
best AS (
    SELECT DISTINCT ON (timestamp, series_key)
        timestamp, series_key, value, src
    FROM keyed
    WHERE series_key IN ('international_imports', 'international_exports')
    ORDER BY timestamp, series_key, priority
)
SELECT
    timestamp,
    MAX(value) FILTER (WHERE series_key = 'international_imports') AS imports_mw,
    MAX(value) FILTER (WHERE series_key = 'international_exports') AS exports_mw,
    MAX(src)   FILTER (WHERE series_key = 'international_imports') AS imports_source,
    MAX(src)   FILTER (WHERE series_key = 'international_exports') AS exports_source
FROM best
GROUP BY 1
ORDER BY 1
