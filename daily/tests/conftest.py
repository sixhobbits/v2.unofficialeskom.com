"""Shared test helpers.

These tests pin the *current* behaviour of the fetch/content/scrapes assets so
the bruin-refactor (collapsing per-graph triplets into catalog-driven assets)
can be proven to preserve the contract. Nothing here hits the network — the
library's HTTP layer is monkeypatched.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
import types

DAILY = pathlib.Path(__file__).resolve().parent.parent
RAW = DAILY / "assets" / "raw"

# eskom_portal lives under daily/ — make it importable.
if str(DAILY) not in sys.path:
    sys.path.insert(0, str(DAILY))


def load_asset(rel_to_raw: str) -> types.ModuleType:
    """Import a loose bruin Python asset (e.g. 'portal_csv_fetch.py') as a module.

    The @bruin header is a module docstring, so the file imports cleanly; we just
    need a unique module name and daily/ on the path (handled above)."""
    path = RAW / rel_to_raw
    name = "asset_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_BRUIN_BLOCK = re.compile(r"/\*\s*@bruin.*?@bruin\s*\*/", re.DOTALL)


def sql_body(rel_to_raw: str) -> str:
    """Return a SQL asset's query with the /* @bruin ... @bruin */ header stripped."""
    text = (RAW / rel_to_raw).read_text()
    return _BRUIN_BLOCK.sub("", text).strip()
