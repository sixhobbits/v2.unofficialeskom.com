/* @bruin
name: raw.news_content
type: duckdb.sql

description: |
    Deduplicated Eskom media statement content store. PK = canonical_url.
    Merge strategy is insert-if-not-exists; repeated weekly scrapes are
    captured in raw.news_scrapes.

materialization:
    type: table
    strategy: merge

depends:
    - raw.news_fetch

columns:
    - name: canonical_url
      type: VARCHAR
      primary_key: true
      checks:
          - name: not_null
          - name: unique
    - name: article_url
      type: VARCHAR
    - name: title
      type: VARCHAR
    - name: published_at
      type: TIMESTAMP
    - name: modified_at
      type: TIMESTAMP
    - name: category
      type: VARCHAR
    - name: og_image_url
      type: VARCHAR
    - name: text_content
      type: VARCHAR
    - name: text_length
      type: BIGINT
    - name: links_json
      type: VARCHAR
    - name: media_urls_json
      type: VARCHAR
    - name: content_hash
      type: VARCHAR
    - name: byte_size
      type: BIGINT
    - name: http_status
      type: INTEGER
    - name: first_seen_at
      type: TIMESTAMP
@bruin */

SELECT
    canonical_url,
    ANY_VALUE(article_url)      AS article_url,
    ANY_VALUE(title)            AS title,
    ANY_VALUE(published_at)     AS published_at,
    ANY_VALUE(modified_at)      AS modified_at,
    ANY_VALUE(category)         AS category,
    ANY_VALUE(og_image_url)     AS og_image_url,
    ANY_VALUE(text_content)     AS text_content,
    ANY_VALUE(text_length)      AS text_length,
    ANY_VALUE(links_json)       AS links_json,
    ANY_VALUE(media_urls_json)  AS media_urls_json,
    ANY_VALUE(content_hash)     AS content_hash,
    ANY_VALUE(byte_size)        AS byte_size,
    ANY_VALUE(http_status)      AS http_status,
    MIN(scraped_at)             AS first_seen_at
FROM raw.news_fetch
WHERE canonical_url IS NOT NULL
GROUP BY canonical_url
