"""Regression guard for the supply-build-up CSV migration.

The per-dataset raw.supply_build_up_csv chain was deleted; staging now reads the
station-build-up CSV from the generic raw.portal_csv (filtered by slug). The
generic parser (parse_csv_text) was proven byte-identical to the old per-dataset
parser on real warehouse data. This test locks that the generic parser keeps
yielding the supply series the dashboard's staging.supply_build_up depends on,
using a real captured CSV fixture.
"""
from __future__ import annotations

import pathlib
import re

from eskom_portal.csv_scrape import parse_csv_text

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "station_build_up_sample.csv"

# series_keys that staging.supply_build_up reads (after its lower/regex normalise)
EXPECTED_KEYS = {
    "thermal_gen_excl_pumping_and_sco",
    "nuclear_generation",
    "eskom_ocgt_generation",
    "eskom_gas_generation",
    "dispatchable_ipp_ocgt",
    "hydro_water_generation",
    "international_imports",
}


def _key(series: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", series.lower()).strip("_")


def test_generic_parser_yields_dashboard_series():
    rows = parse_csv_text(FIXTURE.read_text())
    assert rows, "parser returned no rows for the station-build-up CSV"
    assert all(r["timestamp"] is not None for r in rows), "timestamps must parse"

    keys = {_key(r["series"]) for r in rows}
    missing = EXPECTED_KEYS - keys
    assert not missing, f"generic parser dropped dashboard series: {missing}"
