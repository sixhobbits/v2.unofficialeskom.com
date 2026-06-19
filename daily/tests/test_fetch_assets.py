"""Contract tests for the generic *_fetch.py bruin assets.

These pin the DataFrame shape + the hashing/error semantics that the refactor's
catalog-driven replacement must reproduce. The scraper library is patched so no
network is touched.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from conftest import load_asset

CSV_COLS = [
    "scraped_at", "slug", "section", "name", "page_url", "csv_url",
    "http_status", "content_hash", "etag", "last_modified",
    "content_length", "content_text", "error",
]
PBI_COLS = [
    "scraped_at", "slug", "section", "name", "page_url", "embed_url",
    "visual_id", "visual_title", "response_hash", "response_json",
    "metadata_json", "error",
]

GRAPHS = [
    {"slug": "s/good", "section": "Demand", "name": "Good", "page_url": "https://e/good/"},
    {"slug": "s/empty", "section": "Demand", "name": "Empty", "page_url": "https://e/empty/"},
    {"slug": "s/boom", "section": "Demand", "name": "Boom", "page_url": "https://e/boom/"},
]


def test_portal_csv_fetch_contract(monkeypatch):
    mod = load_asset("portal_csv_fetch.py")
    monkeypatch.setattr(mod, "PORTAL_GRAPHS", GRAPHS)

    def fake_scrape(page_url):
        if page_url.endswith("good/"):
            return {"csv_url": "https://x/f.csv", "http_status": 200,
                    "content_text": "a,b\n1,2\n", "error": None,
                    "etag": '"e"', "last_modified": "lm", "content_length": "8"}
        if page_url.endswith("empty/"):
            return {"csv_url": None, "http_status": 200, "content_text": None,
                    "error": "no CSV link on graph page",
                    "etag": None, "last_modified": None, "content_length": None}
        raise RuntimeError("network exploded")

    monkeypatch.setattr(mod, "scrape_csv", fake_scrape)
    df = mod.materialize()

    assert list(df.columns) == CSV_COLS
    assert len(df) == 3
    by = {r["slug"]: r for _, r in df.iterrows()}

    good = by["s/good"]
    assert good["content_hash"] == hashlib.sha256(b"a,b\n1,2\n").hexdigest()
    assert good["http_status"] == 200 and pd.isna(good["error"])

    empty = by["s/empty"]
    assert pd.isna(empty["content_hash"])         # no body -> no hash (NULL)
    assert empty["error"] == "no CSV link on graph page"

    boom = by["s/boom"]
    assert boom["http_status"] == 0               # exception sweeps to status 0
    assert "RuntimeError" in boom["error"]
    assert pd.isna(boom["content_hash"])


def test_portal_powerbi_fetch_contract(monkeypatch):
    mod = load_asset("portal_powerbi_fetch.py")
    monkeypatch.setattr(mod, "PORTAL_GRAPHS", GRAPHS)

    def fake_fetch(page_url):
        if page_url.endswith("good/"):
            return {"embed_url": "https://embed", "metadata_json": "{}", "error": None,
                    "visuals": [{"visual_id": "v1", "visual_title": "T",
                                 "response_json": '{"d":1}', "error": None}]}
        if page_url.endswith("empty/"):
            return {"embed_url": "https://embed", "metadata_json": None,
                    "error": None, "visuals": []}
        raise RuntimeError("pbi exploded")

    monkeypatch.setattr(mod, "fetch_responses", fake_fetch)
    df = mod.materialize()

    assert list(df.columns) == PBI_COLS
    by = {r["slug"]: r for _, r in df.iterrows()}

    good = by["s/good"]
    assert good["response_hash"] == hashlib.sha256(b'{"d":1}').hexdigest()
    assert good["visual_id"] == "v1"

    empty = by["s/empty"]
    assert pd.isna(empty["response_json"])
    assert empty["error"] == "no visuals returned"

    boom = by["s/boom"]
    assert "RuntimeError" in boom["error"]
    assert pd.isna(boom["response_hash"])
