/* @bruin
name: raw.media_presentations_scrapes
type: duckdb.sql

description: |
    Append-only log of every media-room presentation scrape attempt.
    One row per PDF per pipeline run. pdf_path is NOT carried — it lives
    in raw.media_presentations_content keyed by content_hash.

materialization:
    type: table
    strategy: append

depends:
    - raw.media_presentations_fetch

columns:
    - name: scraped_at
      type: TIMESTAMP
    - name: pdf_url
      type: VARCHAR
    - name: filename
      type: VARCHAR
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
    pdf_url,
    filename,
    content_hash,
    byte_size,
    http_status,
    error
FROM raw.media_presentations_fetch
