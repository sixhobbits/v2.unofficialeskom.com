/* @bruin
name: raw.weekly_system_status_pdf_content
type: duckdb.sql

description: |
    Deduplicated content store for NTCSA Weekly System Status Report PDFs.
    PK = content_hash (sha256 of pdftotext output). Merge strategy — once a
    report's text is captured, the first-seen row is preserved forever even
    if NTCSA re-uploads the same PDF.

materialization:
    type: table
    strategy: merge

depends:
    - raw.weekly_system_status_pdf_fetch

columns:
    - name: content_hash
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: report_name
      type: VARCHAR
    - name: pdf_url
      type: VARCHAR
    - name: post_date
      type: VARCHAR
    - name: text_content
      type: VARCHAR
    - name: first_seen_at
      type: TIMESTAMP
@bruin */

SELECT
    content_hash,
    report_name,
    pdf_url,
    post_date,
    text_content,
    scraped_at AS first_seen_at
FROM raw.weekly_system_status_pdf_fetch
WHERE content_hash IS NOT NULL
