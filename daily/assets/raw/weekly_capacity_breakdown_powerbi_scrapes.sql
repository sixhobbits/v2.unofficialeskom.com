/* @bruin
name: raw.weekly_capacity_breakdown_powerbi_scrapes
type: duckdb.sql

description: |
    Append-only log of every weekly-capacity-breakdown PowerBI scrape attempt.
    Each pipeline run appends this run's rows from the _fetch asset. Holds only
    log-relevant columns (no response_json) — that lives in the _content store,
    referenced by response_hash.

materialization:
    type: table
    strategy: append

depends:
    - raw.weekly_capacity_breakdown_powerbi_fetch

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: visual_id
      type: VARCHAR
    - name: visual_title
      type: VARCHAR
    - name: response_hash
      type: VARCHAR
      description: FK to raw.weekly_capacity_breakdown_powerbi_content
    - name: error
      type: VARCHAR
@bruin */

SELECT
    scraped_at,
    visual_id,
    visual_title,
    response_hash,
    error
FROM raw.weekly_capacity_breakdown_powerbi_fetch
