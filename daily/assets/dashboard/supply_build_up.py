""" @bruin
name: dashboard.supply_build_up
depends:
    - staging.supply_build_up

description: |
    Builds dashboard/supply_build_up.html — a single self-contained file
    rendering the staging table as a React + AG Studio dashboard with
    stacked-area, line chart, and grid widgets.

    Side-effect asset: no warehouse table. The pipeline is:

        staging.supply_build_up   (DuckDB SELECT)
              ↓
        dashboard-src/src/dashboard-data.json   (this script writes)
              ↓
        vite build                              (this script invokes)
              ↓
        dashboard/supply_build_up.html          (single self-contained HTML)

    Requires Node.js + npm installed; dashboard-src/node_modules must be
    populated (run `npm install` in dashboard-src/ once).
@bruin """

import json
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT.parent / "warehouse" / "eskom.duckdb"
DASHBOARD_SRC = ROOT / "dashboard-src"
DATA_JSON = DASHBOARD_SRC / "src" / "dashboard-data.json"
OUT_DIR = ROOT / "dashboard"
OUT_NAME = "supply_build_up.html"


def main() -> None:
    # 1. Pull staging into a list of dicts
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.sql(
            "SELECT * FROM staging.supply_build_up ORDER BY timestamp"
        ).df()

    # Make timestamp an ISO 8601 string (AG Studio parses these as dates).
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    rows = df.to_dict(orient="records")
    print(f"  staging.supply_build_up: {len(rows)} rows")

    # Declared field types — without these, AG Studio infers timestamp as a
    # text category and renders every hour as a rotated label.
    numeric_cols = [c for c in df.columns if c not in ("timestamp", "source")]
    fields = (
        [{"id": "timestamp", "format": "dateTimeFormat"}] +
        [{"id": c, "format": "decimalFormat"} for c in numeric_cols] +
        [{"id": "source", "format": "textFormat"}]
    )

    # 2. Build the AG Studio data + state payload
    payload = {
        "data": {"sources": [{"id": "supply", "data": rows, "fields": fields}]},
        "state": {
            "selectedPageId": "page-1",
            "pages": [{
                "id": "page-1",
                "widgets": {
                    "w-stack": {
                        "type": "area-chart-stacked",
                        "format": {"title": {"text": "Generation mix (MW)", "enabled": True}},
                        "dataMapping": {
                            "categoryKey": [{"id": "supply.timestamp"}],
                            "valueKey": [
                                {"id": "supply.thermal_gen_excl_pumping_and_sco", "aggregation": "sum"},
                                {"id": "supply.nuclear_generation",               "aggregation": "sum"},
                                {"id": "supply.hydro_water_generation",           "aggregation": "sum"},
                                {"id": "supply.pumped_water_generation",          "aggregation": "sum"},
                                {"id": "supply.eskom_ocgt_generation",            "aggregation": "sum"},
                                {"id": "supply.dispatchable_ipp_ocgt",            "aggregation": "sum"},
                                {"id": "supply.wind",                             "aggregation": "sum"},
                                {"id": "supply.pv",                               "aggregation": "sum"},
                                {"id": "supply.csp",                              "aggregation": "sum"},
                                {"id": "supply.other_re",                         "aggregation": "sum"},
                                {"id": "supply.international_imports",            "aggregation": "sum"},
                            ],
                        },
                    },
                    "w-renew": {
                        "type": "line-chart",
                        "format": {"title": {"text": "Renewables (MW)", "enabled": True}},
                        "dataMapping": {
                            "categoryKey": [{"id": "supply.timestamp"}],
                            "valueKey": [
                                {"id": "supply.wind", "aggregation": "sum"},
                                {"id": "supply.pv",   "aggregation": "sum"},
                                {"id": "supply.csp",  "aggregation": "sum"},
                            ],
                        },
                    },
                    "w-grid": {
                        "type": "grid",
                        "format": {"title": {"text": "Hourly detail", "enabled": True}},
                        "dataMapping": {
                            "cols": [
                                {"id": "supply.timestamp"},
                                {"id": "supply.thermal_gen_excl_pumping_and_sco", "aggregation": "sum"},
                                {"id": "supply.nuclear_generation",               "aggregation": "sum"},
                                {"id": "supply.wind",                             "aggregation": "sum"},
                                {"id": "supply.pv",                               "aggregation": "sum"},
                                {"id": "supply.international_imports",            "aggregation": "sum"},
                                {"id": "supply.source"},
                            ],
                        },
                    },
                },
                "widgetLayout": {
                    "w-stack": {"xTrack": 0,  "yTrack": 0,  "xSpan": 24, "ySpan": 6},
                    "w-renew": {"xTrack": 0,  "yTrack": 6,  "xSpan": 12, "ySpan": 5},
                    "w-grid":  {"xTrack": 12, "yTrack": 6,  "xSpan": 12, "ySpan": 5},
                },
                "layout": {
                    "columns": 24,
                    "rowHeight": 80,
                    "widgetPadding": 12,
                    "pagePadding": 16,
                    "widgetBorderEnabled": True,
                    "widgetBorderRadius": 8,
                },
            }],
        },
    }

    # 3. Write JSON into the Vite project
    DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    DATA_JSON.write_text(json.dumps(payload, default=str))
    print(f"  wrote {DATA_JSON.relative_to(ROOT)} ({DATA_JSON.stat().st_size / 1024:.1f} KB)")

    # 4. Run the Vite build
    if not (DASHBOARD_SRC / "node_modules").exists():
        print("  ✗ dashboard-src/node_modules missing — run `npm install` first")
        sys.exit(1)

    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=DASHBOARD_SRC,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("  ✗ vite build failed:")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)

    # 5. Rename index.html → supply_build_up.html
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    built = OUT_DIR / "index.html"
    final = OUT_DIR / OUT_NAME
    if built.exists():
        shutil.move(str(built), str(final))
    size_kb = final.stat().st_size / 1024
    print(f"  ✓ wrote {final.relative_to(ROOT)} ({size_kb:.1f} KB)")


main()
