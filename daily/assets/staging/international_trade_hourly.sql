/* @bruin
name: staging.international_trade_hourly
tags:
    - hourly
type: duckdb.sql

description: |
    Hourly cross-border power flows: imports from neighbouring grids,
    exports to them. Imports are pulled with the same csv > powerbi >
    legacy > esk_bulk priority as the supply build-up (so they track the
    freshest source); exports only ever come from esk_bulk because that's
    the only raw source that publishes them.

    Revisions resolve exactly as in staging.supply_build_up: within a source
    the most recently observed payload wins. timestamp is the SAST wall-clock
    hour beginning (naive TIMESTAMP).

    Imports values are duplicated with staging.supply_build_up.international_imports
    by design — supply_build_up models the supply mix, this table models the
    trade subject, and the trade chart should consume a single table.

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
best AS (
    SELECT DISTINCT ON (timestamp, series_key)
        timestamp, series_key, value, src
    FROM keyed
    WHERE series_key IN ('international_imports', 'international_exports')
    ORDER BY timestamp, series_key, priority, seen_at DESC NULLS LAST, payload DESC NULLS LAST, value DESC
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
