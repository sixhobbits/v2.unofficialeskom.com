"""One-off warehouse repair for the session-time-zone bug (2026-10-23).

Two raw tables were written through a bare TIMESTAMPTZ -> TIMESTAMP cast,
which DuckDB evaluates in the session zone (Europe/Berlin on thet and the
laptop):

- raw.esk_bulk_content.timestamp: SAST wall-clock shifted +1 h (winter) /
  +2 h (summer). The two hours either side of each October clock change
  collapsed onto one key; the merge then inserted duplicate keys run after
  run. raw.esk_bulk_fetch holds the full bulk history (the ESK sqlite), so
  the table is rebuilt from it with the fixed conversion.
- raw.portal_csv_scrapes.scraped_at: real scrape instants stored as naive
  Berlin wall-clock. Converted to TIMESTAMPTZ (the type every other *_scrapes
  log has), so the append keeps instants exact.

Run once, with no bruin run active (DuckDB single-writer), BEFORE the first
pipeline run on the fixed code:

    .venv/bin/python migrations/2026_10_23_timestamp_repair.py ../warehouse/eskom.duckdb

Safe to re-run: the bulk rebuild is deterministic and the scrapes conversion
only runs while the column is still a naive TIMESTAMP. Delete this file once
it has run on every warehouse copy that matters.
"""
from __future__ import annotations

import sys

import duckdb


def repair(conn: duckdb.DuckDBPyConnection) -> None:
    def one(sql: str):
        return conn.execute(sql).fetchone()

    print("before:")
    print("  esk_bulk_content rows/distinct keys:",
          one("SELECT COUNT(*), COUNT(DISTINCT (timestamp, series)) FROM raw.esk_bulk_content"))
    conn.execute("BEGIN")
    conn.execute("DELETE FROM raw.esk_bulk_content")
    conn.execute("""
        INSERT INTO raw.esk_bulk_content (timestamp, series, value)
        SELECT timezone('UTC', timestamp), series, TRY_CAST(value AS DOUBLE)
        FROM raw.esk_bulk_fetch
        WHERE timestamp IS NOT NULL AND series IS NOT NULL
          AND TRY_CAST(value AS DOUBLE) IS NOT NULL
    """)
    scrapes_type = one("""
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'portal_csv_scrapes'
          AND column_name = 'scraped_at'
    """)[0]
    if scrapes_type == "TIMESTAMP":
        conn.execute("""
            ALTER TABLE raw.portal_csv_scrapes ALTER scraped_at
            SET DATA TYPE TIMESTAMPTZ USING timezone('Europe/Berlin', scraped_at)
        """)
    conn.execute("COMMIT")
    print("after:")
    print("  esk_bulk_content rows/distinct keys:",
          one("SELECT COUNT(*), COUNT(DISTINCT (timestamp, series)) FROM raw.esk_bulk_content"))
    print("  esk_bulk_fetch rows:", one("SELECT COUNT(*) FROM raw.esk_bulk_fetch WHERE TRY_CAST(value AS DOUBLE) IS NOT NULL"))
    print("  portal_csv_scrapes.scraped_at:", one("""
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'portal_csv_scrapes'
          AND column_name = 'scraped_at'
    """)[0], one("SELECT MAX(scraped_at)::VARCHAR FROM raw.portal_csv_scrapes")[0])


if __name__ == "__main__":
    with duckdb.connect(sys.argv[1]) as conn:
        conn.execute("SET TimeZone = 'UTC'")
        repair(conn)
