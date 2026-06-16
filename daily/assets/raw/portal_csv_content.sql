/* @bruin
name: raw.portal_csv_content
tags:
    - hourly
type: duckdb.sql

description: |
    Deduplicated content store for generic portal CSV bodies. PK =
    (slug, content_hash) — keyed by slug as well as hash because distinct
    graphs can return byte-identical error pages. Insert-only merge.

materialization:
    type: table
    strategy: merge

depends:
    - raw.portal_csv_fetch

columns:
    - name: slug
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: content_hash
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
    - name: csv_url
      type: VARCHAR
    - name: content_text
      type: VARCHAR
    - name: first_seen_at
      type: TIMESTAMP
@bruin */

SELECT
    slug,
    content_hash,
    ANY_VALUE(csv_url)      AS csv_url,
    ANY_VALUE(content_text) AS content_text,
    MIN(scraped_at)         AS first_seen_at
FROM raw.portal_csv_fetch
WHERE content_hash IS NOT NULL
GROUP BY slug, content_hash
