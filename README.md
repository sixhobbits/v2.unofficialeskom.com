# v2.unofficialeskom.com

Bruin data pipelines + Docusaurus dashboard for https://beta.unofficialeskom.com.

## Layout

- `daily/` — bruin pipeline that scrapes the Eskom Data Portal and populates `warehouse/eskom.duckdb`. Produces `beta.unofficialeskom.com/static/dashboard-data.json`.
- `weekly/` — separate bruin pipeline for the weekly media-room PDFs.
- `beta.unofficialeskom.com/` — Docusaurus site that reads the generated JSON at build time.
- `warehouse/` — generated DuckDB files (gitignored).

## One-time setup

```bash
cp .bruin.example.yml .bruin.yml
cd beta.unofficialeskom.com && yarn install
```

`.bruin.yml` is gitignored because it may need per-machine tweaking, but the example ships with sensible defaults that work out of the box if you run from this directory.

A few `raw.*` assets read from local v1 sqlite files expected at `../sources/eskom.sqlite` and `../sources/eskom_metrics.sqlite` (relative to this directory). Without those files the corresponding assets will fail; the rest of the pipeline still runs.

## Run

```bash
cd daily && bruin run --workers 1 .
cd ../beta.unofficialeskom.com && yarn build
```

`--workers 1` is required (DuckDB is single-writer).

## Stale CSV links and outage coverage

`eskom_portal.csv_scrape.scrape_csv` compares parsed data timestamps with the
current date. If the linked CSV is more than seven days behind (or has no
usable dated rows), it checks the same filename in the current and previous
month's WordPress uploads directories, newer than the linked directory. It
accepts only a valid CSV with the expected series and a later data timestamp;
the chosen URL, body and HTTP validators stay together in the scrape record.
Failed, HTML, unrelated or older candidates never replace usable linked data.
This bounded recovery handles portal pages that keep linking last month's file;
it can be removed when Eskom reliably updates those links.

`staging.uclf_oclf_trend_hourly` selects CSV values per hour and fills missing
hours from the existing daily PowerBI scrape. Daily outage metrics, the hourly
outage chart tail and year-on-year outages all consume that shared series.
Bulk data still takes precedence for the full outage breakdown; recent PCLF
and OCLF still come from weekly reports because the trend reports only their
combined unplanned/other loss total. Hourly runs reuse the latest stored PowerBI
scrape; the normal full daily run refreshes PowerBI.
