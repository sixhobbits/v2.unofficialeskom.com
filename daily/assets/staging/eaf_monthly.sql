/* @bruin
name: staging.eaf_monthly
tags:
    - hourly
type: duckdb.sql

description: |
    Eskom's OWN published monthly EAF (%) with a normalised timestamp.
    Sourced from raw.eskom_metrics_eaf_monthly (frozen snapshot). The
    snapshot's newest month only covers days up to the scrape date (embedded
    in `source`, e.g. ..._2026_05_10T...), so that partial month is dropped —
    a 9-day "monthly EAF" is not comparable and reads as a cliff on charts.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.eskom_metrics_eaf_monthly

columns:
    - name: month_start
      type: TIMESTAMP
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: eaf_pct
      type: DOUBLE
@bruin */

WITH scrape_month AS (
    -- month of the snapshot scrape, from the timestamp in the source path
    SELECT MAX(regexp_extract(source, '(\d{4})_(\d{2})_\d{2}T', 1)
               || regexp_extract(source, '(\d{4})_(\d{2})_\d{2}T', 2)) AS ym
    FROM raw.eskom_metrics_eaf_monthly
)
SELECT
    strptime(year_month::VARCHAR || '01', '%Y%m%d') AS month_start,
    eaf AS eaf_pct
FROM raw.eskom_metrics_eaf_monthly
WHERE eaf IS NOT NULL
  AND year_month::VARCHAR < (SELECT ym FROM scrape_month)
ORDER BY 1
