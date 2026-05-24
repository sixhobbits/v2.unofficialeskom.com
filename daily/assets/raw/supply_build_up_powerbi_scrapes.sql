/* @bruin
name: raw.supply_build_up_powerbi_scrapes
type: duckdb.sql

description: |
    Append-only log of every PowerBI scrape attempt. Each pipeline run
    appends this run's rows from raw.supply_build_up_powerbi_fetch.

    Holds ONLY log-relevant columns (no response_json) — that lives in
    raw.supply_build_up_powerbi_content, referenced by response_hash.

materialization:
    type: table
    strategy: append

depends:
    - raw.supply_build_up_powerbi_fetch

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: visual_id
      type: VARCHAR
    - name: visual_title
      type: VARCHAR
    - name: response_hash
      type: VARCHAR
      description: FK to raw.supply_build_up_powerbi_content
    - name: error
      type: VARCHAR
@bruin */

SELECT
    scraped_at,
    visual_id,
    visual_title,
    response_hash,
    error
FROM raw.supply_build_up_powerbi_fetch
