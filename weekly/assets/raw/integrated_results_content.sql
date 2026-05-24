/* @bruin
name: raw.integrated_results_content
type: duckdb.sql

description: |
    Deduplicated Eskom integrated-results PDF content store. PK =
    content_hash. Merge strategy is insert-if-not-exists — matching hashes
    are skipped, so identical re-uploads of the same PDF are recorded once
    with their first_seen_at preserved. pdf_path points at the on-disk cache;
    the actual bytes live there (not in the warehouse).

    last_seen_at / times_seen are derivable from the scrapes log:
        SELECT content_hash, MAX(scraped_at), COUNT(*)
        FROM raw.integrated_results_scrapes GROUP BY content_hash

materialization:
    type: table
    strategy: merge

depends:
    - raw.integrated_results_fetch

columns:
    - name: content_hash
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: pdf_url
      type: VARCHAR
    - name: filename
      type: VARCHAR
    - name: pdf_path
      type: VARCHAR
    - name: byte_size
      type: BIGINT
    - name: http_status
      type: INTEGER
    - name: first_seen_at
      type: TIMESTAMP
@bruin */

SELECT
    content_hash,
    ANY_VALUE(pdf_url)     AS pdf_url,
    ANY_VALUE(filename)    AS filename,
    ANY_VALUE(pdf_path)    AS pdf_path,
    ANY_VALUE(byte_size)   AS byte_size,
    ANY_VALUE(http_status) AS http_status,
    MIN(scraped_at)        AS first_seen_at
FROM raw.integrated_results_fetch
WHERE content_hash IS NOT NULL
GROUP BY content_hash
