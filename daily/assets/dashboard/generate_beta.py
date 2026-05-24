""" @bruin
name: dashboard.generate_beta
depends:
    - staging.supply_build_up
    - staging.international_trade_hourly
    - staging.outage_metrics_hourly
    - staging.outage_metrics_daily
    - staging.uclf_oclf_yoy_daily
    - staging.rooftop_pv_monthly

description: |
    Generates beta.unofficialeskom.com/index.html. Reads exclusively from
    staging.* tables — no raw.* or external SQLite. Chart→column lineage is
    declared in CHART_SOURCES and validated against duckdb's information_schema
    at build time so a renamed staging column fails the build instead of
    silently emptying a chart. The rendered HTML carries a "Data sources"
    panel derived from the same manifest.
@bruin """

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import duckdb

ROOT     = Path(__file__).resolve().parents[3]
DB_PATH  = ROOT / "warehouse" / "eskom.duckdb"
OUT_PATH = ROOT / "beta.unofficialeskom.com" / "static" / "dashboard-data.json"

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


def load_outage_daily(conn: duckdb.DuckDBPyConnection) -> dict:
    """Load merged daily outage metrics. Already daily-averaged in SQL."""
    rows = conn.execute(
        "SELECT day, eaf_pct, pclf_pct, uclf_pct, oclf_pct, "
        "pclf_src, uclf_src, oclf_src "
        "FROM staging.outage_metrics_daily ORDER BY day"
    ).fetchall()
    eaf, pclf, uclf, oclf = [], [], [], []
    latest_eaf = latest_eaf_ts = None
    src_counts: dict[str, int] = {}
    for day, e, p, u, o, ps, us, os_ in rows:
        dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        ts = _ts_ms(dt)
        eaf.append([ts, round(e, 1)])
        pclf.append([ts, round(p, 1) if p is not None else None])
        uclf.append([ts, round(u, 1) if u is not None else None])
        oclf.append([ts, round(o, 1) if o is not None else None])
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
    print(f"  staging.demand_capacity_hourly: {len(cap_h)} capacity / {len(dem_h)} demand / {len(hr_h)} headroom hours")
    return {
        "available_capacity_avg": _agg(cap_h, "mean"),
        "demand_capacity_residual_demand_avg": _agg(dem_h, "mean"),
        "headroom_avg": _agg(hr_h, "mean"),
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


def build_series(merged: dict) -> dict:
    thermal_h, nuclear_h = [], []
    ocgt_eskom_h, ocgt_ipp_h, ocgt_total_h = [], [], []
    wind_h, pv_h, csp_h, other_re_h = [], [], [], []
    gen_h, demand_h = [], []
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
        "gen_avg":        _agg(gen_h, "mean"),
        "gen_max":        _agg(gen_h, "max"),
        "demand_avg":     _agg(demand_h, "mean"),
        "demand_max":     _agg(demand_h, "max"),
        "wind_avg":       _agg(wind_h, "mean"),
        "pv_avg":         _agg(pv_h, "mean"),
        "csp_avg":        _agg(csp_h, "mean"),
        "other_re_avg":   _agg(other_re_h, "mean"),
    }


def build_payload(data: dict) -> dict:
    eaf_label = ""
    if data.get("latest_eaf_ts"):
        eaf_label = "daily avg " + datetime.fromtimestamp(
            data["latest_eaf_ts"] / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d")

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
        "eafAvg":          data["eaf_avg"],
        "pclfAvg":         data["pclf_avg"],
        "uclfAvg":         data["uclf_avg"],
        "oclfAvg":         data["oclf_avg"],
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
        "rooftopProvinces": data["rooftop_pv"]["provinces"],
        "rooftopSeries":   data["rooftop_pv"]["series"],
        "rooftopProvincesPerHh": data["rooftop_pv"]["provinces_per_hh"],
        "rooftopSeriesPerHh":    data["rooftop_pv"]["series_per_hh"],
        "chartSources":    CHART_SOURCES,
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
        rooftop_pv    = load_rooftop_pv(conn)

    # Merge generation + outage on timestamp (independent series — each loader
    # populates its own keys, no overlap).
    merged: dict[int, dict[str, float]] = {}
    for src in (generation, outage):
        for ts, rec in src.items():
            merged.setdefault(ts, {}).update(rec)

    data = build_series(merged)
    data["imports_avg"]      = trade["imports_avg"]
    data["exports_avg"]      = trade["exports_avg"]
    data["eaf_avg"]          = outage_daily["eaf_avg"]
    data["pclf_avg"]         = outage_daily["pclf_avg"]
    data["uclf_avg"]         = outage_daily["uclf_avg"]
    data["oclf_avg"]         = outage_daily["oclf_avg"]
    data["latest_eaf"]       = outage_daily["latest_eaf"]
    data["latest_eaf_ts"]    = outage_daily["latest_eaf_ts"]
    data["uclf_oclf_yoy"]    = uclf_oclf_yoy
    data["rooftop_pv"]       = rooftop_pv
    data["available_capacity_avg"] = demand_capacity["available_capacity_avg"]
    data["headroom_avg"]           = demand_capacity["headroom_avg"]

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
