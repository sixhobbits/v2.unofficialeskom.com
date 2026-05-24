/* @bruin
name: raw.weekly_capacity_breakdown_powerbi_content
type: duckdb.sql

description: |
    Deduplicated content store for weekly-capacity-breakdown PowerBI responses.
    PK = response_hash. Bruin's merge strategy is insert-if-not-exists — matching
    hashes are skipped, so the row captured on first sighting is preserved.

materialization:
    type: table
    strategy: merge

depends:
    - raw.weekly_capacity_breakdown_powerbi_fetch

columns:
    - name: response_hash
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: visual_id
      type: VARCHAR
    - name: visual_title
      type: VARCHAR
    - name: response_json
      type: VARCHAR
    - name: metadata_json
      type: VARCHAR
    - name: first_seen_at
      type: TIMESTAMP
@bruin */

SELECT
    response_hash,
    visual_id,
    visual_title,
    response_json,
    metadata_json,
    scraped_at AS first_seen_at
FROM raw.weekly_capacity_breakdown_powerbi_fetch
WHERE response_hash IS NOT NULL
