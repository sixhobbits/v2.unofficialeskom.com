import {useEffect, useMemo, useState} from 'react';
import type {ReactNode} from 'react';
import {useColorMode} from '@docusaurus/theme-common';
import useBaseUrl from '@docusaurus/useBaseUrl';

import {PALETTES, timeSeriesOption, type Palette} from '../Dashboard/options';
import {ChartCard, monthlyYoyOption} from '../Dashboard/index';
import card from '../Dashboard/styles.module.css';

// A monthly-aggregate clone of the old Metabase "Long-term" dashboard, so anyone
// who preferred that view has a near-equivalent here. Self-contained on purpose
// (easy to delete if we settle on one layout): it reuses the shared
// timeSeriesOption but builds its own monthly series from the daily arrays in
// dashboard-data.json.

type Point = [number, number | null];

type DashboardData = {
  thermalAvg: Point[];
  nuclearAvg: Point[];
  ocgtMonthlyAvg: Point[];
  ocgtMonthlyMax: Point[];
  hydroAvg: Point[];
  pumpedAvg: Point[];
  reInstalledMonthly: Point[];
  windAvg: Point[];
  pvAvg: Point[];
  cspAvg: Point[];
  otherReAvg: Point[];
  genAvg: Point[];
  demandAvg: Point[];
  importsAvg: Point[];
  exportsAvg: Point[];
  iosAvg: Point[];
  mlrAvg: Point[];
  ilsAvg: Point[];
  iosMax: Point[];
  mlrMax: Point[];
  ilsMax: Point[];
  pclfAvg: Point[];
  uclfAvg: Point[];
  oclfAvg: Point[];
  clfPlanned: Point[];
  clfUnplanned: Point[];
  clfOther: Point[];
  clfTotal: Point[];
  genByYear: Record<string, Array<number | null>>;
  demandByYear: Record<string, Array<number | null>>;
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Daily [ts, value] → one point per calendar month (mean), stamped at the 1st.
function toMonthly(daily: Point[] | undefined): Point[] {
  if (!daily) return [];
  const buckets = new Map<number, {sum: number; n: number}>();
  for (const [ts, v] of daily) {
    if (v == null) continue;
    const d = new Date(ts);
    const key = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
    const b = buckets.get(key) || {sum: 0, n: 0};
    b.sum += v;
    b.n += 1;
    buckets.set(key, b);
  }
  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([ts, b]) => [ts, +(b.sum / b.n).toFixed(1)]);
}

// Daily [ts, value] → one point per calendar month taking the MONTHLY MAX (the
// peak of the daily-peaks). Used for the demand-reduction "max" view.
function toMonthlyMax(daily: Point[] | undefined): Point[] {
  if (!daily) return [];
  const buckets = new Map<number, number>();
  for (const [ts, v] of daily) {
    if (v == null) continue;
    const d = new Date(ts);
    const key = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
    buckets.set(key, Math.max(buckets.get(key) ?? -Infinity, v));
  }
  return [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([ts, v]) => [ts, v]);
}

// The trailing month is usually incomplete (Eskom data ends a few days in), and
// a part-month average isn't comparable — so we cut it. Returns the start-of-
// month for the incomplete trailing month (or null if the last month is full).
function incompleteMonth(daily: Point[] | undefined): {ts: number; year: number; month: number} | null {
  let maxTs = -1;
  for (const [t, v] of daily || []) if (v != null && t > maxTs) maxTs = t;
  if (maxTs < 0) return null;
  const d = new Date(maxTs);
  const y = d.getUTCFullYear();
  const mo = d.getUTCMonth();
  const daysInMonth = new Date(Date.UTC(y, mo + 1, 0)).getUTCDate();
  if (d.getUTCDate() >= daysInMonth) return null; // last month is complete
  return {ts: Date.UTC(y, mo, 1), year: y, month: mo};
}

// Null out the current-year months from the incomplete one onward, for the
// year-over-year {year: [12]} series.
function cutByYear(
  byYear: Record<string, Array<number | null>>,
  cut: {year: number; month: number} | null,
): Record<string, Array<number | null>> {
  if (!cut) return byYear;
  const arr = byYear[String(cut.year)];
  if (!arr) return byYear;
  const a = [...arr];
  for (let i = cut.month; i < 12; i++) a[i] = null;
  return {...byYear, [String(cut.year)]: a};
}

// Combine several daily series (aligned on the first series' timestamps) into a
// derived daily series, e.g. EAF = 100 − Σ(loss factors).
function combineDaily(series: (Point[] | undefined)[], fn: (vals: number[]) => number): Point[] {
  const base = series[0];
  if (!base) return [];
  const maps = series.map((s) => new Map((s || []).map(([t, v]) => [t, v])));
  const out: Point[] = [];
  for (const [t] of base) {
    const vals = maps.map((m) => m.get(t));
    out.push(vals.some((v) => v == null) ? [t, null] : [t, +fn(vals as number[]).toFixed(1)]);
  }
  return out;
}

const LINE = {type: 'line', symbol: 'none', showSymbol: false, animation: false, connectNulls: false} as const;

function line(name: string, data: Point[], color: string, width = 1.6) {
  return {...LINE, name, data, lineStyle: {width, color}, itemStyle: {color}};
}

export default function Monthly(): ReactNode {
  const {colorMode} = useColorMode();
  const P: Palette = PALETTES[colorMode === 'dark' ? 'dark' : 'light'];
  const dataUrl = useBaseUrl('/dashboard-data.json');
  const [data, setData] = useState<DashboardData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(dataUrl)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => !cancelled && setData(j))
      .catch((e) => !cancelled && setErr(String(e)));
    return () => {
      cancelled = true;
    };
  }, [dataUrl]);

  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(max-width: 720px)');
    setIsMobile(mq.matches);
    const h = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', h);
    return () => mq.removeEventListener('change', h);
  }, []);

  const charts = useMemo(() => {
    if (!data) return null;
    // Monthly time-series with a zoom slider opened on the full history.
    const ts = (series: any[], opts: any = {}) => {
      const o = timeSeriesOption(series, {...opts, monthly: true, isMobile}, P) as any;
      o.dataZoom[0].start = 0;
      return o;
    };
    // Drop the incomplete trailing month everywhere (a few days isn't a
    // comparable monthly average). Anchor on the FRESHEST data across all feeds
    // — outage metrics (PCLF/UCLF/OCLF) often run a day or two ahead of demand,
    // so anchoring on one series alone can miss the partial month.
    const cut = incompleteMonth(
      [data.pclfAvg, data.uclfAvg, data.oclfAvg, data.genAvg, data.demandAvg, data.thermalAvg, data.nuclearAvg].flat(),
    );
    const keep = (pts: Point[]) => (cut ? pts.filter((p) => p[0] < cut.ts) : pts);
    const m = (daily: Point[] | undefined) => keep(toMonthly(daily));
    const mMax = (daily: Point[] | undefined) => keep(toMonthlyMax(daily));

    const eafDaily = combineDaily([data.pclfAvg, data.uclfAvg, data.oclfAvg], (v) => 100 - (v[0] + v[1] + v[2]));
    const dispatchableDaily = combineDaily(
      [data.genAvg, data.windAvg, data.pvAvg, data.cspAvg, data.otherReAvg],
      (v) => v[0] - (v[1] + v[2] + v[3] + v[4]),
    );

    return {
      eaf: ts([line('EAF', m(eafDaily), '#2e9e4f', 2)], {unit: '%', decimals: 1}),
      clf: ts([
        line('Planned (PCLF)', m(data.clfPlanned), '#f1c40f'),
        line('Unplanned (UCLF)', m(data.clfUnplanned), '#e57373'),
        line('Other (OCLF)', m(data.clfOther), '#4f9fe0'),
        line('Total', m(data.clfTotal), '#37474f', 1.9),
      ], {unit: 'MW'}),
      genDemand: ts([
        line('Generation', m(data.genAvg), '#1976d2'),
        line('Demand (residual)', m(data.demandAvg), '#d32f2f'),
        line('Dispatchable generation', m(dispatchableDaily), '#5e35b1'),
      ], {unit: 'MW'}),
      thermal: ts([line('Coal', m(data.thermalAvg), '#ff7043')], {unit: 'MW'}),
      nuclear: ts([line('Nuclear', m(data.nuclearAvg), '#ab47bc')], {unit: 'MW'}),
      ocgt: ts([
        {type: 'bar', name: 'Average OCGT', data: keep(data.ocgtMonthlyAvg), animation: false, itemStyle: {color: '#e57373'}},
        {...LINE, name: 'Peak OCGT', data: keep(data.ocgtMonthlyMax), lineStyle: {width: 1.6, color: '#f1c40f'}, itemStyle: {color: '#f1c40f'}},
      ], {unit: 'MW'}),
      hydro: ts([line('Hydro', m(data.hydroAvg), '#26a69a')], {unit: 'MW'}),
      pumped: ts([line('Pumped storage', m(data.pumpedAvg), '#0277bd')], {unit: 'MW', decimals: 1}),
      renewables: ts([
        line('Wind', m(data.windAvg), '#26c6da'),
        line('PV', m(data.pvAvg), '#fdd835'),
        line('CSP', m(data.cspAvg), '#ef6c00'),
        line('Other RE', m(data.otherReAvg), '#9ccc65'),
      ], {unit: 'MW'}),
      trade: ts([
        line('Imports', m(data.importsAvg), '#26a69a'),
        line('Exports', m(data.exportsAvg), '#ef6c00'),
      ], {unit: 'MW'}),
      reduction: ts([
        line('IOS', m(data.iosAvg), '#5e35b1'),
        line('MLR', m(data.mlrAvg), '#ef6c00'),
        line('ILS', m(data.ilsAvg), '#00897b'),
      ], {unit: 'MW', decimals: 1}),
      reductionMax: ts([
        line('IOS (peak)', mMax(data.iosMax), '#5e35b1'),
        line('MLR (peak)', mMax(data.mlrMax), '#ef6c00'),
        line('ILS (peak)', mMax(data.ilsMax), '#00897b'),
      ], {unit: 'MW'}),
      reInstalled: ts([line('Total RE installed capacity', keep(data.reInstalledMonthly), '#43a047')], {unit: 'MW'}),
      genYoy: monthlyYoyOption(cutByYear(data.genByYear, cut), {curColor: '#1976d2'}, P, MONTHS),
      demandYoy: monthlyYoyOption(cutByYear(data.demandByYear, cut), {curColor: '#d32f2f'}, P, MONTHS),
    };
  }, [data, P, isMobile]);

  if (err) return <div style={{padding: '2rem'}}>Failed to load data: {err}</div>;
  if (!data || !charts) return <div style={{padding: '2rem'}}>Loading…</div>;

  return (
    <div style={{width: '100%', padding: '1.5rem'}}>
      <header style={{marginBottom: '1rem'}}>
        <h1 style={{margin: '0 0 0.25rem'}}>Long term</h1>
        <p style={{margin: 0, fontSize: '0.9rem', color: 'var(--ifm-color-emphasis-700)'}}>
          Monthly averages over the full history (2017→present) — a clone of the old long-term
          dashboard. Drag the slider under any chart to zoom.
        </p>
      </header>

      <h2 className={card.sectionTitle}>Availability &amp; outages</h2>
      <div className={card.chartPair}>
        <ChartCard title="Energy availability factor (monthly avg %)" option={charts.eaf} />
        <ChartCard title="Capability loss factors (monthly avg MW)" option={charts.clf} />
      </div>

      <h2 className={card.sectionTitle}>Generation &amp; demand</h2>
      <div className={card.chartGrid}>
        <ChartCard title="Dispatchable generation vs demand (monthly avg MW)" option={charts.genDemand} />
      </div>
      <div className={card.chartPair}>
        <ChartCard title="Generation by year (monthly avg MW)" option={charts.genYoy} />
        <ChartCard title="Demand by year (monthly avg MW)" option={charts.demandYoy} />
      </div>

      <h2 className={card.sectionTitle}>Generation mix</h2>
      <div className={card.chartPair}>
        <ChartCard title="Coal / thermal (monthly avg MW)" option={charts.thermal} />
        <ChartCard title="Nuclear (monthly avg MW)" option={charts.nuclear} />
      </div>
      <div className={card.chartPair}>
        <ChartCard title="OCGT — average (bars) &amp; peak (line) per month (MW)" option={charts.ocgt} />
        <ChartCard title="Hydro (monthly avg MW)" option={charts.hydro} />
      </div>
      <div className={card.chartPair}>
        <ChartCard title="Pumped storage (monthly avg MW)" option={charts.pumped} />
        <ChartCard title="Renewables (monthly avg MW)" option={charts.renewables} />
      </div>
      <div className={card.chartGrid}>
        <ChartCard title="Renewable installed capacity (monthly avg MW)" option={charts.reInstalled} />
      </div>

      <h2 className={card.sectionTitle}>Trade &amp; demand reduction</h2>
      <div className={card.chartPair}>
        <ChartCard title="Imports &amp; exports (monthly avg MW)" option={charts.trade} />
        <ChartCard title="Demand reduction — IOS / MLR / ILS (monthly avg MW)" option={charts.reduction} />
      </div>
      <div className={card.chartGrid}>
        <ChartCard title="Demand reduction — IOS / MLR / ILS (monthly peak MW)" option={charts.reductionMax} />
      </div>
    </div>
  );
}
