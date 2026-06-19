"""Tests for the content/scrapes SQL transforms.

The /* @bruin */ header is stripped and the bare query is run against an
in-memory DuckDB seeded with a synthetic raw.portal_csv_fetch, pinning the
dedup (content) and passthrough (scrapes) semantics.
"""
from __future__ import annotations

import duckdb
import pytest

from conftest import sql_body

FETCH_COLS = [
    "scraped_at", "slug", "section", "name", "page_url", "csv_url",
    "http_status", "content_hash", "etag", "last_modified",
    "content_length", "content_text", "error",
]


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA raw")
    c.execute(f"""
        CREATE TABLE raw.portal_csv_fetch (
            scraped_at TIMESTAMP, slug VARCHAR, section VARCHAR, name VARCHAR,
            page_url VARCHAR, csv_url VARCHAR, http_status INTEGER,
            content_hash VARCHAR, etag VARCHAR, last_modified VARCHAR,
            content_length VARCHAR, content_text VARCHAR, error VARCHAR
        )
    """)
    rows = [
        # s/a seen twice with same hash -> dedup, keep earliest first_seen_at
        ("2026-06-01 04:09:00", "s/a", "sec", "A", "p/a", "u/a", 200, "hashA", "e", "lm", "10", "textA", None),
        ("2026-06-02 04:09:00", "s/a", "sec", "A", "p/a", "u/a", 200, "hashA", "e", "lm", "10", "textA", None),
        ("2026-06-02 04:09:00", "s/b", "sec", "B", "p/b", "u/b", 200, "hashB", "e", "lm", "10", "textB", None),
        # null hash -> excluded from content store, still logged in scrapes
        ("2026-06-02 04:09:00", "s/c", "sec", "C", "p/c", None, 404, None, None, None, None, None, "page fetch HTTP 404"),
    ]
    c.executemany(
        f"INSERT INTO raw.portal_csv_fetch ({', '.join(FETCH_COLS)}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return c


def test_content_dedup(con):
    res = con.execute(sql_body("portal_csv_content.sql")).fetchdf()
    # 4 raw rows -> 2 deduped (s/a, s/b); s/c dropped (null hash)
    assert len(res) == 2
    keys = set(zip(res["slug"], res["content_hash"]))
    assert keys == {("s/a", "hashA"), ("s/b", "hashB")}
    a = res[res["slug"] == "s/a"].iloc[0]
    assert str(a["first_seen_at"]) == "2026-06-01 04:09:00"  # MIN(scraped_at)


def test_scrapes_passthrough(con):
    res = con.execute(sql_body("portal_csv_scrapes.sql")).fetchdf()
    assert len(res) == 4                       # append log keeps every attempt
    assert "content_text" not in res.columns   # body excluded from the log
    assert "content_hash" in res.columns
    # the 404 attempt is logged with its error
    c = res[res["slug"] == "s/c"].iloc[0]
    assert c["http_status"] == 404
    assert c["error"] == "page fetch HTTP 404"
