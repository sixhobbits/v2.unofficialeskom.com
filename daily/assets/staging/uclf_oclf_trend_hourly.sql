/* @bruin
name: staging.uclf_oclf_trend_hourly
tags:
    - hourly
type: duckdb.sql

description: |
    Combined hourly UCLF+OCLF (MW), preferring CSV for overlapping hours and
    using PowerBI for missing hours. Eskom can stop updating its CSV while
    the embedded report keeps advancing, so both sources are required.
    Shared by daily outages, the hourly chart tail and year-on-year outages.
    Within a source the most recently observed payload wins (later of its
    first ingest and last logged scrape; ties on payload hash) — Eskom revises
    recent hours, so averaging stored revisions would blend stale values in.
    Remove the backup only if Eskom retires the PowerBI report or guarantees
    the CSV has identical coverage.

    timestamp is the SAST wall-clock hour beginning (naive TIMESTAMP).

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.uclf_oclf_trend_csv
    - raw.uclf_oclf_trend_csv_content
    - raw.uclf_oclf_trend_csv_scrapes
    - raw.uclf_oclf_trend_powerbi
    - raw.uclf_oclf_trend_powerbi_content
    - raw.uclf_oclf_trend_powerbi_scrapes

columns:
    - name: timestamp
      type: TIMESTAMP
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: uclf_oclf_mw
      type: DOUBLE
    - name: source
      type: VARCHAR
@bruin */

WITH csv_seen AS (
    SELECT content_hash, MAX(seen_at) AS seen_at
    FROM (
        SELECT content_hash, first_seen_at AS seen_at FROM raw.uclf_oclf_trend_csv_content
        UNION ALL
        SELECT content_hash, scraped_at FROM raw.uclf_oclf_trend_csv_scrapes WHERE content_hash IS NOT NULL
    )
    GROUP BY ALL
),
powerbi_seen AS (
    SELECT visual_id, response_hash, MAX(seen_at) AS seen_at
    FROM (
        SELECT visual_id, response_hash, first_seen_at AS seen_at FROM raw.uclf_oclf_trend_powerbi_content
        UNION ALL
        SELECT visual_id, response_hash, scraped_at FROM raw.uclf_oclf_trend_powerbi_scrapes WHERE response_hash IS NOT NULL
    )
    GROUP BY ALL
),
unified AS (
    SELECT timezone('UTC', c.timestamp) AS timestamp, c.value, 'trend_csv' AS source, 1 AS priority,
           s.seen_at, c.content_hash AS payload
    FROM raw.uclf_oclf_trend_csv c
    LEFT JOIN csv_seen s USING (content_hash)
    WHERE c.series = 'Hourly UCLF+OCLF' AND c.timestamp IS NOT NULL AND c.value IS NOT NULL
    UNION ALL
    SELECT timezone('UTC', p.timestamp), p.value, 'trend_powerbi', 2,
           s.seen_at, p.response_hash
    FROM raw.uclf_oclf_trend_powerbi p
    LEFT JOIN powerbi_seen s USING (visual_id, response_hash)
    WHERE p.series = 'Hourly UCLF+OCLF' AND p.timestamp IS NOT NULL AND p.value IS NOT NULL
)
SELECT timestamp, value AS uclf_oclf_mw, source
FROM unified
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY timestamp
    ORDER BY priority, seen_at DESC NULLS LAST, payload DESC, value DESC
) = 1
ORDER BY timestamp
