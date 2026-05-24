/* @bruin
name: raw.news_scrapes
type: duckdb.sql

description: |
    Append-only log of every Eskom media statement scrape attempt.
    One row per article per pipeline run.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.news_fetch

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: article_url
      type: VARCHAR
    - name: canonical_url
      type: VARCHAR
    - name: title
      type: VARCHAR
    - name: published_at
      type: TIMESTAMP
    - name: modified_at
      type: TIMESTAMP
    - name: content_hash
      type: VARCHAR
    - name: byte_size
      type: BIGINT
    - name: http_status
      type: INTEGER
    - name: error
      type: VARCHAR
@bruin */

SELECT
    scraped_at,
    article_url,
    canonical_url,
    title,
    published_at,
    modified_at,
    content_hash,
    byte_size,
    http_status,
    error
FROM raw.news_fetch
