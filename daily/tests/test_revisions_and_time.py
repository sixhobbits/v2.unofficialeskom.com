"""Regression tests for revision selection and the SAST time convention.

Each staging query runs against an in-memory DuckDB whose raw tables use the
live warehouse's column types: ingested data timestamps are TIMESTAMPTZ
carrying the SAST wall-clock as UTC, esk_bulk_content is a naive TIMESTAMP.
Every test runs under both a UTC and a Europe/Berlin session (thet runs
Europe/Berlin), because a bare TIMESTAMPTZ<->TIMESTAMP cast applies the
session zone and shifted hours by 1-2 h before the fix.
"""
from __future__ import annotations

import datetime as dt

import duckdb
import pytest

from conftest import sql_body

RAW_TABLES = {
    "raw.portal_csv": "slug VARCHAR, content_hash VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.portal_csv_content": "slug VARCHAR, content_hash VARCHAR, csv_url VARCHAR, content_text VARCHAR, first_seen_at TIMESTAMPTZ",
    "raw.portal_csv_scrapes": "scraped_at TIMESTAMPTZ, slug VARCHAR, page_url VARCHAR, csv_url VARCHAR, http_status INTEGER, content_hash VARCHAR, etag VARCHAR, last_modified VARCHAR, content_length VARCHAR, error VARCHAR",
    "raw.supply_build_up_powerbi": "response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.supply_build_up_powerbi_content": "response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_json VARCHAR, metadata_json VARCHAR, first_seen_at TIMESTAMPTZ",
    "raw.supply_build_up_powerbi_scrapes": "scraped_at TIMESTAMPTZ, visual_id VARCHAR, visual_title VARCHAR, response_hash VARCHAR, error VARCHAR",
    "raw.station_build_up_legacy_content": "row_hash VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.esk_bulk_fetch": "timestamp TIMESTAMPTZ, series VARCHAR, value VARCHAR",
    "raw.esk_bulk_content": "timestamp TIMESTAMP, series VARCHAR, value DOUBLE",
    "raw.uclf_oclf_trend_csv": "content_hash VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.uclf_oclf_trend_csv_content": "content_hash VARCHAR, csv_url VARCHAR, content_text VARCHAR, first_seen_at TIMESTAMPTZ",
    "raw.uclf_oclf_trend_csv_scrapes": "scraped_at TIMESTAMPTZ, page_url VARCHAR, csv_url VARCHAR, http_status BIGINT, content_hash VARCHAR, error VARCHAR",
    "raw.uclf_oclf_trend_powerbi": "response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.uclf_oclf_trend_powerbi_content": "response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_json VARCHAR, metadata_json VARCHAR, first_seen_at TIMESTAMPTZ",
    "raw.uclf_oclf_trend_powerbi_scrapes": "scraped_at TIMESTAMPTZ, visual_id VARCHAR, visual_title VARCHAR, response_hash VARCHAR, error VARCHAR",
    "raw.weekly_capacity_breakdown_powerbi": "response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, week_start TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.weekly_capacity_breakdown_powerbi_content": "response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_json VARCHAR, metadata_json VARCHAR, first_seen_at TIMESTAMPTZ",
    "raw.weekly_capacity_breakdown_powerbi_scrapes": "scraped_at TIMESTAMPTZ, visual_id VARCHAR, visual_title VARCHAR, response_hash VARCHAR, error VARCHAR",
    "raw.eskom_metrics_weekly_breakdown": "week_start DATE, eaf DOUBLE, pclf DOUBLE, uclf DOUBLE, oclf DOUBLE, source VARCHAR",
    "raw.demand_capacity_csv": "content_hash VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.demand_capacity_csv_content": "content_hash VARCHAR, csv_url VARCHAR, http_status BIGINT, content_text VARCHAR, first_seen_at TIMESTAMPTZ",
    "raw.demand_capacity_csv_scrapes": "scraped_at TIMESTAMPTZ, page_url VARCHAR, csv_url VARCHAR, http_status BIGINT, content_hash VARCHAR, error VARCHAR",
    "raw.demand_capacity_powerbi": "response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.demand_capacity_powerbi_content": "response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_json VARCHAR, metadata_json VARCHAR, first_seen_at TIMESTAMPTZ",
    "raw.demand_capacity_powerbi_scrapes": "scraped_at TIMESTAMPTZ, visual_id VARCHAR, visual_title VARCHAR, response_hash VARCHAR, error VARCHAR",
    "raw.demand_capacity_eskom_sqlite_fetch": "timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
    "raw.demand_capacity_legacy_fetch": "timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE",
}

SBU_SLUG = "supply-side/station-build-up-for-yesterday"
SAST = dt.timezone(dt.timedelta(hours=2))


def utc_wall(s: str) -> str:
    """A SAST wall-clock reading as raw TIMESTAMPTZ columns store it."""
    return s + "+00"


def seen(s: str) -> str:
    """A real observation instant (scrape time), given in UTC."""
    return s + "+00"


@pytest.fixture(params=["UTC", "Europe/Berlin"])
def con(request):
    c = duckdb.connect(":memory:")
    c.execute(f"SET TimeZone = '{request.param}'")
    c.execute("CREATE SCHEMA raw")
    c.execute("CREATE SCHEMA staging")
    for name, cols in RAW_TABLES.items():
        c.execute(f"CREATE TABLE {name} ({cols})")
    return c


def insert(c, table, rows):
    if rows:
        marks = ", ".join("?" * len(rows[0]))
        c.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)


def materialize(c, name):
    """Run a staging/raw SQL asset and store it under its name."""
    schema, table = name.split(".")
    path = f"../{schema}/{table}.sql"
    c.execute(f"CREATE OR REPLACE TABLE {name} AS {sql_body(path)}")
    return c.execute(f"SELECT * FROM {name} ORDER BY 1").fetchdf()


def csv_payload(c, slug, content_hash, first_seen, scrapes, points):
    insert(c, "raw.portal_csv_content", [(slug, content_hash, "u", "t", seen(first_seen))])
    insert(c, "raw.portal_csv_scrapes",
           [(seen(s), slug, "p", "u", 200, content_hash, None, None, None, None) for s in scrapes])
    insert(c, "raw.portal_csv", [(slug, content_hash, utc_wall(ts), series, v) for ts, series, v in points])


def pbi_payload(c, prefix, response_hash, first_seen, scrapes, points, visual="v1"):
    insert(c, f"raw.{prefix}_content", [(response_hash, visual, "T", "{}", "{}", seen(first_seen))])
    insert(c, f"raw.{prefix}_scrapes",
           [(seen(s), visual, "T", response_hash, None) for s in scrapes])
    insert(c, f"raw.{prefix}", [(response_hash, visual, "T", utc_wall(ts), series, v)
                                for ts, series, v in points])


# ---------- Fix 2: latest revision wins within a source ----------

@pytest.mark.parametrize("newest_first", [False, True])
def test_supply_build_up_latest_csv_revision_wins(con, newest_first):
    # 12 Sep 02:00 thermal: first published 16,334.6, revised to 17,728.6.
    hour = "2026-09-12 02:00:00"
    old = lambda: csv_payload(con, SBU_SLUG, "h-old", "2026-09-13 04:10:00", ["2026-09-13 04:40:00"],
                              [(hour, "Thermal_Gen_Excl_Pumping_and_SCO", 16334.6)])
    new = lambda: csv_payload(con, SBU_SLUG, "h-new", "2026-09-14 04:10:00",
                              ["2026-09-14 04:40:00", "2026-09-15 04:40:00"],
                              [(hour, "Thermal_Gen_Excl_Pumping_and_SCO", 17728.6)])
    for load in ((new, old) if newest_first else (old, new)):
        load()
    # an older revision collected again (its old hash) must not win either
    insert(con, "raw.portal_csv",
           [(SBU_SLUG, "h-old", utc_wall(hour), "Thermal_Gen_Excl_Pumping_and_SCO", 16334.6)])
    df = materialize(con, "staging.supply_build_up")
    assert len(df) == 1
    assert df.iloc[0]["thermal_gen_excl_pumping_and_sco"] == 17728.6
    assert df.iloc[0]["timestamp"] == dt.datetime(2026, 9, 12, 2)  # naive SAST wall-clock


def test_supply_build_up_last_observation_beats_first_ingest(con):
    hour = "2026-09-12 02:00:00"
    # A first seen earlier but logged again after B: A is the latest observation.
    csv_payload(con, SBU_SLUG, "A", "2026-09-13 04:10:00", ["2026-09-16 04:40:00"],
                [(hour, "Nuclear Generation", 1800.0)])
    csv_payload(con, SBU_SLUG, "B", "2026-09-14 04:10:00", ["2026-09-14 04:40:00"],
                [(hour, "Nuclear Generation", 900.0)])
    df = materialize(con, "staging.supply_build_up")
    assert df.iloc[0]["nuclear_generation"] == 1800.0


def test_supply_build_up_tie_breaks_on_payload_hash(con):
    hour = "2026-09-12 02:00:00"
    for h, v in (("aaa", 1.0), ("bbb", 2.0)):
        csv_payload(con, SBU_SLUG, h, "2026-09-13 04:10:00", [], [(hour, "Wind", v)])
    df = materialize(con, "staging.supply_build_up")
    assert df.iloc[0]["wind"] == 2.0


def test_supply_build_up_priority_and_backup_coverage(con):
    both, pbi_only, bulk_only = "2026-09-12 02:00:00", "2026-09-12 03:00:00", "2026-08-01 05:00:00"
    csv_payload(con, SBU_SLUG, "c1", "2026-09-13 04:10:00", [], [(both, "Wind", 100.0)])
    # PowerBI: two revisions; csv still beats both where it has the hour
    pbi_payload(con, "supply_build_up_powerbi", "p-old", "2026-09-13 05:00:00", [],
                [(both, "Wind", 50.0), (pbi_only, "Wind", 60.0)])
    pbi_payload(con, "supply_build_up_powerbi", "p-new", "2026-09-14 05:00:00", [],
                [(both, "Wind", 55.0), (pbi_only, "Wind", 66.0)])
    insert(con, "raw.esk_bulk_content", [(dt.datetime(2026, 8, 1, 5), "Wind", 70.0)])
    df = materialize(con, "staging.supply_build_up").set_index("timestamp")
    assert df.loc[dt.datetime(2026, 9, 12, 2), "wind"] == 100.0
    assert df.loc[dt.datetime(2026, 9, 12, 3), "wind"] == 66.0
    assert df.loc[dt.datetime(2026, 9, 12, 3), "source"] == "powerbi"
    assert df.loc[dt.datetime(2026, 8, 1, 5), "wind"] == 70.0
    assert df.loc[dt.datetime(2026, 8, 1, 5), "source"] == "esk_bulk"


def test_trade_uses_latest_revision(con):
    hour = "2026-09-12 02:00:00"
    csv_payload(con, SBU_SLUG, "old", "2026-09-13 04:10:00", [], [(hour, "International Imports", 900.0)])
    csv_payload(con, SBU_SLUG, "new", "2026-09-14 04:10:00", [], [(hour, "International Imports", 950.0)])
    insert(con, "raw.esk_bulk_content", [(dt.datetime(2026, 9, 12, 2), "International Exports", 1200.0)])
    df = materialize(con, "staging.international_trade_hourly")
    assert len(df) == 1
    assert df.iloc[0]["imports_mw"] == 950.0 and df.iloc[0]["exports_mw"] == 1200.0


def test_uclf_oclf_trend_latest_revision_not_average(con):
    # 22 Sep 07:00: latest captured CSV says 7,683.818; older payloads differ.
    hour = "2026-09-22 07:00:00"
    for h, first, v in (("a", "2026-09-23 04:10:00", 6900.0),
                        ("b", "2026-09-24 04:10:00", 6826.0),
                        ("c", "2026-09-25 04:10:00", 7683.818)):
        insert(con, "raw.uclf_oclf_trend_csv_content", [(h, "u", "t", seen(first))])
        insert(con, "raw.uclf_oclf_trend_csv", [(h, utc_wall(hour), "Hourly UCLF+OCLF", v)])
    # PowerBI backup supplies an hour the CSV lacks; its revisions resolve too
    pbi_payload(con, "uclf_oclf_trend_powerbi", "p1", "2026-09-25 05:00:00", [],
                [("2026-09-25 01:00:00", "Hourly UCLF+OCLF", 7000.0)])
    pbi_payload(con, "uclf_oclf_trend_powerbi", "p2", "2026-09-26 05:00:00", [],
                [("2026-09-25 01:00:00", "Hourly UCLF+OCLF", 7100.0)])
    df = materialize(con, "staging.uclf_oclf_trend_hourly").set_index("timestamp")
    assert df.loc[dt.datetime(2026, 9, 22, 7), "uclf_oclf_mw"] == 7683.818
    assert df.loc[dt.datetime(2026, 9, 22, 7), "source"] == "trend_csv"
    assert df.loc[dt.datetime(2026, 9, 25, 1), "uclf_oclf_mw"] == 7100.0
    assert df.loc[dt.datetime(2026, 9, 25, 1), "source"] == "trend_powerbi"


def test_demand_capacity_latest_revision_and_alignment(con):
    hour = "2026-07-10 10:00:00"
    for h, first, v in (("old", "2026-07-11 04:00:00", 22000.0), ("new", "2026-07-12 04:00:00", 22791.687)):
        insert(con, "raw.demand_capacity_csv_content", [(h, "u", 200, "t", seen(first))])
        insert(con, "raw.demand_capacity_csv", [(h, utc_wall(hour), "Residual Demand", v)])
    insert(con, "raw.demand_capacity_eskom_sqlite_fetch",
           [(utc_wall("2026-07-10 11:00:00"), "Residual Demand", 21814.812)])
    df = materialize(con, "staging.demand_capacity_hourly").set_index("timestamp")
    assert df.loc[dt.datetime(2026, 7, 10, 10), "residual_demand"] == 22791.687
    assert df.loc[dt.datetime(2026, 7, 10, 11), "residual_demand"] == 21814.812


# ---------- Fix 1: one coherent weekly snapshot ----------

WEEKLY = "raw.weekly_capacity_breakdown_powerbi"


def weekly_snapshot(c, response_hash, first_seen, week, eaf, pclf, uclf, oclf, scrapes=()):
    insert(c, f"{WEEKLY}_content", [(response_hash, "v", "T", "{}", "{}", seen(first_seen))])
    insert(c, f"{WEEKLY}_scrapes", [(seen(s), "v", "T", response_hash, None) for s in scrapes])
    insert(c, WEEKLY, [(response_hash, "v", "T", utc_wall(week + " 00:00:00"), s, v)
                       for s, v in (("Weekly EAF", eaf), ("Weekly PCLF", pclf),
                                    ("Weekly UCLF", uclf), ("Weekly OCLF", oclf))])


def test_weekly_official_takes_one_coherent_latest_snapshot(con):
    # Each published snapshot sums to 100; component-wise MAX would give
    # 60 + 12 + 26 + 4 = 102.
    weekly_snapshot(con, "r-old", "2026-09-01 08:00:00", "2026-08-31", 58.0, 12.0, 26.0, 4.0)
    weekly_snapshot(con, "r-new", "2026-09-08 08:00:00", "2026-08-31", 60.0, 11.0, 25.0, 4.0)
    # A later response that lacks one factor for the week is not a valid snapshot.
    insert(con, f"{WEEKLY}_content", [("r-partial", "v", "T", "{}", "{}", seen("2026-09-09 08:00:00"))])
    insert(con, WEEKLY, [("r-partial", "v", "T", utc_wall("2026-08-31 00:00:00"), "Weekly EAF", 99.0)])
    insert(con, "raw.eskom_metrics_weekly_breakdown",
           [(dt.date(2026, 8, 31), 50.0, 20.0, 25.0, 5.0, "sqlite"),
            (dt.date(2019, 4, 1), 70.0, 10.0, 17.0, 3.0, "sqlite")])
    df = materialize(con, "staging.eaf_weekly_official")
    df = df.set_index(df.week_start.astype(str))
    wk = df.loc["2026-08-31"]
    assert (wk.eaf_pct, wk.pclf_pct, wk.uclf_pct, wk.oclf_pct, wk.src) == (60.0, 11.0, 25.0, 4.0, "powerbi")
    assert df.loc["2019-04-01", "src"] == "metrics_sqlite"  # history preserved
    sums = df.eaf_pct + df.pclf_pct + df.uclf_pct + df.oclf_pct
    assert (sums.round(6) == 100).all()


def test_weekly_official_rescraped_old_snapshot_wins_by_last_observation(con):
    weekly_snapshot(con, "r1", "2026-09-01 08:00:00", "2026-08-31", 58.0, 12.0, 26.0, 4.0,
                    scrapes=["2026-09-10 08:00:00"])
    weekly_snapshot(con, "r2", "2026-09-08 08:00:00", "2026-08-31", 60.0, 11.0, 25.0, 4.0)
    df = materialize(con, "staging.eaf_weekly_official")
    assert df.iloc[0]["eaf_pct"] == 58.0


# ---------- Fix 3: SAST wall-clock end to end, session independent ----------

def test_esk_bulk_content_keeps_sast_wall_clock_across_dst(con):
    # Hours either side of both 2025 European DST changes, plus month ends.
    hours = ["2025-03-30 01:00:00", "2025-03-30 02:00:00", "2025-03-30 03:00:00",
             "2025-10-26 01:00:00", "2025-10-26 02:00:00", "2025-10-26 03:00:00",
             "2026-07-10 10:00:00", "2026-07-31 23:00:00", "2026-08-01 00:00:00"]
    insert(con, "raw.esk_bulk_fetch", [(utc_wall(h), "Residual Demand", str(i)) for i, h in enumerate(hours)])
    df = materialize(con, "raw.esk_bulk_content")
    assert [str(t) for t in df["timestamp"]] == hours  # no shift, no merged/missing hours
    assert list(df["value"]) == [float(i) for i in range(len(hours))]


def test_bulk_demand_and_csv_generation_share_the_hour(con):
    hour = "2026-07-10 10:00:00"
    insert(con, "raw.esk_bulk_fetch", [(utc_wall(hour), "Residual Demand", "22791.687"),
                                       (utc_wall(hour), "Total PCLF", "5000"),
                                       (utc_wall(hour), "Total UCLF", "12000"),
                                       (utc_wall(hour), "Installed Eskom Capacity", "47000")])
    materialize(con, "raw.esk_bulk_content")
    csv_payload(con, SBU_SLUG, "c", "2026-07-11 04:10:00", [],
                [(hour, "Thermal_Gen_Excl_Pumping_and_SCO", 18000.0)])
    gen = materialize(con, "staging.supply_build_up")
    out = materialize(con, "staging.outage_metrics_hourly")
    assert list(gen["timestamp"]) == list(out["timestamp"]) == [dt.datetime(2026, 7, 10, 10)]
    assert out.iloc[0]["residual_demand_mw"] == 22791.687


def test_daily_buckets_are_sast_days(con):
    # 23:00 and 00:00 SAST are on different days whatever the session zone.
    for h, v in (("2026-09-21 23:00:00", 1.0), ("2026-09-22 00:00:00", 2.0)):
        insert(con, "raw.uclf_oclf_trend_csv_content", [(h, "u", "t", seen("2026-09-23 04:00:00"))])
        insert(con, "raw.uclf_oclf_trend_csv", [(h, utc_wall(h), "Hourly UCLF+OCLF", v)])
    df = materialize(con, "staging.uclf_oclf_trend_hourly")
    days = con.execute("SELECT timestamp::DATE, uclf_oclf_mw FROM staging.uclf_oclf_trend_hourly ORDER BY 1").fetchall()
    assert days == [(dt.date(2026, 9, 21), 1.0), (dt.date(2026, 9, 22), 2.0)]
    assert str(df["timestamp"].dtype).startswith("datetime64")  # naive, not tz-aware


# ---------- dashboard loaders ----------

def dashboard_ns():
    """generate_beta's functions without running its top-level main()."""
    import ast
    from pathlib import Path
    path = Path(__file__).parents[1] / "assets/dashboard/generate_beta.py"
    tree = ast.parse(path.read_text())
    tree.body = [n for n in tree.body if not (
        isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name) and n.value.func.id == "main")]
    ns = {"__file__": str(path)}
    exec(compile(tree, str(path), "exec"), ns)
    return ns


def test_chart_epoch_encodes_sast_wall_clock(con):
    ns = dashboard_ns()
    naive = ns["_ts_ms"](dt.datetime(2026, 7, 10, 10))
    # raw TIMESTAMPTZ values come back in the session zone; same instant
    aware = con.execute("SELECT TIMESTAMPTZ '2026-07-10 10:00:00+00'").fetchone()[0]
    assert ns["_ts_ms"](aware) == naive
    assert dt.datetime.fromtimestamp(naive / 1000, dt.timezone.utc).hour == 10


def test_ocgt_offpeak_uses_sast_hours():
    ns = dashboard_ns()
    ms = lambda h: ns["_ts_ms"](dt.datetime(2026, 10, 20, h))
    # 18:00 SAST is peak; 16:00 SAST is off-peak (read +2 h, it lands in peak)
    merged = {ms(18): {"Eskom_OCGT_Generation": 900.0},
              ms(16): {"Eskom_OCGT_Generation": 800.0},
              ms(22): {"Eskom_OCGT_Generation": 0.0}}
    out = ns["compute_outlook"](merged, None, None, None, None)
    m = {x["id"]: x["value"] for x in out["metrics"]}
    assert m["ocgt-offpeak"] == 1


def test_portal_series_latest_revision_wins(con):
    ns = dashboard_ns()
    slug = "demand-side/official-hourly-forcast-for-next-3-months"
    hour = "2026-10-25 18:00:00"
    csv_payload(con, slug, "new", "2026-10-22 04:10:00", [], [(hour, "Residual Forecast", 27000.0)])
    csv_payload(con, slug, "old", "2026-10-21 04:10:00", [], [(hour, "Residual Forecast", 26000.0)])
    con.execute("CREATE TABLE raw.portal_powerbi (slug VARCHAR, response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, timestamp TIMESTAMPTZ, series VARCHAR, value DOUBLE)")
    con.execute("CREATE TABLE raw.portal_powerbi_content (slug VARCHAR, response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_json VARCHAR, metadata_json VARCHAR, first_seen_at TIMESTAMPTZ)")
    con.execute("CREATE TABLE raw.portal_powerbi_scrapes (scraped_at TIMESTAMPTZ, slug VARCHAR, page_url VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_hash VARCHAR, error VARCHAR)")
    out = ns["_portal_series"](con, slug)
    assert out == {"Residual Forecast": {ns["_ts_ms"](dt.datetime(2026, 10, 25, 18)): 27000.0}}
