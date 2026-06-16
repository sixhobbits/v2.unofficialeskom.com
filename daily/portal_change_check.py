#!/usr/bin/env python3
"""Cheap change-detector for the Eskom Data Portal.

The portal is a WordPress site that republishes its CSV exports as static files
under wp-content/uploads. Every file is served with ETag / Last-Modified /
Content-Length, and Eskom rewrites the whole batch once a day (observed ~04:09
UTC). So instead of running the full scraper (which fetches + decodes every
PowerBI report and parses every CSV — minutes of work) just to discover nothing
changed, we issue one cheap HEAD per known CSV URL and compare the validators to
what we saw last time.

  - any file's (ETag, Last-Modified, Content-Length) changed  -> CHANGED
  - a known URL now 404s (Eskom's monthly /uploads/YYYY/MM/ path rolled over,
    or a file was renamed)                                     -> CHANGED
                                                                  (forces the
    full scraper to re-discover links)
  - first ever run                                             -> records a
    baseline, reports no change

A republished file isn't a guarantee of new *data rows* (Eskom re-emits the same
file daily even when the actuals lag), but it's the right signal to "go scrape
and let the pipeline decide". CSVs are checked as a proxy for the whole portal:
the entire batch (incl. the PowerBI-backed datasets) refreshes together, so a CSV
change means it's worth running everything.

Usage:
    # exit 10 if anything changed, 0 if not, 1 on error
    .venv/bin/python portal_change_check.py

    # on change, run the full pipeline itself
    .venv/bin/python portal_change_check.py --run

State lives in .portal_change_state.json next to this script. URLs come from the
last scrape's discovered links (raw.portal_csv_fetch); if the warehouse is
locked (a scrape is mid-run) we fall back to the URLs cached in the state file.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / ".portal_change_state.json"
WAREHOUSE = HERE.parent / "warehouse" / "eskom.duckdb"
USER_AGENT = "Mozilla/5.0 eskom-change-check (+https://www.eskom.co.za/dataportal/)"
CHANGED_EXIT = 10

# The documented full refresh (see repo-root CLAUDE.md "Updating the beta dashboard").
BRUIN_RUN = [
    "bruin", "run", "--workers", "1",
    "--config-file", str(HERE.parent.parent / ".bruin.yml"), ".",
]


def discovered_urls() -> list[str] | None:
    """Current CSV URLs from the last scrape. None if the warehouse is locked."""
    try:
        import duckdb
    except ImportError:
        return None
    try:
        con = duckdb.connect(str(WAREHOUSE), read_only=True)
    except Exception:
        return None  # a scrape is probably holding the write lock — use the cache
    try:
        rows = con.execute(
            "SELECT DISTINCT csv_url FROM raw.portal_csv_fetch WHERE csv_url IS NOT NULL"
        ).fetchall()
        return sorted(r[0] for r in rows)
    finally:
        con.close()


def head(url: str) -> tuple[str, int, tuple]:
    """HEAD a URL -> (url, status, (etag, last_modified, content_length))."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            h = r.headers
            return url, r.status, (h.get("ETag"), h.get("Last-Modified"), h.get("Content-Length"))
    except urllib.error.HTTPError as e:
        return url, e.code, (None, None, None)
    except Exception:
        return url, 0, (None, None, None)  # transient/network — treat as "unknown", no trigger


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect Eskom Data Portal changes cheaply.")
    ap.add_argument("--run", action="store_true",
                    help="run the full bruin pipeline when a change is detected")
    ap.add_argument("--quiet", action="store_true", help="only print on change / error")
    args = ap.parse_args()

    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            state = {}
    validators: dict[str, list] = state.get("validators", {})

    urls = discovered_urls() or state.get("urls")
    if not urls:
        print("portal-check: no URLs to check (empty warehouse and no cached state)", file=sys.stderr)
        return 1

    first_run = not validators
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(head, urls))

    changed: list[str] = []
    new_validators: dict[str, list] = {}
    for url, status, cur in results:
        if status == 200:
            new_validators[url] = list(cur)
            prev = validators.get(url)
            if prev is not None and list(cur) != prev:
                changed.append(url)
        elif status == 404:
            # Known URL vanished (month rollover / rename) — force a re-discover.
            if url in validators:
                changed.append(url + "  (now 404)")
            # don't carry the dead URL's validator forward
        else:
            # network blip or unknown status: keep the previous validator, no trigger
            if url in validators:
                new_validators[url] = validators[url]

    STATE_FILE.write_text(json.dumps({"urls": urls, "validators": new_validators}, indent=2))

    if first_run:
        if not args.quiet:
            print(f"portal-check: baseline recorded for {len(new_validators)} files — no trigger")
        return 0

    if changed:
        print(f"portal-check: CHANGED ({len(changed)} file(s)):")
        for c in changed:
            print(f"  - {c}")
        if args.run:
            print("portal-check: running full pipeline…")
            return subprocess.run(BRUIN_RUN, cwd=HERE).returncode
        return CHANGED_EXIT

    if not args.quiet:
        print(f"portal-check: no change across {len(new_validators)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
