/* @bruin
name: raw.portal_powerbi_scrapes
type: duckdb.sql

description: |
    Append-only log of every generic portal PowerBI scrape attempt, one row per
    (graph, visual, run). No response_json — content lives in
    raw.portal_powerbi_content keyed by (slug, response_hash).

materialization:
    type: table
    strategy: append

depends:
    - raw.portal_powerbi_fetch

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: slug
      type: VARCHAR
    - name: page_url
      type: VARCHAR
    - name: visual_id
      type: VARCHAR
    - name: visual_title
      type: VARCHAR
    - name: response_hash
      type: VARCHAR
    - name: error
      type: VARCHAR
@bruin */

SELECT scraped_at, slug, page_url, visual_id, visual_title, response_hash, error
FROM raw.portal_powerbi_fetch
