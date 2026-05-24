/* @bruin
name: raw.integrated_results_scrapes
type: duckdb.sql

description: |
    Append-only log of every Eskom integrated-results scrape attempt.
    One row per PDF per pipeline run. pdf_path is NOT carried — it lives
    in raw.integrated_results_content keyed by content_hash.

materialization:
    type: table
    strategy: append

depends:
    - raw.integrated_results_fetch

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
FROM raw.integrated_results_fetch
