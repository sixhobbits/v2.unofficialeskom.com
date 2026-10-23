"""Outage charts keep advancing when Eskom's CSV stalls."""
import ast
from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from conftest import sql_body


@pytest.fixture
def conn():
    c = duckdb.connect(':memory:')
    c.execute('CREATE SCHEMA raw; CREATE SCHEMA staging')
    # Warehouse column types: data timestamps are TIMESTAMPTZ carrying SAST
    # wall-clock as UTC; payloads carry hashes and observation metadata.
    c.execute('CREATE TABLE raw.uclf_oclf_trend_csv (content_hash VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE)')
    c.execute('CREATE TABLE raw.uclf_oclf_trend_csv_content (content_hash VARCHAR, csv_url VARCHAR, content_text VARCHAR, first_seen_at TIMESTAMPTZ)')
    c.execute('CREATE TABLE raw.uclf_oclf_trend_csv_scrapes (scraped_at TIMESTAMPTZ, page_url VARCHAR, csv_url VARCHAR, http_status BIGINT, content_hash VARCHAR, error VARCHAR)')
    c.execute('CREATE TABLE raw.uclf_oclf_trend_powerbi (response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE)')
    c.execute('CREATE TABLE raw.uclf_oclf_trend_powerbi_content (response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_json VARCHAR, metadata_json VARCHAR, first_seen_at TIMESTAMPTZ)')
    c.execute('CREATE TABLE raw.uclf_oclf_trend_powerbi_scrapes (scraped_at TIMESTAMPTZ, visual_id VARCHAR, visual_title VARCHAR, response_hash VARCHAR, error VARCHAR)')
    c.execute("INSERT INTO raw.uclf_oclf_trend_csv_content VALUES ('c1', 'u', 't', TIMESTAMPTZ '2026-09-08 04:00:00+00')")
    c.execute("INSERT INTO raw.uclf_oclf_trend_csv VALUES ('c1', TIMESTAMPTZ '2026-09-06 00:00:00+00', 'Hourly UCLF+OCLF', 1000)")
    c.execute("INSERT INTO raw.uclf_oclf_trend_powerbi_content VALUES ('p1', 'v', 'T', '{}', '{}', TIMESTAMPTZ '2026-09-08 05:00:00+00')")
    c.execute("INSERT INTO raw.uclf_oclf_trend_powerbi SELECT 'p1', 'v', 'T', timezone('UTC', t), 'Hourly UCLF+OCLF', 2000 FROM generate_series(TIMESTAMP '2026-09-06', TIMESTAMP '2026-09-07 23:00:00', INTERVAL 1 HOUR) AS s(t)")
    # A second scrape of the same hours must not inflate coverage or weighting.
    c.execute('INSERT INTO raw.uclf_oclf_trend_powerbi SELECT * FROM raw.uclf_oclf_trend_powerbi')
    c.execute("INSERT INTO raw.uclf_oclf_trend_csv VALUES ('c1', TIMESTAMPTZ '2026-09-07 00:00:00+00', 'Hourly UCLF+OCLF', NULL)")
    yield c
    c.close()


def merge(c):
    c.execute('CREATE TABLE staging.uclf_oclf_trend_hourly AS ' + sql_body('../staging/uclf_oclf_trend_hourly.sql'))


def test_csv_precedence_powerbi_tail_and_dedup(conn):
    merge(conn)
    rows = conn.execute('SELECT * FROM staging.uclf_oclf_trend_hourly ORDER BY timestamp').fetchall()
    assert len(rows) == 48
    assert rows[0][1:] == (1000, 'trend_csv')
    assert rows[-1] == (datetime(2026, 9, 7, 23), 2000, 'trend_powerbi')
    assert rows[24][1:] == (2000, 'trend_powerbi')


def test_empty_csv_still_produces_powerbi_hours(conn):
    conn.execute('DELETE FROM raw.uclf_oclf_trend_csv')
    merge(conn)
    assert conn.execute('SELECT count(*), min(source) FROM staging.uclf_oclf_trend_hourly').fetchone() == (48, 'trend_powerbi')


def test_daily_and_hourly_outages_use_powerbi_tail(conn):
    merge(conn)
    conn.execute('CREATE TABLE raw.esk_bulk_content (timestamp TIMESTAMP, series VARCHAR, value DOUBLE)')
    conn.execute("CREATE TABLE staging.installed_capacity_monthly AS SELECT DATE '2026-09-01' AS month_start, 50000.0::DOUBLE AS installed_mw")
    conn.execute("CREATE TABLE staging.eaf_weekly_official AS SELECT DATE '2026-09-01' AS week_start, 89.0::DOUBLE AS eaf_pct, 10.0::DOUBLE AS pclf_pct, 0.0::DOUBLE AS uclf_pct, 1.0::DOUBLE AS oclf_pct")
    conn.execute('CREATE TABLE staging.outage_metrics_daily AS ' + sql_body('../staging/outage_metrics_daily.sql'))
    latest = conn.execute('SELECT day, eaf_pct, uclf_src FROM staging.outage_metrics_daily ORDER BY day DESC LIMIT 1').fetchone()
    assert str(latest[0]) == '2026-09-07'
    assert latest[1:] == (86.0, 'trend_powerbi')
    conn.execute("CREATE TABLE staging.outage_metrics_hourly AS SELECT TIMESTAMP '2026-09-06' AS timestamp, 85.0 AS eaf_pct, 10.0 AS pclf_pct, 4.0 AS uclf_pct, 1.0 AS oclf_pct")
    # Load the actual chart functions without running the asset's top-level main().
    path = Path(__file__).parents[1] / 'assets/dashboard/generate_beta.py'
    tree = ast.parse(path.read_text())
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == 'main')]
    ns = {'__file__': str(path)}
    exec(compile(tree, str(path), 'exec'), ns)
    data = ns['load_outage_hourly'](conn)
    assert len(data['eaf']) == 48
    assert data['eaf'][-1] == [ns['_ts_ms'](datetime(2026, 9, 7, 23)), 86.0]
