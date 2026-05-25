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
