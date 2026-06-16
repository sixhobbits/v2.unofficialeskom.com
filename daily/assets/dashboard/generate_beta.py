""" @bruin
name: dashboard.generate_beta
tags:
    - hourly
depends:
    - staging.supply_build_up
    - staging.international_trade_hourly
    - staging.outage_metrics_hourly
    - staging.outage_metrics_daily
    - staging.uclf_oclf_yoy_daily
    - staging.eaf_yoy_weekly
    - staging.capacity_yoy_weekly
    - staging.peak_demand_yoy_weekly
    - staging.rooftop_pv_monthly
    - staging.weekly_status_outlook
    - raw.portal_csv
    - raw.portal_powerbi

description: |
    Generates beta.unofficialeskom.com/index.html. Reads exclusively from
    staging.* tables — no raw.* or external SQLite. Chart→column lineage is
    declared in CHART_SOURCES and validated against duckdb's information_schema
    at build time so a renamed staging column fails the build instead of
    silently emptying a chart. The rendered HTML carries a "Data sources"
    panel derived from the same manifest.
@bruin """

import json
import re
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

import duckdb

INSTALLED_CAPACITY_MW = 47276.0  # Eskom installed capacity; CLF % ↔ MW conversion

ROOT           = Path(__file__).resolve().parents[3]
DB_PATH        = ROOT / "warehouse" / "eskom.duckdb"
WEEKLY_DB_PATH = ROOT / "warehouse" / "media_presentations" / "index.duckdb"
OUT_PATH       = ROOT / "beta.unofficialeskom.com" / "static" / "dashboard-data.json"

# staging.supply_build_up column → key used in build_series()
STAGING_COL_MAP = {
    "thermal_gen_excl_pumping_and_sco": "Thermal_Generation",
    "nuclear_generation":               "Nuclear_Generation",
    "eskom_ocgt_generation":            "Eskom_OCGT_Generation",
    "eskom_gas_generation":             "Eskom_Gas_Generation",
    "dispatchable_ipp_ocgt":            "Dispatchable_IPP_OCGT",
    "hydro_water_generation":           "Hydro_Water_Generation",
    "pumped_water_generation":          "Pumped_Water_Generation",
    "international_imports":            "International_Imports",
    "ils_usage":                        "ILS_Usage",
    "manual_load_reduction_mlr":        "Manual_Load_Reduction_MLR",
    "ios_excl_ils_and_mlr":             "IOS_Excl_ILS_and_MLR",
    "wind":                             "Wind",
    "pv":                               "PV",
    "csp":                              "CSP",
    "other_re":                         "Other_RE",
}

# Chart-id → list of "schema.table.column" refs that feed it. Used both to
# validate the staging contract at build time and to render the provenance
# footer in the HTML.
CHART_SOURCES: dict[str, list[str]] = {
    "headline-generation": [f"staging.supply_build_up.{c}" for c in STAGING_COL_MAP],
    "headline-demand":     ["staging.outage_metrics_hourly.residual_demand_mw"],
    "headline-eaf":        ["staging.outage_metrics_daily.eaf_pct"],
    "chart-thermal":       ["staging.supply_build_up.thermal_gen_excl_pumping_and_sco"],
    "chart-nuclear":       ["staging.supply_build_up.nuclear_generation"],
    "chart-ocgt":          ["staging.supply_build_up.eskom_ocgt_generation",
                            "staging.supply_build_up.dispatchable_ipp_ocgt"],
    "chart-outage-stack":  ["staging.outage_metrics_daily.eaf_pct",
                            "staging.outage_metrics_daily.pclf_pct",
                            "staging.outage_metrics_daily.uclf_pct",
                            "staging.outage_metrics_daily.oclf_pct"],
    "chart-uclf-oclf-yoy": ["staging.uclf_oclf_yoy_daily.year",
                            "staging.uclf_oclf_yoy_daily.mmdd",
                            "staging.uclf_oclf_yoy_daily.daily_avg_pct"],
    "chart-outage-split": ["staging.outage_metrics_daily.pclf_pct",
                           "staging.outage_metrics_daily.uclf_pct",
                           "staging.outage_metrics_daily.oclf_pct"],
    "chart-gen-demand-yoy": ["staging.supply_build_up.thermal_gen_excl_pumping_and_sco",
                             "staging.outage_metrics_hourly.residual_demand_mw"],
    "chart-station-hourly": [f"staging.supply_build_up.{c}" for c in STAGING_COL_MAP],
    "chart-eaf-outage-hourly": ["staging.outage_metrics_hourly.eaf_pct",
                                "staging.outage_metrics_hourly.pclf_pct",
                                "staging.outage_metrics_hourly.uclf_pct",
                                "staging.outage_metrics_hourly.oclf_pct"],
    "chart-trade":         ["staging.international_trade_hourly.imports_mw",
                            "staging.international_trade_hourly.exports_mw"],
    "chart-gen-demand":    ["staging.demand_capacity_hourly.available_capacity",
                            "staging.demand_capacity_hourly.residual_demand"],
    "chart-renewables":    ["staging.supply_build_up.wind",
                            "staging.supply_build_up.pv",
                            "staging.supply_build_up.csp",
                            "staging.supply_build_up.other_re"],
    "chart-rooftop-pv":    ["staging.rooftop_pv_monthly.observation_date",
                            "staging.rooftop_pv_monthly.province",
                            "staging.rooftop_pv_monthly.installed_mw"],
    "chart-rooftop-pv-per-household": [
        "staging.rooftop_pv_monthly.observation_date",
        "staging.rooftop_pv_monthly.province",
        "staging.rooftop_pv_monthly.installed_mw",
        # households per province baked into the asset (Statista 2022)
    ],
    "outlook-status-forecast": ["staging.weekly_status_outlook.week_start",
                                "staging.weekly_status_outlook.likely_risk_mw",
                                "staging.weekly_status_outlook.status"],
}


def validate_chart_sources(conn: duckdb.DuckDBPyConnection) -> None:
    """Fail loudly if any column referenced by CHART_SOURCES is missing.

    Catches the silently-empty-chart class of bug where someone renames a
    staging column and the dashboard build keeps "succeeding".
    """
    refs = {ref for cols in CHART_SOURCES.values() for ref in cols}
    rows = conn.execute(
        "SELECT table_schema || '.' || table_name || '.' || column_name "
        "FROM information_schema.columns"
    ).fetchall()
    have = {r[0] for r in rows}
    missing = sorted(refs - have)
    if missing:
        raise RuntimeError(
            "CHART_SOURCES references columns missing from duckdb: "
            + ", ".join(missing)
        )
    print(f"  CHART_SOURCES: validated {len(refs)} column refs across {len(CHART_SOURCES)} charts")


def _ts_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def load_generation_mix(conn: duckdb.DuckDBPyConnection) -> dict[int, dict[str, float]]:
    df = conn.execute(
        "SELECT * FROM staging.supply_build_up ORDER BY timestamp"
    ).df()
    out: dict[int, dict[str, float]] = {}
    for _, row in df.iterrows():
        ts = row["timestamp"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        ts_ms = _ts_ms(ts)
        rec: dict[str, float] = {}
        for col, key in STAGING_COL_MAP.items():
            v = row.get(col)
            if v is not None and str(v) not in ("nan", "None"):
                try:
                    rec[key] = float(v)
                except (TypeError, ValueError):
                    pass
        if rec:
            out[ts_ms] = rec
    print(f"  staging.supply_build_up: {len(out)} hourly rows")
    return out


def load_outage_metrics(conn: duckdb.DuckDBPyConnection) -> dict[int, dict[str, float]]:
    """Load hourly residual demand from staging (only field still consumed here)."""
    rows = conn.execute(
        "SELECT timestamp, residual_demand_mw "
        "FROM staging.outage_metrics_hourly "
        "WHERE residual_demand_mw IS NOT NULL ORDER BY timestamp"
    ).fetchall()
    out: dict[int, dict[str, float]] = {}
    for ts, v in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out[_ts_ms(ts)] = {"Residual_Demand": float(v)}
    print(f"  staging.outage_metrics_hourly: {len(out)} residual-demand hours")
    return out


def load_uclf_oclf_by_year(conn: duckdb.DuckDBPyConnection) -> dict:
    rows = conn.execute(
        "SELECT year, mmdd, daily_avg_pct FROM staging.uclf_oclf_yoy_daily "
        "ORDER BY year, mmdd"
    ).fetchall()
    by_year_map: dict[str, dict[str, float]] = {}
    for year, mmdd, pct in rows:
        by_year_map.setdefault(year, {})[mmdd] = round(float(pct), 2)
    x_keys = sorted({mmdd for d in by_year_map.values() for mmdd in d})
    by_year = {
        year: [by_year_map[year].get(k) for k in x_keys]
        for year in sorted(by_year_map)
    }
    print(f"  staging.uclf_oclf_yoy_daily: {len(x_keys)} day buckets, {len(by_year)} years")
    return {"x_keys": x_keys, "by_year": by_year}


def load_yoy_weekly(conn: duckdb.DuckDBPyConnection, table: str, value_col: str) -> dict:
    """Pivot a (year, week, value) staging table into {weeks: [1..52],
    by_year: {year: [52 values]}} for a weekly year-over-year chart."""
    rows = conn.execute(
        f"SELECT year, week, {value_col} FROM {table} ORDER BY year, week"
    ).fetchall()
    weeks = list(range(1, 53))
    by_year_map: dict[str, dict[int, float]] = {}
    for year, week, v in rows:
        by_year_map.setdefault(year, {})[int(week)] = round(float(v), 2)
    by_year = {
        year: [by_year_map[year].get(w) for w in weeks]
        for year in sorted(by_year_map)
    }
    print(f"  {table}: {len(by_year)} years, {len(weeks)} weeks")
    return {"weeks": weeks, "by_year": by_year}


def load_outage_daily(conn: duckdb.DuckDBPyConnection) -> dict:
    """Load merged daily outage metrics. Already daily-averaged in SQL."""
    rows = conn.execute(
        "SELECT day, eaf_pct, pclf_pct, uclf_pct, oclf_pct, "
        "pclf_src, uclf_src, oclf_src "
        "FROM staging.outage_metrics_daily ORDER BY day"
    ).fetchall()
    eaf, pclf, uclf, oclf = [], [], [], []
    # Capability loss factors in MW (pct of installed capacity → MW), plus their
    # total — for the Outages "Capability loss factors" chart.
    clf_planned, clf_unplanned, clf_other, clf_total = [], [], [], []
    latest_eaf = latest_eaf_ts = None
    src_counts: dict[str, int] = {}
    for day, e, p, u, o, ps, us, os_ in rows:
        dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        ts = _ts_ms(dt)
        eaf.append([ts, round(e, 1)])
        pclf.append([ts, round(p, 1) if p is not None else None])
        uclf.append([ts, round(u, 1) if u is not None else None])
        oclf.append([ts, round(o, 1) if o is not None else None])
        p_mw = (p or 0.0) / 100 * INSTALLED_CAPACITY_MW
        u_mw = (u or 0.0) / 100 * INSTALLED_CAPACITY_MW
        o_mw = (o or 0.0) / 100 * INSTALLED_CAPACITY_MW
        clf_planned.append([ts, round(p_mw)])
        clf_unplanned.append([ts, round(u_mw)])
        clf_other.append([ts, round(o_mw)])
        clf_total.append([ts, round(p_mw + u_mw + o_mw)])
        latest_eaf = e
        latest_eaf_ts = ts
        for s in (ps, us, os_):
            if s:
                src_counts[s] = src_counts.get(s, 0) + 1
    print(f"  staging.outage_metrics_daily: {len(rows)} days, src tally={src_counts}")
    return {
        "eaf_avg":       eaf,
        "pclf_avg":      pclf,
        "uclf_avg":      uclf,
        "oclf_avg":      oclf,
        "clf_planned":   clf_planned,
        "clf_unplanned": clf_unplanned,
        "clf_other":     clf_other,
        "clf_total":     clf_total,
        "latest_eaf":    round(latest_eaf, 1) if latest_eaf is not None else None,
        "latest_eaf_ts": latest_eaf_ts,
    }


def load_demand_capacity(conn: duckdb.DuckDBPyConnection) -> dict:
    """Hourly Available Capacity + Residual Demand from staging.

    The merged staging table prefers PowerBI > CSV > legacy. Coverage is
    continuous 2022-10 through 2026-02, then a gap (Eskom's CSV link broke
    Feb 22), then the past ~5–7 days from the PowerBI iframe.
    """
    rows = conn.execute(
        "SELECT timestamp, available_capacity, residual_demand, headroom "
        "FROM staging.demand_capacity_hourly "
        "ORDER BY timestamp"
    ).fetchall()
    cap_h: list[list] = []
    dem_h: list[list] = []
    hr_h: list[list] = []
    for ts, cap, dem, hr in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_ms = _ts_ms(ts)
        if cap is not None: cap_h.append([ts_ms, float(cap)])
        if dem is not None: dem_h.append([ts_ms, float(dem)])
        if hr is not None:  hr_h.append([ts_ms, float(hr)])
    # Tightest headroom (capacity − demand) over the most recent 3 days — how
    # close the grid came to the edge. Anchored to the headroom feed's own
    # latest hour, which can lead the supply feed by an hour or two.
    headroom_min_3d = None
    if hr_h:
        latest = hr_h[-1][0]
        d3 = latest - 3 * 86_400_000
        recent = [v for ts, v in hr_h if ts >= d3]
        if recent:
            headroom_min_3d = round(min(recent))
    print(f"  staging.demand_capacity_hourly: {len(cap_h)} capacity / {len(dem_h)} demand / {len(hr_h)} headroom hours; 3d-min headroom {headroom_min_3d}")
    return {
        "available_capacity_avg": _agg(cap_h, "mean"),
        "demand_capacity_residual_demand_avg": _agg(dem_h, "mean"),
        "headroom_avg": _agg(hr_h, "mean"),
        "headroom_min_3d": headroom_min_3d,
    }


def load_trade(conn: duckdb.DuckDBPyConnection) -> dict[str, list[list]]:
    """Load hourly imports + exports from the trade staging table."""
    rows = conn.execute(
        "SELECT timestamp, imports_mw, exports_mw "
        "FROM staging.international_trade_hourly ORDER BY timestamp"
    ).fetchall()
    imports_h: list[list] = []
    exports_h: list[list] = []
    for ts, imp, exp in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_ms = _ts_ms(ts)
        if imp is not None: imports_h.append([ts_ms, float(imp)])
        if exp is not None: exports_h.append([ts_ms, float(exp)])
    print(f"  staging.international_trade_hourly: {len(imports_h)} import / {len(exports_h)} export hours")
    return {"imports_avg": _agg(imports_h, "mean"), "exports_avg": _agg(exports_h, "mean")}


# Statista 2022 — total number of households per province (thousands).
# Used to normalise installed rooftop PV into W/household.
HOUSEHOLDS_K_2022 = {
    "Gauteng":       5587,
    "KwaZulu-Natal": 3200,
    "Western Cape":  2079,
    "Eastern Cape":  1742,
    "Limpopo":       1729,
    "Mpumalanga":    1445,
    "North-West":    1349,
    "Free State":     975,
    "Northern Cape":  371,
}


def load_rooftop_pv(conn: duckdb.DuckDBPyConnection) -> dict:
    rows = conn.execute(
        "SELECT observation_date, province, installed_mw "
        "FROM staging.rooftop_pv_monthly ORDER BY observation_date"
    ).fetchall()
    raw: dict[str, list[list]] = {}
    per_hh: dict[str, list[list]] = {}
    latest_by_prov: dict[str, float] = {}
    missing_hh: set[str] = set()
    for obs_date, province, mw in rows:
        dt = datetime(obs_date.year, obs_date.month, obs_date.day, tzinfo=timezone.utc)
        ts = _ts_ms(dt)
        mw_f = float(mw)
        raw.setdefault(province, []).append([ts, round(mw_f, 1)])
        latest_by_prov[province] = mw_f
        hh_k = HOUSEHOLDS_K_2022.get(province)
        if hh_k:
            # W per household = (MW * 1_000_000) / (households_k * 1000) = MW * 1000 / households_k
            per_hh.setdefault(province, []).append([ts, round(mw_f * 1000 / hh_k, 1)])
        else:
            missing_hh.add(province)
    ordered = sorted(latest_by_prov, key=latest_by_prov.get, reverse=True)
    # Per-household ordering: by latest W/household, descending
    latest_per_hh = {
        p: (per_hh[p][-1][1] if p in per_hh and per_hh[p] else 0.0)
        for p in latest_by_prov
    }
    ordered_per_hh = sorted(
        [p for p in latest_by_prov if p in per_hh],
        key=latest_per_hh.get,
        reverse=True,
    )
    if missing_hh:
        print(f"  rooftop households lookup missing: {sorted(missing_hh)}")
    print(f"  staging.rooftop_pv_monthly: {len(ordered)} provinces")
    return {
        "provinces":         ordered,
        "series":            {p: raw[p] for p in ordered},
        "provinces_per_hh":  ordered_per_hh,
        "series_per_hh":     {p: per_hh[p] for p in ordered_per_hh},
    }


def load_portal_catalog(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Flat catalogue of every Eskom Data Portal graph for the Source Data page.

    The graph list + stable portal page URLs come from eskom_portal.catalog;
    the volatile CSV / PowerBI links and the freshness (latest scraped data
    point, SAST) are read from the generic raw.portal_csv* / raw.portal_powerbi*
    sweeps, so both update on every run.

    Per type we emit {url, latest, rows}: url is the discovered download/embed
    link (None if the portal offers none), latest is the newest data date we
    hold (None if we parsed no dated rows), rows is the parsed point count.
    """
    from eskom_portal.catalog import PORTAL_GRAPHS

    # Latest discovered links (fetch tables are create+replace → this run only).
    csv_url = dict(conn.execute(
        "SELECT slug, csv_url FROM raw.portal_csv_fetch WHERE csv_url IS NOT NULL"
    ).fetchall())
    pbi_url = dict(conn.execute(
        "SELECT slug, ANY_VALUE(embed_url) FROM raw.portal_powerbi_fetch "
        "WHERE embed_url IS NOT NULL GROUP BY slug"
    ).fetchall())

    # Last time the CSV content hash changed vs the previous run (SAST date).
    # portal_csv_scrapes is append-only, one row per (slug, run). A hash change
    # means Eskom published data we hadn't seen before.
    csv_published: dict[str, str | None] = {
        row[0]: row[1]
        for row in conn.execute("""
            WITH ranked AS (
                SELECT slug, scraped_at, content_hash,
                    LAG(content_hash) OVER (PARTITION BY slug ORDER BY scraped_at) AS prev_hash
                FROM raw.portal_csv_scrapes
            ),
            changes AS (
                SELECT slug, scraped_at FROM ranked
                WHERE prev_hash IS NOT NULL
                  AND content_hash IS NOT NULL
                  AND content_hash != prev_hash
            )
            SELECT slug,
                strftime(timezone('Africa/Johannesburg', MAX(scraped_at)), '%Y-%m-%d')
            FROM changes GROUP BY slug
        """).fetchall()
    }

    # Last time the PowerBI response hash changed per slug (SAST date).
    # portal_powerbi_content is a merge table keyed on (slug, response_hash);
    # first_seen_at is set once when each new hash is first ingested and never
    # updated. MAX(first_seen_at) per slug = when the content last changed.
    pbi_published: dict[str, str | None] = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT slug, "
            "strftime(timezone('Africa/Johannesburg', MAX(first_seen_at)), '%Y-%m-%d') "
            "FROM raw.portal_powerbi_content GROUP BY slug"
        ).fetchall()
    }

    def freshness(table: str) -> dict[str, tuple]:
        return {
            row[0]: (row[1], int(row[2]))
            for row in conn.execute(
                "SELECT slug, "
                "strftime(timezone('Africa/Johannesburg', MAX(timestamp)), '%Y-%m-%d') AS latest, "
                "COUNT(value) AS rows "
                f"FROM {table} GROUP BY slug"
            ).fetchall()
        }

    csv_fresh = freshness("raw.portal_csv")
    pbi_fresh = freshness("raw.portal_powerbi")

    def cell(slug: str, url_map: dict, fresh: dict, published: dict) -> dict:
        latest, rows = fresh.get(slug, (None, 0))
        return {"url": url_map.get(slug), "latest": latest, "rows": rows,
                "published": published.get(slug)}

    catalog = []
    for g in PORTAL_GRAPHS:
        csv = cell(g["slug"], csv_url, csv_fresh, csv_published)
        pbi = cell(g["slug"], pbi_url, pbi_fresh, pbi_published)
        # We don't care which source it came from — surface the freshest data
        # point we hold for the graph (the later of the two dates), and whether
        # we hold any rows at all.
        latest = max((d for d in (csv["latest"], pbi["latest"]) if d), default=None)
        rows = max(csv["rows"], pbi["rows"])
        catalog.append({
            "section": g["section"],
            "name":    g["name"],
            "slug":    g["slug"],
            "page":    g["page_url"],
            "csv":     csv,
            "powerbi": pbi,
            "latest":  latest,
            "rows":    rows,
        })
    scraped = sum(1 for c in catalog if c["rows"])
    print(f"  portal catalog: {len(catalog)} graphs, {scraped} with scraped data")
    return catalog


def load_station_hourly(conn: duckdb.DuckDBPyConnection, days: int = 92) -> dict:
    """Hourly generation mix (the 'station build-up' stack) for the last ~3
    months — kept short so the dashboard JSON stays small."""
    rows = conn.execute(
        "SELECT timestamp, "
        "TRY_CAST(thermal_gen_excl_pumping_and_sco AS DOUBLE), "
        "TRY_CAST(nuclear_generation AS DOUBLE), "
        "COALESCE(TRY_CAST(eskom_ocgt_generation AS DOUBLE),0)"
        "+COALESCE(TRY_CAST(dispatchable_ipp_ocgt AS DOUBLE),0)"
        "+COALESCE(TRY_CAST(eskom_gas_generation AS DOUBLE),0), "
        "TRY_CAST(hydro_water_generation AS DOUBLE), "
        "TRY_CAST(pumped_water_generation AS DOUBLE), "
        "TRY_CAST(international_imports AS DOUBLE), "
        "TRY_CAST(wind AS DOUBLE), TRY_CAST(pv AS DOUBLE), "
        "COALESCE(TRY_CAST(csp AS DOUBLE),0)+COALESCE(TRY_CAST(other_re AS DOUBLE),0) "
        "FROM staging.supply_build_up "
        f"WHERE timestamp > (SELECT max(timestamp) FROM staging.supply_build_up) - INTERVAL {days} DAY "
        "ORDER BY timestamp"
    ).fetchall()
    keys = ["coal", "nuclear", "ocgt", "hydro", "pumped", "imports", "wind", "pv", "otherRe"]
    out: dict[str, list] = {k: [] for k in keys}
    for r in rows:
        ts = _ts_ms(r[0])
        for i, k in enumerate(keys):
            v = r[i + 1]
            out[k].append([ts, round(v, 1) if v is not None else None])
    print(f"  station hourly: {len(rows)} hours x {len(keys)} sources")
    return out


def load_outage_hourly(conn: duckdb.DuckDBPyConnection, days: int = 92) -> dict:
    """Hourly EAF + capability-loss split (%) for the last ~3 months.

    The bulk feed (staging.outage_metrics_hourly) lags ~a few days, so the most
    recent hours — exactly the ones that explain a dip in the EAF headline — are
    missing. We append those from the hourly UCLF+OCLF trend CSV, holding PCLF
    and OCLF at the last bulk value (PCLF only publishes weekly), and derive EAF.
    """
    rows = conn.execute(
        "SELECT timestamp, eaf_pct, pclf_pct, uclf_pct, oclf_pct "
        "FROM staging.outage_metrics_hourly "
        f"WHERE timestamp > (SELECT max(timestamp) FROM staging.outage_metrics_hourly) - INTERVAL {days} DAY "
        "ORDER BY timestamp"
    ).fetchall()
    out: dict[str, list] = {"eaf": [], "pclf": [], "uclf": [], "oclf": []}
    last_ts = last_pclf = last_oclf = None
    for ts, e, p, u, o in rows:
        t = _ts_ms(ts)
        out["eaf"].append([t, round(e, 1) if e is not None else None])
        out["pclf"].append([t, round(p, 1) if p is not None else None])
        out["uclf"].append([t, round(u, 1) if u is not None else None])
        out["oclf"].append([t, round(o, 1) if o is not None else None])
        last_ts, last_pclf, last_oclf = ts, p, o

    # Recent tail from the trend CSV (hourly UCLF+OCLF in MW), where the bulk
    # feed hasn't reached yet. PCLF/OCLF held at the last bulk value.
    tail_n = 0
    if last_ts is not None and last_pclf is not None:
        tail = conn.execute(
            "SELECT timestamp, AVG(value) FROM raw.uclf_oclf_trend_csv "
            "WHERE series = 'Hourly UCLF+OCLF' AND timestamp > ? GROUP BY 1 ORDER BY 1",
            [last_ts],
        ).fetchall()
        held_oclf = last_oclf or 0.0
        for ts, combined_mw in tail:
            combined_pct = combined_mw / INSTALLED_CAPACITY_MW * 100
            uclf = max(0.0, combined_pct - held_oclf)
            eaf = 100 - last_pclf - uclf - held_oclf
            t = _ts_ms(ts)
            out["eaf"].append([t, round(eaf, 1)])
            out["pclf"].append([t, round(last_pclf, 1)])
            out["uclf"].append([t, round(uclf, 1)])
            out["oclf"].append([t, round(held_oclf, 1)])
            tail_n += 1
    print(f"  outage hourly: {len(rows)} bulk + {tail_n} trend-tail hours")
    return out


def load_re_installed(conn: duckdb.DuckDBPyConnection) -> list[list]:
    """Monthly-average Total RE Installed Capacity (MW) from the ESK bulk."""
    rows = conn.execute(
        "SELECT date_trunc('month', timestamp) AS m, avg(TRY_CAST(value AS DOUBLE)) AS v "
        "FROM raw.esk_bulk_fetch "
        "WHERE series = 'Total RE Installed Capacity' AND TRY_CAST(value AS DOUBLE) > 0 "
        "GROUP BY 1 ORDER BY 1"
    ).fetchall()
    out: list[list] = []
    for m, v in rows:
        out.append([_ts_ms(datetime(m.year, m.month, 1, tzinfo=timezone.utc)), round(v)])
    print(f"  RE installed capacity: {len(out)} months")
    return out


def _portal_series(conn: duckdb.DuckDBPyConnection, slug: str) -> dict[str, dict[int, float]]:
    """All dated points we hold for a portal graph, merged across CSV + PowerBI.

    Returns {series_name: {ts_ms: value}}. We don't care which source a point
    came from; later writes (PowerBI usually has fuller coverage) win on a
    timestamp collision.
    """
    out: dict[str, dict[int, float]] = {}
    for tbl in ("raw.portal_csv", "raw.portal_powerbi"):
        rows = conn.execute(
            f"SELECT series, timestamp, value FROM {tbl} "
            "WHERE slug = ? AND timestamp IS NOT NULL AND value IS NOT NULL",
            [slug],
        ).fetchall()
        for series, ts, val in rows:
            out.setdefault(series, {})[_ts_ms(ts)] = float(val)
    return out


def load_outlook_series(conn: duckdb.DuckDBPyConnection) -> dict:
    """Forward-looking series for the Outlook tab: the official 3-month hourly
    forecast and the recent hourly demand / available-capacity actuals."""
    def pts(d: dict[int, float]) -> list[list]:
        return sorted([ts, round(v, 1)] for ts, v in d.items())

    fc = _portal_series(conn, "demand-side/official-hourly-forcast-for-next-3-months")
    dc = _portal_series(conn, "demand-side/system-hourly-demand-and-available-capacity")

    # The demand/capacity report ships the available-capacity series under two
    # spellings (one truncated by Eskom's export) — merge them into one.
    ac: dict[int, float] = {}
    for name, series in dc.items():
        if name.startswith("Available Capacity"):
            ac.update(series)

    forecast = {
        "residual":   pts(fc.get("Residual Forecast", {})),
        "contracted": pts(fc.get("RSA Contracted Forecast", {})),
    }
    demand_capacity = {
        "contractedDemand":  pts(dc.get("RSA Contracted Demand", {})),
        "residualDemand":    pts(dc.get("Residual Demand", {})),
        "availableCapacity": pts(ac),
    }
    print(f"  outlook: forecast {len(forecast['residual'])}h, "
          f"demand/capacity {len(demand_capacity['contractedDemand'])}h")
    return {"forecast": forecast, "demandCapacity": demand_capacity}


def load_status_outlook(conn: duckdb.DuckDBPyConnection) -> dict | None:
    """The latest NTCSA report's 52-week adequacy outlook: green/yellow/orange/
    red week counts, the first at-risk week, and the per-week series."""
    rows = conn.execute(
        "SELECT report_week, report_period, week_start, week_num, "
        "likely_risk_mw, status FROM staging.weekly_status_outlook ORDER BY week_start"
    ).fetchall()
    if not rows:
        return None
    counts = {"green": 0, "yellow": 0, "orange": 0, "red": 0}
    weeks: list[dict] = []
    first_risk = None
    for _, _, ws, wknum, likely, status in rows:
        counts[status] = counts.get(status, 0) + 1
        ws_ms = _ts_ms(datetime(ws.year, ws.month, ws.day, tzinfo=timezone.utc))
        weeks.append({"weekStart": ws_ms, "weekNum": wknum, "status": status, "likelyRiskMw": likely})
        if status != "green" and first_risk is None:
            first_risk = {"weekStart": ws_ms, "weekNum": wknum, "status": status}
    print(f"  status outlook: report wk{rows[0][0]}, {len(weeks)} weeks {counts}")
    return {
        "reportWeek": rows[0][0],
        "reportPeriod": rows[0][1],
        "counts": {**counts, "total": len(weeks)},
        "firstRisk": first_risk,
        "weeks": weeks,
    }


def _iso_week_range(year: int | None, week: int | None) -> str | None:
    if not year or not week:
        return None
    try:
        mon = date.fromisocalendar(year, week, 1)
        sun = date.fromisocalendar(year, week, 7)
    except ValueError:
        return None
    return f"{mon.strftime('%d %b')} – {sun.strftime('%d %b %Y')}"


def load_weekly_reports(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """NTCSA Weekly System Status Reports we hold — for the Source Data page:
    the week each covers, the PDF link, and when we first grabbed it."""
    rows = conn.execute(
        "SELECT report_name, ANY_VALUE(pdf_url) AS pdf_url, MIN(first_seen_at) AS grabbed "
        "FROM raw.weekly_system_status_pdf_content GROUP BY report_name"
    ).fetchall()
    out: list[dict] = []
    for name, pdf_url, grabbed in rows:
        m = re.search(r"_(\d{4})_w(\d+)", name)
        year = int(m.group(1)) if m else None
        week = int(m.group(2)) if m else None
        out.append({
            "name": name,
            "year": year,
            "week": week,
            "period": _iso_week_range(year, week),
            "pdfUrl": pdf_url,
            "grabbedAt": _ts_ms(grabbed) if grabbed else None,
        })
    out.sort(key=lambda r: (r["year"] or 0, r["week"] or 0), reverse=True)
    print(f"  weekly reports: {len(out)}")
    return out


def load_loadshedding(conn: duckdb.DuckDBPyConnection) -> dict:
    """Daily max loadshedding stage from EskomSePush, for the calendar heatmap."""
    try:
        rows = conn.execute(
            "SELECT date, max_stage FROM staging.esp_loadshedding_daily ORDER BY date"
        ).fetchall()
    except Exception as exc:
        print(f"  loadshedding: table not ready ({exc})")
        return {}

    if not rows:
        return {}

    # Convert to [[date_str, stage], ...] for ECharts calendar heatmap
    days = [[str(r[0]), r[1]] for r in rows]

    # Streak: find most recent stage=0 event that is the last event overall
    # (i.e. no loadshedding since that date)
    from datetime import datetime, timezone
    streak_since_ms: int | None = None
    # Work backwards through the raw events to find when loadshedding last ended
    try:
        raw = conn.execute(
            "SELECT event_at, stage FROM raw.esp_loadshedding_fetch ORDER BY event_at DESC LIMIT 50"
        ).fetchall()
        for event_at, stage in raw:
            if stage == 0:
                # This is the most recent "off" event — streak started here
                ts = datetime(event_at.year, event_at.month, event_at.day,
                              event_at.hour, event_at.minute, event_at.second,
                              tzinfo=timezone.utc)
                streak_since_ms = int(ts.timestamp() * 1000)
                break
    except Exception:
        pass

    print(f"  loadshedding: {len(days)} days, streak_since_ms={streak_since_ms}")
    return {
        "days": days,
        "streakSinceMs": streak_since_ms,
    }


def load_annual_financials() -> dict:
    """Load Eskom annual income statement data from the weekly warehouse.

    Returns pivoted series (one list per metric) indexed by year, suitable for
    Chart.js bar/line charts. Reads raw.integrated_results_afs_topline which is
    populated by the weekly pipeline.
    """
    WANTED = {"revenue", "ebitda", "primary_energy", "employee_costs",
              "depreciation", "net_profit", "profit_before_tax"}
    if not WEEKLY_DB_PATH.exists():
        print("  annual financials: weekly warehouse not found, skipping")
        return {}
    try:
        with duckdb.connect(str(WEEKLY_DB_PATH), read_only=True) as conn:
            rows = conn.execute("""
                SELECT financial_year, metric, value_rm
                FROM raw.integrated_results_afs_topline
                WHERE metric IS NOT NULL AND financial_year IS NOT NULL
                ORDER BY financial_year, metric
            """).fetchall()
    except Exception as exc:
        print(f"  annual financials: error reading weekly warehouse: {exc}")
        return {}

    # Pivot: year → {metric: value}
    by_year: dict[int, dict[str, int]] = {}
    for yr, metric, val in rows:
        if metric not in WANTED:
            continue
        by_year.setdefault(yr, {})[metric] = val

    if not by_year:
        return {}

    years = sorted(by_year)
    result: dict = {"years": years}
    for m in sorted(WANTED):
        result[m] = [by_year[y].get(m) for y in years]

    print(f"  annual financials: {len(years)} years ({years[0]}–{years[-1]})")
    return result


# Eskom time-of-use peak windows (SAST): morning 06:00–08:59, evening
# 17:00–20:59. OCGT is a peaking plant, so generation outside these windows
# signals the grid leaning on it under stress.
_SAST = timezone(timedelta(hours=2))
_PEAK_HOURS_SAST = {6, 7, 8, 17, 18, 19, 20}
# OCGT runs a ~150 MW IPP baseload almost continuously, so ">100 MW off-peak"
# fires ~70 h/week even on a healthy grid. Use a real-dispatch floor instead:
# at >500 MW off-peak hours run ~2/week (median), spiking when supply is tight.
_OCGT_OFFPEAK_DISPATCH_MW = 500.0


def compute_outlook(merged: dict[int, dict[str, float]], latest_eaf: float | None,
                    pclf: float | None, uclf: float | None,
                    headroom_min_3d: float | None) -> dict:
    """Derive the Outlook dial metrics + Current Incidents from recent hourly data.

    Thresholds are set from each metric's own 1-year distribution (see the
    one-off analysis in the PR), green/amber/red. Windows are measured back from
    the newest hour we hold, not wall-clock now, so a lagging feed doesn't
    silently clear everything.
    """
    times = sorted(merged)
    if not times:
        return {"metrics": [], "incidents": [], "checks": [], "latestNuclear": None}

    latest = times[-1]
    d7 = latest - 7 * 86_400_000
    d3 = latest - 3 * 86_400_000

    latest_nuclear: float | None = None
    for ts in reversed(times):
        n = merged[ts].get("Nuclear_Generation")
        if n is not None:
            latest_nuclear = round(n)
            break

    # Single pass over the recent windows.
    offpeak_hours = 0
    offpeak_max = 0.0
    ocgt_peak_max = 0.0
    coal_max_7d = 0.0
    pumped_peak_3d = 0.0
    have_7d = False
    red_tools: dict[str, float] = {}
    for ts in times:
        if ts < d7:
            continue
        have_7d = True
        rec = merged[ts]
        ocgt = rec.get("Eskom_OCGT_Generation", 0.0) + rec.get("Dispatchable_IPP_OCGT", 0.0)
        ocgt_peak_max = max(ocgt_peak_max, ocgt)
        if ocgt > _OCGT_OFFPEAK_DISPATCH_MW:
            hr = datetime.fromtimestamp(ts / 1000, _SAST).hour
            if hr not in _PEAK_HOURS_SAST:
                offpeak_hours += 1
                offpeak_max = max(offpeak_max, ocgt)
        coal = rec.get("Thermal_Generation")
        if coal is not None:
            coal_max_7d = max(coal_max_7d, coal)
        if ts >= d3:
            pmp = rec.get("Pumped_Water_Generation")
            if pmp is not None:
                pumped_peak_3d = max(pumped_peak_3d, pmp)
            for key in ("ILS_Usage", "Manual_Load_Reduction_MLR", "IOS_Excl_ILS_and_MLR"):
                v = rec.get(key)
                if v is not None and v > 0:
                    red_tools[key] = max(red_tools.get(key, 0.0), v)

    # ---- Dial metrics. zones are [upTo, color] ascending; the last upTo == max.
    metrics = [
        {"id": "eaf", "label": "Energy Availability Factor", "value": latest_eaf,
         "min": 0, "max": 100, "unit": "%", "decimals": 0,
         "zones": [[50, "bad"], [70, "warn"], [100, "good"]]},
        {"id": "pclf", "label": "Planned outages (PCLF)", "value": pclf,
         "min": 0, "max": 25, "unit": "%", "decimals": 0,
         "zones": [[10, "good"], [16, "warn"], [25, "bad"]]},
        {"id": "uclf", "label": "Unplanned outages (UCLF)", "value": uclf,
         "min": 0, "max": 40, "unit": "%", "decimals": 0,
         "zones": [[20, "good"], [30, "warn"], [40, "bad"]]},
        {"id": "nuclear", "label": "Nuclear output",
         "value": round(latest_nuclear / 1000, 1) if latest_nuclear is not None else None,
         "min": 0, "max": 2, "unit": "GW", "decimals": 1,
         "zones": [[0.9, "bad"], [1.8, "warn"], [2, "good"]]},
        {"id": "coal", "label": "Coal peak (7-day)",
         "value": round(coal_max_7d / 1000, 1) if have_7d else None,
         "min": 0, "max": 28, "unit": "GW", "decimals": 1,
         "zones": [[20, "bad"], [22.5, "warn"], [28, "good"]]},
        {"id": "ocgt-peak", "label": "OCGT peak (7-day)",
         "value": round(ocgt_peak_max / 1000, 1) if have_7d else None,
         "min": 0, "max": 3, "unit": "GW", "decimals": 1,
         "zones": [[0.5, "good"], [1.5, "warn"], [3, "bad"]]},
        {"id": "ocgt-offpeak", "label": "OCGT off-peak hours (7-day)",
         "value": offpeak_hours if have_7d else None,
         "min": 0, "max": 30, "unit": "", "decimals": 0,
         "zones": [[5, "good"], [15, "warn"], [30, "bad"]]},
        {"id": "pumped", "label": "Pumped storage peak (3-day)",
         "value": round(pumped_peak_3d / 1000, 1),
         "min": 0, "max": 3, "unit": "GW", "decimals": 1,
         "zones": [[1, "good"], [2, "warn"], [3, "bad"]]},
        # Headroom (available capacity − demand) at its tightest in the last 3
        # days — how close the grid came to the edge. Negative = deficit, so the
        # dial floor dips below zero. Daily-min headroom near 0 is loadshedding
        # territory; a few GW of buffer is healthy.
        {"id": "headroom", "label": "Headroom min (3-day)",
         "value": round(headroom_min_3d / 1000, 1) if headroom_min_3d is not None else None,
         "min": -2, "max": 12, "unit": "GW", "decimals": 1,
         "zones": [[1, "bad"], [3, "warn"], [12, "good"]]},
    ]

    # ---- Incidents (the user-specified anomaly rules). Active ones surface as
    # cards; the rest list under "monitored, currently normal".
    checks: list[dict] = []

    def add(cid: str, label: str, severity: str, active: bool, detail: str) -> None:
        checks.append({"id": cid, "label": label, "severity": severity,
                       "active": bool(active), "detail": detail})

    add("eaf-low", "EAF below 70%", "high",
        latest_eaf is not None and latest_eaf < 70,
        f"Latest EAF {latest_eaf:.1f}%" if latest_eaf is not None else "No EAF data")

    add("nuclear-low", "Nuclear output below 900 MW", "high",
        latest_nuclear is not None and latest_nuclear < 900,
        f"Latest nuclear {latest_nuclear:,} MW" if latest_nuclear is not None else "No nuclear data")

    add("ocgt-offpeak", "OCGT dispatched outside peak times (last 7 days)", "medium",
        offpeak_hours >= 5,
        f"{offpeak_hours} off-peak hour(s) above {round(_OCGT_OFFPEAK_DISPATCH_MW)} MW, "
        f"up to {round(offpeak_max):,} MW" if offpeak_hours else "No off-peak OCGT dispatch")

    add("ocgt-peak-high", "OCGT peak above 500 MW (last 7 days)", "medium",
        ocgt_peak_max > 500, f"Peak {round(ocgt_peak_max):,} MW")

    add("coal-low", "Max coal below 20 GW (last 7 days)", "high",
        have_7d and coal_max_7d < 20000, f"Peak coal {coal_max_7d / 1000:.1f} GW")

    for key, label in (
        ("ILS_Usage", "Interruptible load (ILS)"),
        ("Manual_Load_Reduction_MLR", "Manual load reduction (MLR)"),
        ("IOS_Excl_ILS_and_MLR", "IOS (excl. ILS & MLR)"),
    ):
        mx = red_tools.get(key, 0.0)
        add(f"reduction-{key}", f"{label} used (last 3 days)", "medium",
            mx > 0, f"Up to {round(mx):,} MW" if mx > 0 else "None")

    incidents = [c for c in checks if c["active"]]
    print(f"  outlook: {len(metrics)} dials, {len(incidents)} active incidents of {len(checks)} checks")
    return {"metrics": metrics, "incidents": incidents, "checks": checks,
            "latestNuclear": latest_nuclear}


def _bucket_by_day(points: list[list]) -> dict[int, list[float]]:
    buckets: dict[int, list[float]] = {}
    for ts, v in points:
        day = ts - (ts % 86_400_000)
        buckets.setdefault(day, []).append(v)
    return buckets


def _agg(points: list[list], how: str) -> list[list]:
    if not points:
        return points
    out: list[list] = []
    for day, vs in sorted(_bucket_by_day(points).items()):
        v = max(vs) if how == "max" else (min(vs) if how == "min" else sum(vs) / len(vs))
        out.append([day, round(v, 1)])
    return out


def _monthly_avg_max(points: list[list]) -> tuple[list, list]:
    """Bucket [ts_ms, value] points by calendar month → (monthly mean, monthly
    max), each [month_ts, value]. Used for OCGT (avg bars + peak line)."""
    buckets: dict[int, list[float]] = {}
    for ts, v in points:
        if v is None:
            continue
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        key = _ts_ms(datetime(dt.year, dt.month, 1, tzinfo=timezone.utc))
        buckets.setdefault(key, []).append(v)
    avg = [[k, round(sum(vs) / len(vs))] for k, vs in sorted(buckets.items())]
    mx = [[k, round(max(vs))] for k, vs in sorted(buckets.items())]
    return avg, mx


def monthly_yoy(daily_points: list[list]) -> dict:
    """Pivot a daily [ts_ms, value] series into {months:[1..12], by_year:{year:
    [12 monthly means]}} for a month-over-month year-on-year line chart."""
    buckets: dict[tuple, list[float]] = {}
    for ts, v in daily_points:
        if v is None:
            continue
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        buckets.setdefault((dt.year, dt.month), []).append(v)
    by_year_map: dict[str, dict[int, float]] = {}
    for (y, m), vals in buckets.items():
        by_year_map.setdefault(str(y), {})[m] = round(sum(vals) / len(vals))
    months = list(range(1, 13))
    by_year = {
        y: [by_year_map[y].get(m) for m in months]
        for y in sorted(by_year_map)
    }
    return {"months": months, "by_year": by_year}


def build_series(merged: dict) -> dict:
    thermal_h, nuclear_h = [], []
    ocgt_eskom_h, ocgt_ipp_h, ocgt_total_h = [], [], []
    wind_h, pv_h, csp_h, other_re_h = [], [], [], []
    gen_h, demand_h, hydro_h = [], [], []
    ils_h, mlr_h, ios_h, total_red_h = [], [], [], []  # demand-reduction tools
    pumped_h = []  # pumped-storage generation (discharge; negative = pumping)
    latest_ts = latest_gen = latest_demand = None

    for ts in sorted(merged):
        rec = merged[ts]
        t   = rec.get("Thermal_Generation", 0.0)
        n   = rec.get("Nuclear_Generation", 0.0)
        oe  = rec.get("Eskom_OCGT_Generation", 0.0)
        oi  = rec.get("Dispatchable_IPP_OCGT", 0.0)
        gas = rec.get("Eskom_Gas_Generation", 0.0)
        hyd = rec.get("Hydro_Water_Generation", 0.0)
        pmp = rec.get("Pumped_Water_Generation", 0.0)
        imp = rec.get("International_Imports", 0.0)
        ils = rec.get("ILS_Usage", 0.0)
        mlr = rec.get("Manual_Load_Reduction_MLR", 0.0)
        ios = rec.get("IOS_Excl_ILS_and_MLR", 0.0)

        thermal_h.append([ts, t])
        nuclear_h.append([ts, n])
        ocgt_eskom_h.append([ts, oe])
        ocgt_ipp_h.append([ts, oi])
        ocgt_total_h.append([ts, oe + oi])

        if "Wind"     in rec: wind_h.append([ts, rec["Wind"]])
        if "PV"       in rec: pv_h.append([ts, rec["PV"]])
        if "CSP"      in rec: csp_h.append([ts, rec["CSP"]])
        if "Other_RE" in rec: other_re_h.append([ts, rec["Other_RE"]])

        ils_h.append([ts, ils])
        mlr_h.append([ts, mlr])
        ios_h.append([ts, ios])
        total_red_h.append([ts, ils + mlr + ios])
        pumped_h.append([ts, pmp])
        hydro_h.append([ts, hyd])

        demand = rec.get("Residual_Demand") or (t + n + oe + oi + gas + hyd + pmp + imp + ils + mlr + ios)
        gen = t + n + oe + oi + gas + hyd + pmp + imp
        gen_h.append([ts, gen])
        demand_h.append([ts, demand])
        latest_ts = ts
        latest_gen = round(gen, 1)
        latest_demand = round(demand, 1)

    return {
        "latest_ts":      latest_ts,
        "latest_gen":     latest_gen,
        "latest_demand":  latest_demand,
        "thermal_min":    _agg(thermal_h, "min"),
        "thermal_avg":    _agg(thermal_h, "mean"),
        "thermal_max":    _agg(thermal_h, "max"),
        "nuclear_avg":    _agg(nuclear_h, "mean"),
        "ocgt_eskom_max": _agg(ocgt_eskom_h, "max"),
        "ocgt_ipp_max":   _agg(ocgt_ipp_h, "max"),
        "ocgt_total_avg": _agg(ocgt_total_h, "mean"),
        # Last 365 days of raw hourly values for the hourly-zoom chart.
        # Bigger than that materially bloats the dashboard JSON; if year-
        # scale browsing is needed long-term, split the hourly into its own
        # lazily-fetched JSON.
        "ocgt_eskom_hourly": ocgt_eskom_h[-365 * 24:],
        "ocgt_ipp_hourly":   ocgt_ipp_h[-365 * 24:],
        # Last 14 days of raw hourly pumped-storage generation for the Outlook
        # "recent use" chart (OCGT reuses the hourly arrays above).
        "pumped_hourly":     pumped_h[-14 * 24:],
        "gen_avg":        _agg(gen_h, "mean"),
        "gen_max":        _agg(gen_h, "max"),
        "demand_avg":     _agg(demand_h, "mean"),
        "demand_max":     _agg(demand_h, "max"),
        "wind_avg":       _agg(wind_h, "mean"),
        "pv_avg":         _agg(pv_h, "mean"),
        "csp_avg":        _agg(csp_h, "mean"),
        "other_re_avg":   _agg(other_re_h, "mean"),
        "ils_avg":             _agg(ils_h, "mean"),
        "mlr_avg":             _agg(mlr_h, "mean"),
        "ios_avg":             _agg(ios_h, "mean"),
        "total_reduction_avg": _agg(total_red_h, "mean"),
        "ils_max":             _agg(ils_h, "max"),
        "mlr_max":             _agg(mlr_h, "max"),
        "ios_max":             _agg(ios_h, "max"),
        "total_reduction_max": _agg(total_red_h, "max"),
        "pumped_avg":          _agg(pumped_h, "mean"),
        "hydro_avg":           _agg(hydro_h, "mean"),
        # Monthly OCGT total (Eskom + IPP): average + peak, full history.
        "ocgt_monthly_avg":    _monthly_avg_max(ocgt_total_h)[0],
        "ocgt_monthly_max":    _monthly_avg_max(ocgt_total_h)[1],
    }


def build_payload(data: dict) -> dict:
    eaf_label = ""
    if data.get("latest_eaf_ts"):
        eaf_label = "daily avg " + datetime.fromtimestamp(
            data["latest_eaf_ts"] / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    gen_monthly = monthly_yoy(data["gen_avg"])
    demand_monthly = monthly_yoy(data["demand_avg"])

    return {
        "latestTs":        data["latest_ts"],
        "thermalMin":      data["thermal_min"],
        "thermalAvg":      data["thermal_avg"],
        "thermalMax":      data["thermal_max"],
        "nuclearAvg":      data["nuclear_avg"],
        "ocgtEskomMax":    data["ocgt_eskom_max"],
        "ocgtIppMax":      data["ocgt_ipp_max"],
        "ocgtTotalAvg":    data["ocgt_total_avg"],
        "ocgtEskomHourly": data["ocgt_eskom_hourly"],
        "ocgtIppHourly":   data["ocgt_ipp_hourly"],
        "genAvg":          data["gen_avg"],
        "genMax":          data["gen_max"],
        "demandAvg":       data["demand_avg"],
        "demandMax":       data["demand_max"],
        "availableCapacityAvg": data["available_capacity_avg"],
        "headroomAvg":          data["headroom_avg"],
        "pclfAvg":         data["pclf_avg"],
        "uclfAvg":         data["uclf_avg"],
        "oclfAvg":         data["oclf_avg"],
        "clfPlanned":      data["clf_planned"],
        "clfUnplanned":    data["clf_unplanned"],
        "clfOther":        data["clf_other"],
        "clfTotal":        data["clf_total"],
        "iosAvg":             data["ios_avg"],
        "mlrAvg":             data["mlr_avg"],
        "ilsAvg":             data["ils_avg"],
        "totalReductionAvg":  data["total_reduction_avg"],
        "iosMax":             data["ios_max"],
        "mlrMax":             data["mlr_max"],
        "ilsMax":             data["ils_max"],
        "totalReductionMax":  data["total_reduction_max"],
        "pumpedAvg":          data["pumped_avg"],
        "hydroAvg":           data["hydro_avg"],
        "ocgtMonthlyAvg":     data["ocgt_monthly_avg"],
        "ocgtMonthlyMax":     data["ocgt_monthly_max"],
        "reInstalledMonthly": data["re_installed"],
        "importsAvg":      data["imports_avg"],
        "exportsAvg":      data["exports_avg"],
        "latestGen":       data["latest_gen"],
        "latestDemand":    data["latest_demand"],
        "latestEaf":       data["latest_eaf"],
        "latestEafLabel":  eaf_label,
        "windAvg":         data["wind_avg"],
        "pvAvg":           data["pv_avg"],
        "cspAvg":          data["csp_avg"],
        "otherReAvg":      data["other_re_avg"],
        "uclfOclfXKeys":   data["uclf_oclf_yoy"]["x_keys"],
        "uclfOclfByYear":  data["uclf_oclf_yoy"]["by_year"],
        "eafWeeks":        data["eaf_yoy"]["weeks"],
        "eafByYear":       data["eaf_yoy"]["by_year"],
        # Monthly generation + demand, year-over-year (avg MW per calendar month).
        "yoyMonths":       gen_monthly["months"],
        "genByYear":       gen_monthly["by_year"],
        "demandByYear":    demand_monthly["by_year"],
        # Weekly YoY series share the eafWeeks (1..52) x-axis.
        "capacityByYear":   data["capacity_yoy"]["by_year"],
        "peakDemandByYear": data["peak_demand_yoy"]["by_year"],
        "rooftopProvinces": data["rooftop_pv"]["provinces"],
        "rooftopSeries":   data["rooftop_pv"]["series"],
        "rooftopProvincesPerHh": data["rooftop_pv"]["provinces_per_hh"],
        "rooftopSeriesPerHh":    data["rooftop_pv"]["series_per_hh"],
        "chartSources":    CHART_SOURCES,
        "portalCatalog":   data["portal_catalog"],
        "recentPumpedHourly": data["pumped_hourly"],
        "stationHourly":   data["station_hourly"],
        "outageHourly":    data["outage_hourly"],
        "outlook":         data["outlook"],
        "weeklyReports":   data["weekly_reports"],
        "annualFinancials": data.get("annual_financials") or {},
        "loadshedding": data.get("loadshedding") or {},
    }


def main() -> None:
    print("Generating beta dashboard from DuckDB...")
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        validate_chart_sources(conn)
        generation = load_generation_mix(conn)
        outage     = load_outage_metrics(conn)
        outage_daily = load_outage_daily(conn)
        trade      = load_trade(conn)
        demand_capacity = load_demand_capacity(conn)
        uclf_oclf_yoy = load_uclf_oclf_by_year(conn)
        eaf_yoy       = load_yoy_weekly(conn, "staging.eaf_yoy_weekly", "eaf_pct")
        capacity_yoy    = load_yoy_weekly(conn, "staging.capacity_yoy_weekly", "capacity_mw")
        peak_demand_yoy = load_yoy_weekly(conn, "staging.peak_demand_yoy_weekly", "peak_demand_mw")
        rooftop_pv    = load_rooftop_pv(conn)
        portal_catalog = load_portal_catalog(conn)
        outlook_series = load_outlook_series(conn)
        status_outlook = load_status_outlook(conn)
        weekly_reports = load_weekly_reports(conn)
        re_installed = load_re_installed(conn)
        station_hourly = load_station_hourly(conn)
        outage_hourly = load_outage_hourly(conn)
        loadshedding = load_loadshedding(conn)

    annual_financials = load_annual_financials()

    # Merge generation + outage on timestamp (independent series — each loader
    # populates its own keys, no overlap).
    merged: dict[int, dict[str, float]] = {}
    for src in (generation, outage):
        for ts, rec in src.items():
            merged.setdefault(ts, {}).update(rec)

    data = build_series(merged)
    data["imports_avg"]      = trade["imports_avg"]
    data["exports_avg"]      = trade["exports_avg"]
    data["pclf_avg"]         = outage_daily["pclf_avg"]
    data["uclf_avg"]         = outage_daily["uclf_avg"]
    data["oclf_avg"]         = outage_daily["oclf_avg"]
    data["clf_planned"]      = outage_daily["clf_planned"]
    data["clf_unplanned"]    = outage_daily["clf_unplanned"]
    data["clf_other"]        = outage_daily["clf_other"]
    data["clf_total"]        = outage_daily["clf_total"]
    data["latest_eaf"]       = outage_daily["latest_eaf"]
    data["latest_eaf_ts"]    = outage_daily["latest_eaf_ts"]
    data["uclf_oclf_yoy"]    = uclf_oclf_yoy
    data["eaf_yoy"]          = eaf_yoy
    data["capacity_yoy"]     = capacity_yoy
    data["peak_demand_yoy"]  = peak_demand_yoy
    data["rooftop_pv"]       = rooftop_pv
    data["available_capacity_avg"] = demand_capacity["available_capacity_avg"]
    data["headroom_avg"]           = demand_capacity["headroom_avg"]
    data["portal_catalog"]         = portal_catalog

    def _last(series: list[list]) -> float | None:
        for _, v in reversed(series):
            if v is not None:
                return v
        return None

    outlook_metrics = compute_outlook(
        merged, data["latest_eaf"], _last(outage_daily["pclf_avg"]), _last(outage_daily["uclf_avg"]),
        demand_capacity["headroom_min_3d"])
    data["outlook"] = {**outlook_series, **outlook_metrics, "statusForecast": status_outlook}
    data["weekly_reports"] = weekly_reports
    data["re_installed"] = re_installed
    data["station_hourly"] = station_hourly
    data["outage_hourly"] = outage_hourly
    data["annual_financials"] = annual_financials
    data["loadshedding"] = loadshedding

    payload = build_payload(data)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")))

    size_kb = OUT_PATH.stat().st_size / 1024
    latest_iso = datetime.fromtimestamp(data["latest_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if data["latest_ts"] else "?"
    print(f"  wrote {OUT_PATH} ({size_kb:.0f} KB)")
    print(f"  latest: {latest_iso}  gen: {data['latest_gen']:,} MW  demand: {data['latest_demand']:,} MW")
    if data["latest_eaf"] is not None:
        eaf_when = datetime.fromtimestamp(data["latest_eaf_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"  EAF (hourly derived): {data['latest_eaf']}% @ {eaf_when}")


main()
