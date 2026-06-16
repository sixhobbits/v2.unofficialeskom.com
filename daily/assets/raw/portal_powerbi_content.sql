/* @bruin
name: raw.portal_powerbi_content
type: duckdb.sql

description: |
    Deduplicated content store for generic portal PowerBI responses. PK =
    (slug, response_hash). Insert-only merge.

materialization:
    type: table
    strategy: merge

depends:
    - raw.portal_powerbi_fetch

columns:
    - name: slug
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: response_hash
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
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
    slug,
    response_hash,
    ANY_VALUE(visual_id)     AS visual_id,
    ANY_VALUE(visual_title)  AS visual_title,
    ANY_VALUE(response_json) AS response_json,
    ANY_VALUE(metadata_json) AS metadata_json,
    MIN(scraped_at)          AS first_seen_at
FROM raw.portal_powerbi_fetch
WHERE response_hash IS NOT NULL
GROUP BY slug, response_hash
