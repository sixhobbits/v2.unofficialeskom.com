# Eskom scraper pipeline — refactor notes

## Current state — how the scrapers run

Everything lives in `unofficialeskom_v2/daily/`, a bruin pipeline (`pipeline.yml`).
You run it with `bruin run --workers 1 --config-file ../../.bruin.yml .` (full /
daily) or `--tag hourly` (CSV + dashboard only). Each "asset" is a `.py` whose
`materialize()` returns a DataFrame, or a `.sql`. The actual HTTP/parse logic is
**not** in bruin assets — it's a hand-rolled Python library in `eskom_portal/`
(`catalog.py`, `csv_scrape.py`, `powerbi_scrape.py`, `fetch.py`,
`weekly_status_report.py`) that the assets import and call.

```
daily/
├─ pipeline.yml              # schedule, vars (2 page URLs), duckdb connection
├─ eskom_portal/             # hand-written scraper LIBRARY (not bruin)
│   ├─ catalog.py            # the 24 portal graphs (page URLs only)
│   ├─ csv_scrape.py         # discover + download a page's CSV
│   ├─ powerbi_scrape.py     # decode iframe + querydata API
│   └─ fetch.py              # HTTP + validators
├─ assets/
│   ├─ raw/                  # fetch + store assets (the mess — see below)
│   ├─ staging/              # *.sql transforms (this part is clean, real bruin)
│   └─ dashboard/            # generate_beta.py builds dashboard-data.json
└─ portal_change_check.py    # standalone HEAD-poll gate (not a bruin asset)
```

### Files/folders touched on a run
- `eskom_portal/*`, `assets/raw/*`, `assets/staging/*`, `assets/dashboard/generate_beta.py`
- the DuckDB warehouse (`../warehouse/…`), then `beta.unofficialeskom.com/static/dashboard-data.json`

### Dead / untouched — candidates for removal
- `dashboard-src/` — a leftover Vite/TS app; the live site is the Docusaurus app in `beta.unofficialeskom.com/`. **Remove.**
- `assets/dashboard/supply_build_up.py` + `dashboard/supply_build_up.html` — orphan one-off; not in the dashboard JSON path. **Remove.**
- Per-graph `raw/` chains (`supply_build_up_*`, `demand_capacity_*`, `uclf_oclf_trend_*`, `weekly_capacity_breakdown_*`) — near-identical copies of the generic `portal_csv*` / `portal_powerbi*` (which already loop over all 24 graphs). They survive only because the staging SQL points at their table names. **Collapse, don't keep.**

## How "bruin" is this, really?

Honest answer: the transform half (`assets/staging/*.sql`, materialization,
`depends`, freshness checks) is genuine native bruin and is fine. The ingestion
half is **not** — it's a custom Python scraping framework wearing a bruin asset
as a hat. Bruin's job (fetch a source, dedupe, store, log validators) is
reimplemented by hand in `eskom_portal/` + copy-pasted `*_fetch.py` /
`*_content.sql` / `*_scrapes.sql` triplets, one set per dataset.

The duplication is the tell: every `*_csv_fetch.py` is the same 60–70 lines
calling `scrape_csv(page_url)` with a different URL, and the generic
`portal_csv_fetch.py` already does all of them from `catalog.py`. So a graph is
"defined" in 4–6 files instead of one, the `depends:` edges between fetchers
exist only to serialise DuckDB's single writer (not real lineage), and
`portal_change_check.py` is a second, parallel scraper outside bruin entirely.
Web scraping genuinely isn't something bruin ingests natively (no connector for
"WordPress page → find CSV link → PowerBI querydata"), so *some* Python is
unavoidable — but it should be one thin Python asset per concern, not a bespoke
framework with per-graph clones.

## Desired state — clean native bruin

Keep one scraper library, drive everything off `catalog.py`, and have **exactly
one CSV asset and one PowerBI asset per graph** generated from the catalog — no
hand-copied per-dataset fetchers. Each asset is a thin `materialize()` that calls
the library and returns rows; bruin owns dedupe (merge strategy on `content_hash`),
the change-log (append strategy), freshness checks, and lineage. Delete
`portal_change_check.py`'s separate path — the hourly run already records the same
validators. Move staging SQL to depend on the catalog-driven raw tables, not on
per-graph table names.

```
daily/
├─ pipeline.yml              # schedule, connections, vars, default quality checks
├─ eskom_portal/             # the ONLY hand-written code: pure scrape functions
│   ├─ catalog.py            # single source of truth: every graph + its kind (csv/powerbi/pdf)
│   ├─ csv_scrape.py · powerbi_scrape.py · weekly_status_report.py · fetch.py
├─ assets/
│   ├─ raw/
│   │   ├─ portal_csv.py          # one asset: loops catalog → all CSV graphs
│   │   ├─ portal_powerbi.py      # one asset: loops catalog → all PowerBI graphs
│   │   ├─ portal_csv_log.sql     # append-only validator/hash log (bruin append)
│   │   └─ weekly_status_pdf.py   # the genuinely-special PDF feed
│   ├─ staging/              # *.sql only, depend on the 2 raw tables by slug
│   └─ dashboard/generate_beta.py
└─ (no dashboard-src/, no per-graph clones, no portal_change_check.py)
```

- Per-graph behaviour (a different parse) belongs in `catalog.py` metadata, not a new file.
- Bruin natives to lean on: `materialization.strategy: merge` for dedupe, `append` for logs, column `checks` (`not_null`/`unique`) and `freshness` instead of custom SQL, `depends` for real lineage only.
- Net: a new graph = one row in `catalog.py`; ~6 files per dataset collapses to 2 shared assets + the library.
