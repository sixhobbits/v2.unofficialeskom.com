#!/usr/bin/env python3
"""Generate static/dashboard-ag.html — an AG Charts version of the ECharts dashboard.

Reads the embedded `const DATA = {...};` line from static/dashboard.html and
emits a self-contained HTML page that renders the same series with AG Charts
Enterprise 13.3.0 (loaded from jsDelivr). The trial license key lives in
../.aglicense at the repo root.

Run after dashboard.html has been refreshed by the bruin pipeline:

    python3 scripts/generate_dashboard_ag.py
"""

from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ECHARTS_HTML = ROOT / "static" / "dashboard.html"
OUT_HTML     = ROOT / "static" / "dashboard-ag.html"
LICENSE_FILE = ROOT.parent / ".aglicense"


def extract_data_literal(html_path: Path) -> str:
    """Return the literal `const DATA = {...};` line from the ECharts dashboard."""
    with html_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.lstrip()
            if stripped.startswith("const DATA = "):
                return stripped.rstrip("\n")
    raise RuntimeError(f"DATA constant not found in {html_path}")


def main() -> None:
    data_line = extract_data_literal(ECHARTS_HTML)
    license_key = LICENSE_FILE.read_text(encoding="utf-8").strip().splitlines()[0]

    page = TEMPLATE.replace("__DATA_LINE__", data_line).replace("__LICENSE__", license_key)
    OUT_HTML.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size:,} bytes)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Eskom Beta Dashboard (AG Charts)</title>
  <script src="https://cdn.jsdelivr.net/npm/ag-charts-enterprise@13.3.0/dist/umd/ag-charts-enterprise.min.js"></script>
  <style>
    :root {
      --body-grad: linear-gradient(135deg, #f5f6fa 0%, #e8eaf0 100%);
      --text: #1a1a2e; --muted: #666; --dim: #999;
      --card-bg: #ffffff; --card-border: transparent;
      --card-shadow: 0 2px 8px rgba(0,0,0,0.08);
      --chart-title: #333;
      --provenance-bg: #ffffff; --provenance-text: #444;
      --provenance-strong: #1a1a2e; --provenance-border: #eeeeee;
      --gauge-label: #888; --gauge-value: #1a1a2e; --gauge-units: #666; --gauge-sub: #999;
    }
    :root[data-theme="dark"] {
      --body-grad: linear-gradient(135deg, #0e0e1a 0%, #1a1a2e 100%);
      --text: #e6e6ed; --muted: #9aa0b4; --dim: #7a7f93;
      --card-bg: #1e1e2e; --card-border: #2a2a3a;
      --card-shadow: 0 2px 12px rgba(0,0,0,0.35);
      --chart-title: #dadbe6;
      --provenance-bg: #1e1e2e; --provenance-text: #b8bcd0;
      --provenance-strong: #f4f4fa; --provenance-border: #2a2a3a;
      --gauge-label: #8a8fa6; --gauge-value: #f4f4fa; --gauge-units: #9aa0b4; --gauge-sub: #7a7f93;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--body-grad);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text); padding: 24px; min-height: 100vh;
    }
    .container { max-width: none; margin: 0; }
    header { margin-bottom: 24px; display:flex; justify-content:space-between; align-items:flex-end; gap:16px; }
    header h1 { font-size: 2rem; font-weight: 700; letter-spacing: -1px; margin-bottom: 4px; }
    header p { font-size: 0.9rem; color: var(--muted); }
    .top-row { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 20px; margin-bottom: 24px; }
    .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; box-shadow: var(--card-shadow); padding: 20px 24px; }
    .card.headline { background: linear-gradient(135deg, #1a1a2e 0%, #2d3748 100%); border-color: #2d3748; color: #fff; }
    .gauge-card { display: flex; flex-direction: column; justify-content: space-between; gap: 8px; }
    .gauge-meta { display: flex; flex-direction: column; gap: 6px; }
    .gauge-label { font-size: 0.8rem; color: var(--gauge-label); text-transform: uppercase; letter-spacing: 0.6px; }
    .card.headline .gauge-label { color: #b8bcd0; }
    .card.headline .gauge-value { color: #fff; }
    .card.headline .gauge-units { color: #b8bcd0; }
    .gauge-value { font-size: 2.6rem; font-weight: 700; letter-spacing: -1px; line-height: 1; color: var(--gauge-value); }
    .gauge-value.big { font-size: 3.4rem; }
    .gauge-units { font-size: 0.95rem; color: var(--gauge-units); font-weight: 500; }
    .gauge-sub { font-size: 0.75rem; color: var(--gauge-sub); margin-top: 4px; }
    .gauge { width: 100%; height: 220px; display: block; }
    .chart-row { display: grid; grid-template-columns: 1fr; gap: 20px; }
    .chart-card { padding: 16px 18px 8px; }
    .chart-card h3 { font-size: 0.95rem; font-weight: 600; color: var(--chart-title); margin-bottom: 8px; }
    .chart { width: 100%; height: 420px; }
    .theme-toggle { background: var(--card-bg); color: var(--text); border: 1px solid var(--card-border); border-radius: 8px; padding: 6px 12px; font-size: 0.85rem; cursor: pointer; box-shadow: var(--card-shadow); }
    @media (max-width: 900px) { .top-row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Eskom Beta Dashboard <span style="font-size:0.55em;color:var(--muted);font-weight:500">— AG Charts</span></h1>
        <p>Same data series as the ECharts dashboard, rendered with AG Charts Enterprise 13.</p>
      </div>
      <button class="theme-toggle" id="theme-toggle">Toggle theme</button>
    </header>

    <div class="top-row">
      <div class="card headline gauge-card">
        <div class="gauge-meta">
          <div class="gauge-label">Latest generation</div>
          <div><span class="gauge-value big" id="val-generation">—</span> <span class="gauge-units">MW</span></div>
          <div class="gauge-sub" id="lbl-generation"></div>
        </div>
      </div>
      <div class="card gauge-card">
        <div class="gauge-meta">
          <div class="gauge-label">Latest residual demand</div>
          <div><span class="gauge-value" id="val-demand">—</span> <span class="gauge-units">MW</span></div>
          <div class="gauge-sub" id="lbl-demand"></div>
        </div>
      </div>
      <div class="card gauge-card">
        <div class="gauge-meta">
          <div class="gauge-label">Energy availability factor</div>
        </div>
        <div id="gauge-eaf" class="gauge"></div>
        <div class="gauge-sub" id="lbl-eaf"></div>
      </div>
    </div>

    <div class="chart-row">
      <div class="card chart-card"><h3>Daily outage breakdown (EAF / PCLF / UCLF / OCLF, %)</h3><div id="chart-outage-stack" class="chart"></div></div>
      <div class="card chart-card"><h3>Renewables generation (MW)</h3><div id="chart-renewables" class="chart"></div></div>
      <div class="card chart-card"><h3>Thermal generation — min / avg / max (MW)</h3><div id="chart-thermal" class="chart"></div></div>
      <div class="card chart-card"><h3>Nuclear generation (MW)</h3><div id="chart-nuclear" class="chart"></div></div>
      <div class="card chart-card"><h3>OCGT peak generation (MW)</h3><div id="chart-ocgt" class="chart"></div></div>
      <div class="card chart-card"><h3>UCLF + OCLF, year-on-year (%)</h3><div id="chart-uclf-oclf-yoy" class="chart"></div></div>
      <div class="card chart-card"><h3>Rooftop PV installed by province (MW)</h3><div id="chart-rooftop-pv" class="chart"></div></div>
      <div class="card chart-card"><h3>Rooftop PV per household by province (W/household)</h3><div id="chart-rooftop-pv-per-household" class="chart"></div></div>
      <div class="card chart-card"><h3>International trade (MW)</h3><div id="chart-trade" class="chart"></div></div>
    </div>
  </div>

  <script>
    agCharts.LicenseManager.setLicenseKey("__LICENSE__");
    __DATA_LINE__

    // ---- helpers -----------------------------------------------------------
    const fmt = (n) => Math.round(n).toLocaleString('en-ZA');
    const charts = [];

    // Convert [[ts, val], ...] -> [{x: Date, y: val}, ...]
    const pairsToXY = (pairs) => (pairs || []).map(([t, v]) => ({ x: new Date(t), y: v }));

    // Merge several [[ts, val], ...] series into a single array of rows keyed by date.
    // Returns { data: [{date: Date, name1: v, name2: v, ...}], keys: [...] }
    function mergeByTimestamp(seriesMap) {
      const idx = new Map();
      for (const [name, pairs] of Object.entries(seriesMap)) {
        for (const [t, v] of (pairs || [])) {
          let row = idx.get(t);
          if (!row) { row = { date: new Date(t) }; idx.set(t, row); }
          row[name] = v;
        }
      }
      return [...idx.entries()].sort((a, b) => a[0] - b[0]).map(([, r]) => r);
    }

    const EIGHT_WEEKS_MS = 56 * 24 * 60 * 60 * 1000;

    // Latest timestamp across an array of merged rows ({date, ...}).
    function lastDateIn(rows) {
      let last = null;
      for (const r of rows) {
        if (r.date && (last == null || r.date > last)) last = r.date;
      }
      return last;
    }

    // Time x-axis capped to the last data point (no future-padding) + numeric y-axis.
    function axes(unit = '', decimals = 0, yMax, data) {
      const y = {
        type: 'number',
        position: 'left',
        label: { formatter: ({ value }) => value.toLocaleString('en-ZA') + unit },
      };
      if (yMax != null) y.max = yMax;
      const x = { type: 'time', position: 'bottom', nice: false };
      const last = data ? lastDateIn(data) : null;
      if (last) x.max = last;
      return [x, y];
    }

    // Default the visible zoom to the last 8 weeks. Navigator can scroll back.
    function initialZoomFor(data) {
      const last = lastDateIn(data);
      if (!last) return undefined;
      const start = last.getTime() - EIGHT_WEEKS_MS;
      return {
        zoom: {
          rangeX: {
            start: { __type: 'date', value: start },
            end:   { __type: 'date', value: last.getTime() },
          },
        },
      };
    }

    // Series helpers — colours come from the active AG Charts theme palette.
    function lineSeries(name, key, dashed = false) {
      return {
        type: 'line', xKey: 'date', yKey: key, yName: name,
        strokeWidth: 1.6,
        marker: { enabled: false },
        lineDash: dashed ? [4, 4] : undefined,
        interpolation: { type: 'linear' },
      };
    }
    function areaSeries(name, key, stacked = false) {
      return {
        type: 'area', xKey: 'date', yKey: key, yName: name,
        stacked, stackGroup: stacked ? 'stack' : undefined,
        strokeWidth: 0,
        marker: { enabled: false },
      };
    }

    // ---- chart specs -------------------------------------------------------
    function specOutageStack(theme) {
      const data = mergeByTimestamp({ eaf: DATA.eafAvg, pclf: DATA.pclfAvg, uclf: DATA.uclfAvg, oclf: DATA.oclfAvg });
      return {
        theme, data, axes: axes('%', 1, 100, data),
        series: [
          areaSeries('EAF (available)', 'eaf', true),
          areaSeries('PCLF (planned)',  'pclf', true),
          areaSeries('UCLF (unplanned)','uclf', true),
          areaSeries('OCLF (other)',    'oclf', true),
        ],
      };
    }

    function specRenewables(theme) {
      const data = mergeByTimestamp({ wind: DATA.windAvg, pv: DATA.pvAvg, csp: DATA.cspAvg, other: DATA.otherReAvg });
      return {
        theme, data, axes: axes(' MW', 0, undefined, data),
        series: [
          lineSeries('Wind', 'wind'),
          lineSeries('PV', 'pv'),
          lineSeries('CSP', 'csp'),
          lineSeries('Other RE', 'other'),
        ],
      };
    }

    function specThermal(theme) {
      const data = mergeByTimestamp({ tmin: DATA.thermalMin, tavg: DATA.thermalAvg, tmax: DATA.thermalMax });
      return {
        theme, data, axes: axes(' MW', 0, undefined, data),
        series: [
          { ...lineSeries('Min', 'tmin', true), strokeWidth: 1 },
          { ...lineSeries('Average', 'tavg'), strokeWidth: 1.8 },
          { ...lineSeries('Max', 'tmax', true), strokeWidth: 1 },
        ],
      };
    }

    function specNuclear(theme) {
      const data = pairsToXY(DATA.nuclearAvg).map(({x, y}) => ({ date: x, nuclear: y }));
      return {
        theme, data, axes: axes(' MW', 0, undefined, data),
        series: [areaSeries('Average', 'nuclear')],
      };
    }

    function specOcgt(theme) {
      const data = mergeByTimestamp({ eskom: DATA.ocgtEskomMax, ipp: DATA.ocgtIppMax });
      return {
        theme, data, axes: axes(' MW', 0, undefined, data),
        series: [
          areaSeries('Eskom OCGT (peak)',       'eskom', true),
          areaSeries('Dispatchable IPP (peak)', 'ipp',   true),
        ],
      };
    }

    function specTrade(theme) {
      const data = mergeByTimestamp({ imports: DATA.importsAvg, exports: DATA.exportsAvg });
      return {
        theme, data, axes: axes(' MW', 0, undefined, data),
        series: [
          lineSeries('Imports', 'imports'),
          lineSeries('Exports', 'exports'),
        ],
      };
    }

    function specUclfOclfYoy(theme) {
      const years = Object.keys(DATA.uclfOclfByYear || {});
      const xKeys = DATA.uclfOclfXKeys || []; // ['01-01', ...]
      const data = xKeys.map((k, i) => {
        const row = { date: new Date(2024, +k.slice(0, 2) - 1, +k.slice(3)) };
        years.forEach(y => { row[y] = DATA.uclfOclfByYear[y]?.[i] ?? null; });
        return row;
      });
      return {
        theme, data, skipInitialZoom: true,
        axes: [
          { type: 'time', position: 'bottom', label: { format: '%b' } },
          { type: 'number', position: 'left', label: { formatter: ({ value }) => value + '%' } },
        ],
        series: years.map((y) => ({
          type: 'line', xKey: 'date', yKey: y, yName: y,
          strokeWidth: 1.4, marker: { enabled: false }, connectMissingData: false,
        })),
      };
    }

    function specRooftop(theme, provinces, seriesByProv, unitSuffix) {
      const seriesMap = {};
      provinces.forEach(p => { seriesMap[p] = seriesByProv[p] || []; });
      const data = mergeByTimestamp(seriesMap);
      return {
        theme, data, axes: axes(unitSuffix, 1, undefined, data),
        series: provinces.map((p) => ({
          type: 'area', xKey: 'date', yKey: p, yName: p,
          stacked: true, stackGroup: 'rooftop',
          strokeWidth: 0, marker: { enabled: false },
          interpolation: { type: 'step', position: 'end' },
        })),
      };
    }

    function specEafGauge(theme, value) {
      return {
        type: 'radial-gauge',
        theme,
        value: value == null ? 0 : value,
        scale: {
          min: 0, max: 100,
          interval: { step: 20 },
          label: { formatter: ({ value }) => value + '%' },
        },
        bar: {
          fills: [
            { color: '#d32f2f', stop: 50 },
            { color: '#fdd835', stop: 70 },
            { color: '#43a047' },
          ],
          fillMode: 'continuous',
        },
        secondaryLabel: { text: 'EAF' },
        label: { formatter: ({ value }) => value.toFixed(1) + '%' },
      };
    }

    // ---- render ------------------------------------------------------------
    function disposeAll() {
      while (charts.length) {
        const c = charts.pop();
        try { c.destroy(); } catch (_) {}
      }
    }

    // Mix in zoom + navigator (the range-selector bar) on every time-series chart.
    // `rangeButtons` is a Financial-Chart-only option in AG Charts v13; for regular
    // cartesian charts we wire our own preset buttons below the chart via setZoom().
    function withRange(opts) {
      const { skipInitialZoom, ...rest } = opts;
      return {
        ...rest,
        zoom: {
          enabled: true,
          enableAxisDragging: true,
          enablePanning: true,
          enableScrolling: true,
          axes: 'x',
        },
        navigator: { enabled: true, height: 36 },
        initialState: skipInitialZoom ? undefined : initialZoomFor(opts.data),
      };
    }

    function renderAll(theme) {
      disposeAll();
      const c = agCharts.AgCharts;
      const mk = (id, spec) => charts.push(c.create({ container: document.getElementById(id), ...withRange(spec) }));

      charts.push(c.createGauge({ container: document.getElementById('gauge-eaf'), ...specEafGauge(theme, DATA.latestEaf) }));
      mk('chart-outage-stack',              specOutageStack(theme));
      mk('chart-renewables',                specRenewables(theme));
      mk('chart-thermal',                   specThermal(theme));
      mk('chart-nuclear',                   specNuclear(theme));
      mk('chart-ocgt',                      specOcgt(theme));
      mk('chart-uclf-oclf-yoy',             specUclfOclfYoy(theme));
      mk('chart-rooftop-pv',                specRooftop(theme, DATA.rooftopProvinces || [], DATA.rooftopSeries || {}, ' MW'));
      mk('chart-rooftop-pv-per-household',  specRooftop(theme, DATA.rooftopProvincesPerHh || [], DATA.rooftopSeriesPerHh || {}, ' W/hh'));
      mk('chart-trade',                     specTrade(theme));
    }

    // ---- headline values ---------------------------------------------------
    if (DATA.latestGen != null)    document.getElementById('val-generation').textContent = fmt(DATA.latestGen);
    if (DATA.latestDemand != null) document.getElementById('val-demand').textContent = fmt(DATA.latestDemand);
    if (DATA.latestGenLabel)    document.getElementById('lbl-generation').textContent = DATA.latestGenLabel;
    if (DATA.latestDemandLabel) document.getElementById('lbl-demand').textContent = DATA.latestDemandLabel;
    if (DATA.latestEafLabel)    document.getElementById('lbl-eaf').textContent = DATA.latestEafLabel;

    // ---- theming -----------------------------------------------------------
    function detectInitialTheme() {
      if (location.hash === '#dark') return 'dark';
      if (location.hash === '#light') return 'light';
      try { if (window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark'; } catch (e) {}
      return 'light';
    }
    function applyTheme(mode) {
      const m = mode === 'dark' ? 'dark' : 'light';
      document.documentElement.dataset.theme = m;
      renderAll(m === 'dark' ? 'ag-polychroma-dark' : 'ag-polychroma');
    }
    document.getElementById('theme-toggle').addEventListener('click', () => {
      applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    });
    window.addEventListener('message', (e) => {
      if (e.data && e.data.type === 'theme') applyTheme(e.data.mode);
    });
    applyTheme(detectInitialTheme());
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
