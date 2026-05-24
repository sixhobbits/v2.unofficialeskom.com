/* @bruin
name: raw.demand_capacity_powerbi_scrapes
type: duckdb.sql

description: |
    Append-only log of every PowerBI scrape attempt for the demand+capacity
    feed. Holds only log-relevant columns (no response_json) — content lives
    in raw.demand_capacity_powerbi_content keyed by response_hash.

materialization:
    type: table
    strategy: append

depends:
    - raw.demand_capacity_powerbi_fetch

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: visual_id
      type: VARCHAR
    - name: visual_title
      type: VARCHAR
    - name: response_hash
      type: VARCHAR
    - name: error
      type: VARCHAR
@bruin */

SELECT scraped_at, visual_id, visual_title, response_hash, error
FROM raw.demand_capacity_powerbi_fetch
