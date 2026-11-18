import {useMemo, useRef, useState} from 'react';
import type {ReactNode} from 'react';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import {useColorMode} from '@docusaurus/theme-common';

import {useDashboardData, useIsMobile, type DashboardData, type Point} from '../../lib/dashboardData';
import {PALETTES, type Palette} from '../Dashboard/options';
import styles from './styles.module.css';

// Experimental, unlinked page: ways to see change in a wide-range series
// without truncating the y-axis. Every level chart starts at zero; every
// change chart is centred on zero. Self-contained so it is easy to delete.

const DAY = 86_400_000;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const SYNC_GROUP = 'candles-sync';

type Period = 'week' | 'month' | 'quarter' | 'year';
type Range = '1Y' | '3Y' | '5Y' | 'All';
type BodyMode = 'mean' | 'firstLast';
type GridMode = 'value' | 'yoy';

// good: +1 = higher is better, -1 = higher is worse, 0 = neither.
type Metric = {key: string; label: string; unit: 'MW' | '%'; good: 1 | -1 | 0; daily: (d: DashboardData) => Point[]; note: string};

function combine(series: Point[][], fn: (v: number[]) => number): Point[] {
  const base = series[0] || [];
  const maps = series.map((s) => new Map(s.map(([t, v]) => [t, v])));
  return base.map(([t]) => {
    const vals = maps.map((m) => m.get(t));
    return vals.some((v) => v == null) ? [t, null] : [t, fn(vals as number[])];
  });
}

const METRICS: Metric[] = [
  {key: 'demand', label: 'Demand (avg)', unit: 'MW', good: 0, daily: (d) => d.demandAvg, note: 'Residual demand, daily average'},
  {key: 'peak', label: 'Peak demand', unit: 'MW', good: 0, daily: (d) => d.demandMax, note: 'Highest hour of each day'},
  {key: 'capacity', label: 'Available capacity', unit: 'MW', good: 1, daily: (d) => d.availableCapacityAvg, note: 'What the fleet could deliver after outages'},
  {key: 'headroom', label: 'Headroom (avg)', unit: 'MW', good: 1, daily: (d) => d.headroomAvg, note: 'Available capacity minus demand, daily average'},
  {key: 'headroomMin', label: 'Headroom (tightest hour)', unit: 'MW', good: 1, daily: (d) => d.headroomMin, note: 'Lowest hourly headroom of each day'},
  {key: 'eaf', label: 'EAF', unit: '%', good: 1, daily: (d) => combine([d.pclfAvg, d.uclfAvg, d.oclfAvg], (v) => 100 - (v[0] + v[1] + v[2])), note: 'Energy availability factor, derived'},
  {key: 'uclf', label: 'Unplanned outages', unit: 'MW', good: -1, daily: (d) => d.clfUnplanned, note: 'Capacity lost to breakdowns (UCLF)'},
  {key: 'pclf', label: 'Planned maintenance', unit: 'MW', good: 0, daily: (d) => d.clfPlanned, note: 'Capacity out for planned maintenance (PCLF)'},
  {key: 'gen', label: 'Generation', unit: 'MW', good: 0, daily: (d) => d.genAvg, note: 'Total generation, daily average'},
  {key: 'coal', label: 'Coal', unit: 'MW', good: 0, daily: (d) => d.thermalAvg, note: 'Thermal generation, daily average'},
  {key: 're', label: 'Renewables', unit: 'MW', good: 1, daily: (d) => combine([d.windAvg, d.pvAvg, d.cspAvg, d.otherReAvg], (v) => v[0] + v[1] + v[2] + v[3]), note: 'Wind + PV + CSP + other RE'},
  {key: 'ocgt', label: 'OCGT (diesel)', unit: 'MW', good: -1, daily: (d) => d.ocgtTotalAvg, note: 'Diesel peakers, daily average'},
  {key: 'imports', label: 'Imports', unit: 'MW', good: 0, daily: (d) => d.importsAvg, note: 'Imports, daily average'},
];

// ---------- periods ----------

function periodStart(ts: number, p: Period): number {
  const d = new Date(ts);
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth();
  if (p === 'week') return Date.UTC(y, m, d.getUTCDate()) - ((d.getUTCDay() + 6) % 7) * DAY;
  if (p === 'month') return Date.UTC(y, m, 1);
  if (p === 'quarter') return Date.UTC(y, m - (m % 3), 1);
  return Date.UTC(y, 0, 1);
}
function periodNext(start: number, p: Period): number {
  if (p === 'week') return start + 7 * DAY;
  const d = new Date(start);
  const step = p === 'month' ? 1 : p === 'quarter' ? 3 : 12;
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + step, 1);
}
function yearBefore(start: number, p: Period): number {
  if (p === 'week') return start - 364 * DAY;
  const d = new Date(start);
  return Date.UTC(d.getUTCFullYear() - 1, d.getUTCMonth(), 1);
}
function periodLabel(start: number, p: Period): string {
  const d = new Date(start);
  const y = d.getUTCFullYear();
  if (p === 'week') return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${y}`;
  if (p === 'month') return `${MONTHS[d.getUTCMonth()]} ${y}`;
  if (p === 'quarter') return `Q${Math.floor(d.getUTCMonth() / 3) + 1} ${y}`;
  return String(y);
}
const PER_YEAR: Record<Period, number> = {week: 52, month: 12, quarter: 4, year: 1};

type Row = {
  start: number; label: string;
  first: number; last: number; min: number; max: number; mean: number;
  prevMean: number | null; yoyMean: number | null; roll: number | null;
};

// Daily points → complete periods. Partial first/last periods are dropped:
// a few days aren't comparable with a full month.
function buildRows(daily: Point[], p: Period): Row[] {
  const pts = daily.filter((x): x is [number, number] => x[1] != null).sort((a, b) => a[0] - b[0]);
  if (!pts.length) return [];
  const minTs = pts[0][0];
  const maxTs = pts[pts.length - 1][0];
  const buckets = new Map<number, {first: number; last: number; min: number; max: number; sum: number; n: number}>();
  for (const [t, v] of pts) {
    const k = periodStart(t, p);
    const b = buckets.get(k);
    if (!b) buckets.set(k, {first: v, last: v, min: v, max: v, sum: v, n: 1});
    else {
      b.last = v;
      b.min = Math.min(b.min, v);
      b.max = Math.max(b.max, v);
      b.sum += v;
      b.n += 1;
    }
  }
  const starts = [...buckets.keys()].sort((a, b) => a - b).filter((s) => s >= minTs && periodNext(s, p) - DAY <= maxTs);
  const means = new Map<number, number>();
  for (const s of starts) {
    const b = buckets.get(s)!;
    means.set(s, b.sum / b.n);
  }
  const n = PER_YEAR[p];
  const rows: Row[] = starts.map((s, i) => {
    const b = buckets.get(s)!;
    const mean = b.sum / b.n;
    let roll: number | null = null;
    if (i >= n - 1) {
      let sum = 0;
      for (let j = i - n + 1; j <= i; j++) sum += means.get(starts[j])!;
      roll = sum / n;
    }
    return {
      start: s, label: periodLabel(s, p),
      first: b.first, last: b.last, min: b.min, max: b.max, mean,
      prevMean: i > 0 ? means.get(starts[i - 1])! : null,
      yoyMean: means.get(yearBefore(s, p)) ?? null,
      roll,
    };
  });
  return rows;
}

// ---------- formatting & colour ----------

const GOOD = '#2e9e4f';
const BAD = '#d32f2f';
const UP = '#1976d2';
const DOWN = '#ef6c00';

function upDownColors(good: Metric['good']): [string, string] {
  if (good === 0) return [UP, DOWN];
  return good > 0 ? [GOOD, BAD] : [BAD, GOOD];
}
function deltaColor(delta: number | null, good: Metric['good']): string {
  if (delta == null || delta === 0) return '#9e9e9e';
  const [u, d] = upDownColors(good);
  return delta > 0 ? u : d;
}
function fmt(v: number | null | undefined, unit: string, signed = false): string {
  if (v == null || !isFinite(v)) return '–';
  const dec = unit === '%' ? 1 : 0;
  const s = Math.abs(v).toLocaleString('en-ZA', {minimumFractionDigits: dec, maximumFractionDigits: dec});
  const sign = v < 0 ? '−' : signed && v > 0 ? '+' : '';
  return `${sign}${s} ${unit === '%' ? (signed ? 'pp' : '%') : unit}`;
}
function fmtPct(v: number | null): string {
  if (v == null || !isFinite(v)) return '–';
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`;
}
// Compact cell text: GW for MW series, % with one decimal otherwise.
function cell(v: number, unit: string, signed = false): string {
  const x = unit === 'MW' ? v / 1000 : v;
  const s = Math.abs(x).toFixed(1);
  return `${x < 0 ? '−' : signed && x > 0 ? '+' : ''}${s}`;
}

// ---------- shared chart bits ----------

// Round an axis bound outward to 1/2/2.5/5 × 10^n so ticks land on round numbers.
function niceCeil(x: number): number {
  if (x <= 0) return 0;
  const pow = 10 ** Math.floor(Math.log10(x));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * pow >= x) return m * pow;
  return 10 * pow;
}

function axisBase(P: Palette) {
  return {
    axisLabel: {color: P.axisLabel, fontSize: 11},
    axisLine: {lineStyle: {color: P.axisLine}},
    splitLine: {lineStyle: {color: P.splitLine, type: 'dashed' as const}},
  };
}
function tooltipBase(P: Palette) {
  return {
    trigger: 'axis' as const,
    backgroundColor: P.tooltipBg,
    borderColor: P.tooltipBorder,
    textStyle: {color: P.tooltipText, fontSize: 12},
    axisPointer: {type: 'cross' as const, label: {show: false}},
  };
}
// Every synced chart carries the same two dataZoom components (inside + slider)
// so ECharts' connect() can mirror zooms by index; only the top chart shows
// its slider.
function zoom(P: Palette, startValue: number, showSlider: boolean) {
  return [
    {type: 'inside', startValue, filterMode: 'none'},
    {
      type: 'slider', show: showSlider, startValue, height: 22, bottom: 6, filterMode: 'none',
      borderColor: P.dzBorder, textStyle: {color: P.dzText}, fillerColor: P.dzFill,
      handleStyle: {color: P.dzHandle, borderColor: P.dzBorderH},
    },
  ];
}
function rangeStart(n: number, p: Period, r: Range): number {
  if (r === 'All') return 0;
  const years = r === '1Y' ? 1 : r === '3Y' ? 3 : 5;
  return Math.max(0, n - years * PER_YEAR[p]);
}

function Card({title, children, how}: {title: string; children: ReactNode; how?: ReactNode}) {
  return (
    <div className={styles.card}>
      <div className={styles.cardTitle}>{title}</div>
      {how && <div className={styles.how}>{how}</div>}
      {children}
    </div>
  );
}

function Seg<T extends string>({value, options, onChange}: {value: T; options: {v: T; label: string}[]; onChange: (v: T) => void}) {
  return (
    <div className={styles.seg}>
      {options.map((o) => (
        <button key={o.v} type="button" className={o.v === value ? styles.segOn : styles.segBtn} onClick={() => onChange(o.v)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// Tiny zero-centred YoY bar sparkline as inline SVG.
function YoySpark({vals, good}: {vals: (number | null)[]; good: Metric['good']}) {
  const w = 120;
  const h = 26;
  const m = Math.max(1e-9, ...vals.map((v) => Math.abs(v ?? 0)));
  const bw = w / Math.max(1, vals.length);
  return (
    <svg width={w} height={h} className={styles.spark} aria-hidden>
      <line x1={0} x2={w} y1={h / 2} y2={h / 2} stroke="currentColor" strokeOpacity={0.25} />
      {vals.map((v, i) => {
        if (v == null) return null;
        const bh = (Math.abs(v) / m) * (h / 2 - 1);
        return <rect key={i} x={i * bw + 0.5} width={Math.max(1, bw - 1)} y={v > 0 ? h / 2 - bh : h / 2} height={bh} fill={deltaColor(v, good)} />;
      })}
    </svg>
  );
}

// ---------- page ----------

export default function Candles(): ReactNode {
  const {colorMode} = useColorMode();
  const dark = colorMode === 'dark';
  const P: Palette = PALETTES[dark ? 'dark' : 'light'];
  const {data, err} = useDashboardData();
  const isMobile = useIsMobile();

  const [metricKey, setMetricKey] = useState('demand');
  const [period, setPeriodRaw] = useState<Period>('month');
  const [range, setRange] = useState<Range>('All');
  const [body, setBody] = useState<BodyMode>('mean');
  const [gridMode, setGridMode] = useState<GridMode>('yoy');
  const [yoyPct, setYoyPct] = useState(false);
  const topRef = useRef<HTMLDivElement>(null);

  // Weekly candles over nine years are a blur; open them on the last year.
  const setPeriod = (p: Period) => {
    setPeriodRaw(p);
    setRange(p === 'week' ? '1Y' : p === 'year' ? 'All' : range === '1Y' && p !== 'month' ? 'All' : range);
  };

  const metric = METRICS.find((m) => m.key === metricKey) ?? METRICS[0];
  const [upC, downC] = upDownColors(metric.good);

  // Scorecard: one monthly summary per metric.
  const score = useMemo(() => {
    if (!data) return [];
    return METRICS.map((m) => {
      const rows = buildRows(m.daily(data) ?? [], 'month');
      const last = rows[rows.length - 1];
      if (!last) return {m, last: null as Row | null, yoy: null, yoyPct: null, trend: null, spark: [] as (number | null)[]};
      const yoy = last.yoyMean != null ? last.mean - last.yoyMean : null;
      const prevRoll = rows.length > 12 ? rows[rows.length - 13].roll : null;
      return {
        m, last, yoy,
        yoyPct: yoy != null && last.yoyMean ? (yoy / Math.abs(last.yoyMean)) * 100 : null,
        trend: last.roll != null && prevRoll != null ? last.roll - prevRoll : null,
        spark: rows.slice(-24).map((r) => (r.yoyMean != null ? r.mean - r.yoyMean : null)),
      };
    });
  }, [data]);

  const charts = useMemo(() => {
    if (!data) return null;
    const rows = buildRows(metric.daily(data) ?? [], period);
    if (!rows.length) return null;
    const cats = rows.map((r) => r.label);
    const startValue = rangeStart(rows.length, period, range);
    const ax = axisBase(P);
    const unit = metric.unit;
    const grid = {left: 64, right: 18, top: 36, bottom: 40};
    const yMin = (v: {min: number}) => (v.min < 0 ? -niceCeil(-v.min) : 0);
    const legend = {top: 0, textStyle: {color: P.legend, fontSize: 11}, itemWidth: 14, itemHeight: 8};
    const xAxis = {type: 'category', data: cats, boundaryGap: true, ...ax, splitLine: {show: false}};
    const rowTip = (i: number) => {
      const r = rows[i];
      const yoy = r.yoyMean != null ? r.mean - r.yoyMean : null;
      return (
        `<b>${r.label}</b><br/>` +
        `Average: <b>${fmt(r.mean, unit)}</b><br/>` +
        `Lowest day: ${fmt(r.min, unit)} · Highest day: ${fmt(r.max, unit)}<br/>` +
        `First day: ${fmt(r.first, unit)} · Last day: ${fmt(r.last, unit)}<br/>` +
        `vs previous ${period}: <span style="color:${deltaColor(r.prevMean != null ? r.mean - r.prevMean : null, metric.good)}">${fmt(r.prevMean != null ? r.mean - r.prevMean : null, unit, true)}</span><br/>` +
        `vs a year before: <span style="color:${deltaColor(yoy, metric.good)}">${fmt(yoy, unit, true)}</span>` +
        (r.roll != null ? `<br/>12-month average: ${fmt(r.roll, unit)}` : '')
      );
    };
    const idxTip = (params: any) => rowTip((Array.isArray(params) ? params[0] : params).dataIndex);

    // 1. Candles.
    const candles = {
      animation: false,
      legend: {...legend, data: ['Candle', '12-month average']},
      grid: {...grid, bottom: 64},
      tooltip: {...tooltipBase(P), formatter: idxTip},
      xAxis,
      yAxis: {type: 'value', min: yMin, ...ax},
      dataZoom: zoom(P, startValue, true),
      series: [
        {
          name: 'Candle', type: 'candlestick',
          data: rows.map((r) => (body === 'mean' ? [r.prevMean ?? r.mean, r.mean, r.min, r.max] : [r.first, r.last, r.min, r.max])),
          itemStyle: {color: upC, color0: downC, borderColor: upC, borderColor0: downC},
          barMaxWidth: 18,
        },
        {name: '12-month average', type: 'line', data: rows.map((r) => r.roll), symbol: 'none', lineStyle: {width: 1.5, color: dark ? '#ddd' : '#37474f', type: 'dashed'}, itemStyle: {color: dark ? '#ddd' : '#37474f'}},
      ],
    };

    // 2. Range band: same information as the candles, drawn as a ribbon.
    const band = {
      animation: false,
      legend: {...legend, data: ['Daily range', 'Average', '12-month average']},
      grid,
      tooltip: {...tooltipBase(P), formatter: idxTip},
      xAxis: {...xAxis, boundaryGap: false},
      yAxis: {type: 'value', min: yMin, ...ax},
      dataZoom: zoom(P, startValue, false),
      series: [
        {name: 'base', type: 'line', stack: 'band', data: rows.map((r) => r.min), symbol: 'none', lineStyle: {opacity: 0}, silent: true, tooltip: {show: false}},
        {name: 'Daily range', type: 'line', stack: 'band', data: rows.map((r) => r.max - r.min), symbol: 'none', lineStyle: {opacity: 0}, areaStyle: {color: dark ? 'rgba(124,178,232,0.25)' : 'rgba(25,118,210,0.15)'}, itemStyle: {color: dark ? 'rgba(124,178,232,0.6)' : 'rgba(25,118,210,0.4)'}},
        {name: 'Average', type: 'line', data: rows.map((r) => r.mean), symbol: 'none', lineStyle: {width: 1.6, color: UP}, itemStyle: {color: UP}},
        {name: '12-month average', type: 'line', data: rows.map((r) => r.roll), symbol: 'none', lineStyle: {width: 1.5, color: dark ? '#ddd' : '#37474f', type: 'dashed'}, itemStyle: {color: dark ? '#ddd' : '#37474f'}},
      ],
    };

    // 3. Change vs the same period a year before, zero-centred and symmetric.
    const yoyVals = rows.map((r) => {
      if (r.yoyMean == null) return null;
      const dlt = r.mean - r.yoyMean;
      return yoyPct ? (r.yoyMean ? (dlt / Math.abs(r.yoyMean)) * 100 : null) : dlt;
    });
    const yoyMax = Math.max(1, ...yoyVals.map((v) => Math.abs(v ?? 0)));
    const yoyUnit = yoyPct ? '%' : unit;
    const yoy = {
      animation: false,
      grid,
      tooltip: {...tooltipBase(P), formatter: idxTip},
      xAxis,
      yAxis: {
        type: 'value', min: -niceCeil(yoyMax), max: niceCeil(yoyMax), ...ax,
        axisLabel: {...ax.axisLabel, formatter: (v: number) => (yoyPct ? `${v > 0 ? '+' : ''}${v.toFixed(0)}%` : `${v > 0 ? '+' : ''}${Math.round(v).toLocaleString('en-ZA')}`)},
      },
      dataZoom: zoom(P, startValue, false),
      series: [{
        name: 'Change vs a year before', type: 'bar', barMaxWidth: 18,
        data: yoyVals.map((v) => ({value: v, itemStyle: {color: deltaColor(v, metric.good)}})),
        markLine: {silent: true, symbol: 'none', label: {show: false}, lineStyle: {color: P.axisLabel, type: 'solid', width: 1}, data: [{yAxis: 0}]},
      }],
    };

    // 4. 12-month average, measured as change since the first full year.
    const firstRoll = rows.find((r) => r.roll != null)?.roll ?? null;
    const sinceVals = rows.map((r) => (r.roll != null && firstRoll != null ? r.roll - firstRoll : null));
    const sinceMax = Math.max(1, ...sinceVals.map((v) => Math.abs(v ?? 0)));
    const [goodCol, badCol] = metric.good === -1 ? [BAD, GOOD] : metric.good === 1 ? [GOOD, BAD] : [UP, DOWN];
    const firstFull = rows.find((r) => r.roll != null);
    const since = {
      animation: false,
      grid,
      tooltip: {...tooltipBase(P), formatter: idxTip},
      xAxis: {...xAxis, boundaryGap: false},
      yAxis: {type: 'value', min: -niceCeil(sinceMax), max: niceCeil(sinceMax), ...ax, axisLabel: {...ax.axisLabel, formatter: (v: number) => `${v > 0 ? '+' : ''}${unit === '%' ? v.toFixed(1) : Math.round(v).toLocaleString('en-ZA')}`}},
      dataZoom: zoom(P, startValue, false),
      series: [
        {
          name: 'Above start', type: 'line', data: sinceVals.map((v) => (v == null ? null : Math.max(0, v))), symbol: 'none',
          lineStyle: {width: 2, color: goodCol}, itemStyle: {color: goodCol}, areaStyle: {color: goodCol, opacity: 0.18},
          markLine: {silent: true, symbol: 'none', label: {show: false}, lineStyle: {color: P.axisLabel, type: 'solid', width: 1}, data: [{yAxis: 0}]},
        },
        {
          name: 'Below start', type: 'line', data: sinceVals.map((v) => (v == null ? null : Math.min(0, v))), symbol: 'none',
          lineStyle: {width: 2, color: badCol}, itemStyle: {color: badCol}, areaStyle: {color: badCol, opacity: 0.18},
        },
      ],
    };

    // 5. Stripes: one stripe per period, two rows.
    const flip = metric.good === -1 ? -1 : 1;
    const overall = rows.reduce((s, r) => s + r.mean, 0) / rows.length;
    const devRaw = rows.map((r) => r.mean - overall);
    const devMax = Math.max(1e-9, ...devRaw.map(Math.abs));
    const yoyRaw = rows.map((r) => (r.yoyMean != null ? r.mean - r.yoyMean : null));
    const yoyRawMax = Math.max(1e-9, ...yoyRaw.map((v) => Math.abs(v ?? 0)));
    const stripeData: any[] = [];
    rows.forEach((r, i) => {
      stripeData.push([i, 1, (devRaw[i] / devMax) * flip, devRaw[i]]);
      if (yoyRaw[i] != null) stripeData.push([i, 0, (yoyRaw[i]! / yoyRawMax) * flip, yoyRaw[i]]);
    });
    const neutralMid = dark ? '#2a2a3a' : '#f3f3f3';
    const divColors = metric.good === 0 ? [DOWN, neutralMid, UP] : [BAD, neutralMid, GOOD];
    const stripes = {
      animation: false,
      grid: {left: 130, right: 18, top: 6, bottom: 40},
      tooltip: {
        backgroundColor: P.tooltipBg, borderColor: P.tooltipBorder, textStyle: {color: P.tooltipText, fontSize: 12},
        formatter: (p: any) => `<b>${rows[p.value[0]].label}</b><br/>${p.value[1] === 1 ? `vs long-run average (${fmt(overall, unit)})` : 'vs a year before'}: <b>${fmt(p.value[3], unit, true)}</b>`,
      },
      xAxis: {type: 'category', data: cats, ...ax, splitLine: {show: false}, axisTick: {show: false}},
      yAxis: {type: 'category', data: ['vs a year before', 'vs long-run average'], ...ax, splitLine: {show: false}, axisTick: {show: false}},
      visualMap: {show: false, min: -1, max: 1, dimension: 2, inRange: {color: divColors}},
      dataZoom: zoom(P, startValue, false),
      series: [{type: 'heatmap', data: stripeData, itemStyle: {borderWidth: 0}, emphasis: {disabled: true}}],
    };

    return {candles, band, yoy, since, stripes, firstFull: firstFull?.label ?? 'the first full year'};
  }, [data, metric, period, range, body, yoyPct, P, dark, upC, downC]);

  // 6. Year × month grid — monthly regardless of the period switch.
  const yearGrid = useMemo(() => {
    if (!data) return null;
    const rows = buildRows(metric.daily(data) ?? [], 'month');
    if (!rows.length) return null;
    const years = [...new Set(rows.filter((r) => gridMode === 'value' || r.yoyMean != null).map((r) => new Date(r.start).getUTCFullYear()))].sort((a, b) => a - b);
    const flip = metric.good === -1 ? -1 : 1;
    const pts: any[] = [];
    let maxAbs = 1e-9;
    let lo = Infinity;
    let hi = -Infinity;
    for (const r of rows) {
      const d = new Date(r.start);
      const yoy = r.yoyMean != null ? r.mean - r.yoyMean : null;
      if (gridMode === 'yoy') {
        if (yoy == null) continue;
        maxAbs = Math.max(maxAbs, Math.abs(yoy));
        pts.push({value: [d.getUTCMonth(), years.indexOf(d.getUTCFullYear()), yoy * flip], raw: yoy, mean: r.mean, label: r.label});
      } else {
        lo = Math.min(lo, r.mean);
        hi = Math.max(hi, r.mean);
        pts.push({value: [d.getUTCMonth(), years.indexOf(d.getUTCFullYear()), r.mean], raw: r.mean, mean: r.mean, yoy, label: r.label});
      }
    }
    const unit = metric.unit;
    const neutralMid = dark ? '#2a2a3a' : '#f3f3f3';
    const ax = axisBase(P);
    const visualMap =
      gridMode === 'yoy'
        ? {show: false, min: -maxAbs, max: maxAbs, dimension: 2, inRange: {color: metric.good === 0 ? [DOWN, neutralMid, UP] : [BAD, neutralMid, GOOD]}}
        : {show: false, min: lo, max: hi, dimension: 2, inRange: {color: dark ? ['#1c2433', '#2f6db0'] : ['#f7fbff', '#7fb3e0']}};
    return {
      height: Math.max(220, years.length * 30 + 60),
      option: {
        animation: false,
        grid: {left: 52, right: 12, top: 8, bottom: 28},
        tooltip: {
          backgroundColor: P.tooltipBg, borderColor: P.tooltipBorder, textStyle: {color: P.tooltipText, fontSize: 12},
          formatter: (p: any) => `<b>${p.data.label}</b><br/>Average: ${fmt(p.data.mean, unit)}` + (gridMode === 'yoy' ? `<br/>vs a year before: <b>${fmt(p.data.raw, unit, true)}</b>` : ''),
        },
        xAxis: {type: 'category', data: MONTHS, position: 'top', ...ax, splitLine: {show: false}, axisTick: {show: false}, axisLine: {show: false}},
        yAxis: {type: 'category', data: years.map(String), inverse: true, ...ax, splitLine: {show: false}, axisTick: {show: false}, axisLine: {show: false}},
        visualMap,
        series: [{
          type: 'heatmap', data: pts,
          label: {show: true, fontSize: 11, color: dark ? '#e6e6ed' : '#263238', formatter: (p: any) => cell(p.data.raw, unit, gridMode === 'yoy')},
          itemStyle: {borderColor: dark ? '#14141f' : '#fff', borderWidth: 2},
          emphasis: {disabled: true},
        }],
      },
    };
  }, [data, metric, gridMode, P, dark]);

  if (err) return <div style={{padding: '2rem'}}>Failed to load data: {err}</div>;
  if (!data) return <div style={{padding: '2rem'}}>Loading…</div>;

  const onReady = (inst: any) => {
    inst.group = SYNC_GROUP;
    echarts.connect(SYNC_GROUP);
  };
  const h = (desktop: number) => (isMobile ? Math.round(desktop * 0.75) : desktop);
  const unitWord = metric.unit === 'MW' ? 'GW' : 'percentage points';

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Candles &amp; other experiments</h1>
        <p>
          Experimental page. The question: how do you see a change of a few hundred MW on a series that sits around
          25 000 MW, without cutting the y-axis? Rules followed here: every chart of levels starts at zero, every
          chart of change is centred on zero, and colour means better (green) or worse (red) for that metric, or
          up (blue) and down (orange) when neither is better. Pick a metric in the table or the chips below.
        </p>
      </header>

      <Card title="At a glance — latest full month, every metric" how="Bars: change against the same month a year before, for the last 24 months. Click a row to explore it below.">
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Metric</th>
                <th>Month</th>
                <th className={styles.num}>Average</th>
                <th className={styles.num}>vs a year before</th>
                <th className={styles.num}>12-month avg, change in a year</th>
                <th>Last 24 months vs year before</th>
              </tr>
            </thead>
            <tbody>
              {score.map((s) => (
                <tr key={s.m.key} className={s.m.key === metricKey ? styles.rowOn : styles.row} onClick={() => { setMetricKey(s.m.key); topRef.current?.scrollIntoView({behavior: 'smooth', block: 'start'}); }}>
                  <td title={s.m.note}>{s.m.label}</td>
                  <td>{s.last?.label ?? '–'}</td>
                  <td className={styles.num}>{fmt(s.last?.mean, s.m.unit)}</td>
                  <td className={styles.num} style={{color: deltaColor(s.yoy, s.m.good)}}>
                    {s.yoy == null ? '–' : `${s.yoy > 0 ? '▲' : '▼'} ${fmt(s.yoy, s.m.unit, true)}`}
                    {s.m.unit === 'MW' && s.yoyPct != null && <span className={styles.dim}> ({fmtPct(s.yoyPct)})</span>}
                  </td>
                  <td className={styles.num} style={{color: deltaColor(s.trend, s.m.good)}}>
                    {s.trend == null ? '–' : `${s.trend > 0 ? '▲' : '▼'} ${fmt(s.trend, s.m.unit, true)}`}
                  </td>
                  <td><YoySpark vals={s.spark} good={s.m.good} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div ref={topRef} className={styles.controls}>
        <div className={styles.chips}>
          {METRICS.map((m) => (
            <button key={m.key} type="button" className={m.key === metricKey ? styles.chipOn : styles.chip} onClick={() => setMetricKey(m.key)}>
              {m.label}
            </button>
          ))}
        </div>
        <div className={styles.controlRow}>
          <span className={styles.ctlLabel}>Candle size</span>
          <Seg value={period} onChange={setPeriod} options={[{v: 'week', label: 'Week'}, {v: 'month', label: 'Month'}, {v: 'quarter', label: 'Quarter'}, {v: 'year', label: 'Year'}]} />
          <span className={styles.ctlLabel}>Show</span>
          <Seg value={range} onChange={setRange} options={[{v: '1Y', label: '1Y'}, {v: '3Y', label: '3Y'}, {v: '5Y', label: '5Y'}, {v: 'All', label: 'All'}]} />
          <span className={styles.ctlNote}>{metric.note}. Zooming one chart zooms them all.</span>
        </div>
      </div>

      {!charts ? (
        <div className={styles.card}>No data for {metric.label}.</div>
      ) : (
        <>
          <Card
            title={`${metric.label} — candlesticks (y-axis from zero)`}
            how={
              <>
                <Seg value={body} onChange={setBody} options={[{v: 'mean', label: 'Body: change in average'}, {v: 'firstLast', label: 'Body: first → last day'}]} />
                <span>
                  {body === 'mean'
                    ? `Body runs from the previous ${period}'s average to this ${period}'s average, so its colour and height are the change in the average.`
                    : `Body runs from the first day to the last day of the ${period}, like a share price's open and close.`}{' '}
                  Wicks reach the lowest and highest day.
                </span>
              </>
            }>
            <ReactECharts option={charts.candles} notMerge onChartReady={onReady} style={{height: h(420)}} />
          </Card>

          <Card title={`${metric.label} — daily range ribbon (y-axis from zero)`} how="The same lows, highs and averages as the candles, drawn as a band. Easier to follow the trend; harder to see single-period moves.">
            <ReactECharts option={charts.band} notMerge onChartReady={onReady} style={{height: h(300)}} />
          </Card>

          <Card
            title={`${metric.label} — change against the same ${period} a year before`}
            how={
              <>
                <Seg value={yoyPct ? 'pct' : 'abs'} onChange={(v) => setYoyPct(v === 'pct')} options={[{v: 'abs', label: metric.unit === '%' ? 'Points' : 'MW'}, {v: 'pct', label: '%'}]} />
                <span>Comparing with the same {period} last year removes the winter/summer swing, so what remains is the real trend. The axis is symmetric around zero.</span>
              </>
            }>
            <ReactECharts option={charts.yoy} notMerge onChartReady={onReady} style={{height: h(280)}} />
          </Card>

          <Card title={`${metric.label} — 12-month average, change since the year to ${charts.firstFull}`} how="A rolling year smooths out seasons and noise. The line shows how far that yearly average has moved from where it started.">
            <ReactECharts option={charts.since} notMerge onChartReady={onReady} style={{height: h(280)}} />
          </Card>

          <Card title={`${metric.label} — stripes`} how="One stripe per period, no axis to read. Top: against the average over the whole history. Bottom: against the same period a year before. Darker means a bigger difference.">
            <ReactECharts option={charts.stripes} notMerge onChartReady={onReady} style={{height: 140}} />
          </Card>
        </>
      )}

      {yearGrid && (
        <Card
          title={`${metric.label} — year × month grid (${unitWord})`}
          how={
            <>
              <Seg value={gridMode} onChange={setGridMode} options={[{v: 'yoy', label: 'Change vs year before'}, {v: 'value', label: 'Monthly average'}]} />
              <span>Read across a row for the seasons, down a column for the years. Numbers are in {unitWord}.</span>
            </>
          }>
          <ReactECharts option={yearGrid.option} notMerge style={{height: yearGrid.height}} />
        </Card>
      )}
    </div>
  );
}
