import {useMemo, useRef, useState} from 'react';
import type {ReactNode} from 'react';
import ReactECharts from 'echarts-for-react';
import {useColorMode} from '@docusaurus/theme-common';
import clsx from 'clsx';

import {useDashboardData, useIsMobile, type Point} from '../../lib/dashboardData';
import {PALETTES, timeSeriesOption, type Palette} from './options';
import {Gauge} from './Gauge';
import styles from './styles.module.css';

const ROOFTOP_PALETTE = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
  '#8c564b', '#e377c2', '#17becf', '#bcbd22',
];
const YOY_PALETTE = ['#90a4ae', '#80deea', '#ffd54f', '#ef6c00', '#7e57c2', '#43a047'];

const LINE_BASE = {
  type: 'line',
  symbol: 'none',
  showSymbol: false,
  sampling: 'lttb',
  large: true,
  largeThreshold: 2000,
  animation: false,
  progressive: 4000,
  progressiveThreshold: 4000,
} as const;
const AREA_STACK = {
  ...LINE_BASE,
  stack: 'cap',
  areaStyle: {opacity: 0.85},
  lineStyle: {width: 0},
} as const;

const RANGE_PRESETS: Array<{label: string; days: number | null}> = [
  {label: '7D', days: 7},
  {label: '1M', days: 30},
  {label: '3M', days: 90},
  {label: '1Y', days: 365},
  {label: 'All', days: null},
];

export function ChartCard({title, option}: {title: string; option: any}) {
  const chartRef = useRef<ReactECharts>(null);
  // Presets only make sense on time-axis charts with a zoom slider — the
  // category YoY charts get just the title.
  const hasTimeZoom = option?.xAxis?.type === 'time' && option?.dataZoom;

  const setRange = (days: number | null) => {
    const inst = chartRef.current?.getEchartsInstance();
    if (!inst) return;
    if (days == null) {
      inst.dispatchAction({type: 'dataZoom', start: 0, end: 100});
      return;
    }
    // Window end = newest timestamp across all series, not "now" — some feeds
    // lag a few days and an empty window would look broken.
    let maxTs = -Infinity;
    for (const s of option.series ?? []) {
      const d = s?.data;
      const last = Array.isArray(d) && d.length ? d[d.length - 1] : null;
      const t = Array.isArray(last) ? last[0] : null;
      if (typeof t === 'number' && t > maxTs) maxTs = t;
    }
    if (!isFinite(maxTs)) return;
    inst.dispatchAction({type: 'dataZoom', startValue: maxTs - days * 86_400_000, endValue: maxTs});
  };

  return (
    <div className={styles.card}>
      <div className={styles.chartHead}>
        <div className={styles.chartTitle}>{title}</div>
        {hasTimeZoom && (
          <div className={styles.rangeBtns}>
            {RANGE_PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className={styles.rangeBtn}
                onClick={() => setRange(p.days)}>
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <ReactECharts
        ref={chartRef}
        option={option}
        notMerge
        lazyUpdate
        style={{height: 320, width: '100%'}}
        opts={{renderer: 'canvas'}}
      />
    </div>
  );
}

function fmt(n: number | null | undefined) {
  if (n == null) return '–';
  return Math.round(n).toLocaleString('en-ZA');
}

function lastVal(series: Array<[number, number | null]> | undefined): number | null {
  if (!series || !series.length) return null;
  for (let i = series.length - 1; i >= 0; i--) {
    const v = series[i][1];
    if (v != null) return v;
  }
  return null;
}

function fmt1(n: number | null) {
  return n == null ? '–' : n.toFixed(1);
}

// Insert explicit null points where the time series has gaps wider than
// thresholdDays. ECharts otherwise draws a straight line across gaps; nulls
// force connectNulls:false to actually break the line.
function withGapNulls(
  series: Array<[number, number | null]>,
  thresholdDays = 3,
): Array<[number, number | null]> {
  if (series.length < 2) return series;
  const ms = thresholdDays * 86_400_000;
  const out: Array<[number, number | null]> = [series[0]];
  for (let i = 1; i < series.length; i++) {
    const [t, v] = series[i];
    const [tPrev] = series[i - 1];
    if (t - tPrev > ms) {
      out.push([tPrev + ms / 2, null]);
    }
    out.push([t, v]);
  }
  return out;
}

// Trailing N-point rolling mean of a single [ts, value] series (skips nulls).
// Used to smooth the outage-split lines, which mix daily (bulk / trend CSV) and
// weekly (system-status report, held flat per week) sources into one jagged +
// stepped picture — a 7-day mean reads as a consistent trend.
function rollingMean(
  series: Array<[number, number | null]>,
  win = 7,
): Array<[number, number | null]> {
  return series.map((pt, i) => {
    let sum = 0;
    let count = 0;
    for (let j = Math.max(0, i - win + 1); j <= i; j++) {
      const v = series[j][1];
      if (v != null) {
        sum += v;
        count++;
      }
    }
    return [pt[0], count ? +(sum / count).toFixed(2) : null];
  });
}

// Trailing N-hour rolling mean of (a[i] + b[i]). Series a and b are assumed
// to share the same timestamps. Skips hours where either side is null.
function rollingSumAvg(
  a: Array<[number, number | null]>,
  b: Array<[number, number | null]>,
  windowHours = 24 * 7,
): Array<[number, number | null]> {
  const n = Math.min(a.length, b.length);
  const out: Array<[number, number | null]> = [];
  let sum = 0;
  let count = 0;
  const valueAt = (i: number): number | null => {
    const va = a[i]?.[1];
    const vb = b[i]?.[1];
    if (va == null || vb == null) return null;
    return va + vb;
  };
  for (let i = 0; i < n; i++) {
    const v = valueAt(i);
    if (v != null) {
      sum += v;
      count++;
    }
    if (i >= windowHours) {
      const drop = valueAt(i - windowHours);
      if (drop != null) {
        sum -= drop;
        count--;
      }
    }
    out.push([a[i][0], count > 0 ? sum / count : null]);
  }
  return out;
}

// A weekly year-over-year line chart on a shared Jan→Dec week axis: every year
// overlaid, the current year drawn bold in `curColor`, earlier years fading to
// progressively lighter grey (oldest lightest). By default only the current
// year and the previous two are visible; the rest are toggleable in the legend.
// Defensive against a stale cached JSON that predates the data fields — a
// missing field degrades the card, never crashes the dashboard.
function weeklyYoyOption(
  byYearRaw: Record<string, Array<number | null>> | undefined,
  weeksRaw: number[] | undefined,
  opts: {curColor: string; yMin?: number; yMax?: number; defaultYears?: number; unit?: '%' | 'MW'},
  P: Palette,
  months: string[],
) {
  const isPct = (opts.unit ?? '%') === '%';
  const fmtVal = (v: number) =>
    isPct ? Number(v).toFixed(1) + '%' : Math.round(Number(v)).toLocaleString('en-US') + ' MW';
  const fmtAxis = (v: number) => (isPct ? v + '%' : Number(v).toLocaleString('en-US'));
  const byYear = byYearRaw ?? {};
  const weeks = weeksRaw ?? [];
  const years = Object.keys(byYear).sort();
  const curYear = years[years.length - 1];
  const past = years.filter((y) => y !== curYear); // ascending, oldest first
  const grey = (year: string) => {
    const n = past.length;
    const i = past.indexOf(year);
    const t = n <= 1 ? 1 : i / (n - 1); // 0 = oldest, 1 = most recent past
    const g = Math.round(216 - (216 - 120) * t); // light grey → dark grey
    return `rgb(${g},${g},${g})`;
  };
  // Month of the week starting `i*7` days into a reference (non-leap) year —
  // used to drop a month label at the first week of each calendar month.
  const weekMonth = (i: number) => new Date(Date.UTC(2025, 0, 1 + i * 7)).getUTCMonth();
  const visible = opts.defaultYears ?? 3; // current + previous two
  const selected: Record<string, boolean> = {};
  years.forEach((y, i) => {
    selected[y] = i >= years.length - visible;
  });
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: P.tooltipBg,
      borderColor: P.tooltipBorder,
      borderWidth: 1,
      textStyle: {color: P.tooltipText, fontSize: 12},
      formatter: (params: any[]) => {
        const wk = +String(params[0].axisValue).slice(1);
        const lines = params
          .filter((p: any) => p.value != null)
          .sort((a: any, b: any) => Number(b.value) - Number(a.value))
          .map((p: any) => p.marker + ' ' + p.seriesName + ': <b>' + fmtVal(p.value) + '</b>');
        return '<div style="font-weight:600;margin-bottom:4px">Week ' + wk + '</div>' + lines.join('<br/>');
      },
    },
    legend: {data: years, selected, top: 0, left: 'center', selectedMode: true, icon: 'rect', itemWidth: 14, itemHeight: 10, itemGap: 14, textStyle: {fontSize: 11, color: P.legend}},
    grid: {top: 50, right: 18, bottom: 30, left: 56},
    xAxis: {
      type: 'category',
      data: weeks.map((w) => 'W' + String(w).padStart(2, '0')),
      boundaryGap: false,
      axisLabel: {
        interval: 0,
        formatter: (_v: string, i: number) =>
          i === 0 || weekMonth(i) !== weekMonth(i - 1) ? months[weekMonth(i)] : '',
        fontSize: 10,
        color: P.axisLabel,
      },
      axisTick: {alignWithLabel: true},
      axisLine: {lineStyle: {color: P.axisLine}},
      splitLine: {show: false},
    },
    yAxis: {
      type: 'value',
      min: opts.yMin,
      max: opts.yMax,
      scale: true,
      axisLabel: {fontSize: 10, color: P.axisLabel, formatter: fmtAxis},
      axisLine: {show: false},
      axisTick: {show: false},
      splitLine: {lineStyle: {color: P.splitLine, type: 'dashed'}},
    },
    series: [
      ...past.map((year) => ({
        name: year,
        type: 'line',
        data: byYear[year],
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        animation: false,
        z: 2,
        lineStyle: {width: 1.2, color: grey(year)},
        itemStyle: {color: grey(year)},
      })),
      ...(curYear
        ? [{
            name: curYear,
            type: 'line',
            data: byYear[curYear],
            symbol: 'none',
            showSymbol: false,
            connectNulls: false,
            animation: false,
            z: 10,
            lineStyle: {width: 3, color: opts.curColor},
            itemStyle: {color: opts.curColor},
          }]
        : []),
    ],
  };
}

// Monthly generation/demand year-over-year: each year a line on a Jan→Dec month
// axis — current year bold in curColor, earlier years fading grey (oldest
// lightest). Defaults to the current year + previous two; the rest toggle in the
// legend. Mirrors weeklyYoyOption on a 12-month category axis.
export function monthlyYoyOption(
  byYearRaw: Record<string, Array<number | null>> | undefined,
  opts: {curColor: string; defaultYears?: number},
  P: Palette,
  monthNames: string[],
) {
  const fmtVal = (v: number) => Math.round(Number(v)).toLocaleString('en-US') + ' MW';
  const byYear = byYearRaw ?? {};
  const years = Object.keys(byYear).sort();
  const curYear = years[years.length - 1];
  const past = years.filter((y) => y !== curYear);
  const grey = (year: string) => {
    const n = past.length;
    const i = past.indexOf(year);
    const t = n <= 1 ? 1 : i / (n - 1);
    const g = Math.round(216 - (216 - 120) * t);
    return `rgb(${g},${g},${g})`;
  };
  const visible = opts.defaultYears ?? 3;
  const selected: Record<string, boolean> = {};
  years.forEach((y, i) => {
    selected[y] = i >= years.length - visible;
  });
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: P.tooltipBg,
      borderColor: P.tooltipBorder,
      borderWidth: 1,
      textStyle: {color: P.tooltipText, fontSize: 12},
      formatter: (params: any[]) => {
        const mon = monthNames[params[0].dataIndex] ?? params[0].axisValue;
        const lines = params
          .filter((p: any) => p.value != null)
          .sort((a: any, b: any) => Number(b.value) - Number(a.value))
          .map((p: any) => p.marker + ' ' + p.seriesName + ': <b>' + fmtVal(p.value) + '</b>');
        return '<div style="font-weight:600;margin-bottom:4px">' + mon + '</div>' + lines.join('<br/>');
      },
    },
    legend: {data: years, selected, top: 0, left: 'center', icon: 'rect', itemWidth: 14, itemHeight: 10, itemGap: 14, textStyle: {fontSize: 11, color: P.legend}},
    grid: {top: 50, right: 18, bottom: 30, left: 56},
    xAxis: {
      type: 'category',
      data: monthNames,
      boundaryGap: false,
      axisLabel: {fontSize: 10, color: P.axisLabel},
      axisTick: {alignWithLabel: true},
      axisLine: {lineStyle: {color: P.axisLine}},
      splitLine: {show: false},
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {fontSize: 10, color: P.axisLabel, formatter: (v: number) => Number(v).toLocaleString('en-US')},
      axisLine: {show: false},
      axisTick: {show: false},
      splitLine: {lineStyle: {color: P.splitLine, type: 'dashed'}},
    },
    series: [
      ...past.map((year) => ({
        name: year, type: 'line', data: byYear[year],
        symbol: 'none', showSymbol: false, connectNulls: false, animation: false, z: 2,
        lineStyle: {width: 1.2, color: grey(year)}, itemStyle: {color: grey(year)},
      })),
      ...(curYear
        ? [{
            name: curYear, type: 'line', data: byYear[curYear],
            symbol: 'none', showSymbol: false, connectNulls: false, animation: false, z: 10,
            lineStyle: {width: 3, color: opts.curColor}, itemStyle: {color: opts.curColor},
          }]
        : []),
    ],
  };
}

export default function Dashboard(): ReactNode {
  const {colorMode} = useColorMode();
  const P: Palette = PALETTES[colorMode === 'dark' ? 'dark' : 'light'];

  const {data, err} = useDashboardData();

  const displayTs = useMemo(() => {
    if (!data?.latestTs) return 'Unknown';
    return new Date(data.latestTs).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
  }, [data?.latestTs]);

  const rooftopColorByProv = useMemo(() => {
    const map: Record<string, string> = {};
    (data?.rooftopProvinces ?? []).forEach((prov, i) => {
      map[prov] = ROOFTOP_PALETTE[i % ROOFTOP_PALETTE.length];
    });
    return map;
  }, [data?.rooftopProvinces]);

  // Mobile stat carousel: which 2×2 page is in view. The wrappers are
  // display:contents on desktop, so none of this affects the grid layout.
  const statPagesRef = useRef<HTMLDivElement>(null);
  const [statPage, setStatPage] = useState(0);
  const onStatScroll = () => {
    const el = statPagesRef.current;
    if (!el) return;
    let best = 0;
    let bestDist = Infinity;
    Array.from(el.children).forEach((kid, i) => {
      const d = Math.abs((kid as HTMLElement).offsetLeft - el.scrollLeft);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    setStatPage(best);
  };
  const scrollToStatPage = (i: number) => {
    const el = statPagesRef.current;
    const kid = el?.children[i] as HTMLElement | undefined;
    if (el && kid) el.scrollTo({left: kid.offsetLeft, behavior: 'smooth'});
  };

  const isMobile = useIsMobile();

  const charts = useMemo(() => {
    if (!data) return null;

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const ts = (
      series: Parameters<typeof timeSeriesOption>[0],
      opts: Parameters<typeof timeSeriesOption>[1] = {},
    ) => timeSeriesOption(series, {...opts, isMobile}, P);

    // Capability loss factors in MW: planned / unplanned / other and their total.
    const clf = ts(
      [
        {...LINE_BASE, name: 'Planned (PCLF)', data: data.clfPlanned, lineStyle: {width: 1.4, color: '#f1c40f'}, itemStyle: {color: '#f1c40f'}},
        {...LINE_BASE, name: 'Unplanned (UCLF)', data: data.clfUnplanned, lineStyle: {width: 1.4, color: '#e57373'}, itemStyle: {color: '#e57373'}},
        {...LINE_BASE, name: 'Other (OCLF)', data: data.clfOther, lineStyle: {width: 1.4, color: '#4f9fe0'}, itemStyle: {color: '#4f9fe0'}},
        {...LINE_BASE, name: 'Total', data: data.clfTotal, lineStyle: {width: 1.8, color: '#37474f'}, itemStyle: {color: '#37474f'}},
      ],
      {unit: 'MW', decimals: 0});

    // Demand-reduction tools (daily MW). Mostly zero with spikes during
    // constrained periods, so each gets its own chart — daily average solid,
    // daily peak as a dashed line (averages hide short, sharp curtailment).
    const reductionChart = (avg: Point[], max: Point[], color: string) =>
      ts([
        {...LINE_BASE, name: 'Daily avg', data: avg, lineStyle: {width: 1.4, color}, areaStyle: {color, opacity: 0.12}, itemStyle: {color}},
        {...LINE_BASE, name: 'Daily max', data: max, lineStyle: {width: 1, color, type: 'dashed'}, itemStyle: {color}},
      ], {unit: 'MW', decimals: 1});
    const iosChart = reductionChart(data.iosAvg, data.iosMax, '#5e35b1');
    const mlrChart = reductionChart(data.mlrAvg, data.mlrMax, '#ef6c00');
    const ilsChart = reductionChart(data.ilsAvg, data.ilsMax, '#00897b');
    const totalReductionChart = reductionChart(data.totalReductionAvg, data.totalReductionMax, '#d32f2f');

    const renewables = ts(
      [
        {...LINE_BASE, name: 'Wind', data: data.windAvg, lineStyle: {width: 1.4, color: '#26c6da'}, itemStyle: {color: '#26c6da'}},
        {...LINE_BASE, name: 'PV', data: data.pvAvg, lineStyle: {width: 1.4, color: '#fdd835'}, itemStyle: {color: '#fdd835'}},
        {...LINE_BASE, name: 'CSP', data: data.cspAvg, lineStyle: {width: 1.4, color: '#ef6c00'}, itemStyle: {color: '#ef6c00'}},
        {...LINE_BASE, name: 'Other RE', data: data.otherReAvg, lineStyle: {width: 1.4, color: '#9ccc65'}, itemStyle: {color: '#9ccc65'}},
      ],
      {});

    const rooftopPv = ts(
      (data.rooftopProvinces || []).map((prov) => ({
        type: 'bar', stack: 'rooftop', name: prov, data: data.rooftopSeries[prov] || [],
        animation: false, large: true,
        itemStyle: {color: rooftopColorByProv[prov]},
      })),
      {unit: 'MW', decimals: 1});

    const rooftopPvPerHh = ts(
      (data.rooftopProvincesPerHh || []).map((prov) => ({
        type: 'bar', stack: 'rooftop_per_hh', name: prov, data: data.rooftopSeriesPerHh[prov] || [],
        animation: false, large: true,
        itemStyle: {color: rooftopColorByProv[prov]},
      })),
      {
        unit: 'W/household',
        decimals: 1,
        yAxis: {
          type: 'value',
          axisLabel: {fontSize: 10, color: P.axisLabel, formatter: (v: number) => v.toLocaleString('en-ZA') + ' W/hh'},
          axisLine: {show: false},
          axisTick: {show: false},
          splitLine: {lineStyle: {color: P.splitLine, type: 'dashed'}},
        },
      });

    const thermal = ts(
      [
        {...LINE_BASE, name: 'Min (dashed)', data: data.thermalMin, lineStyle: {width: 1, color: '#ffab91', type: 'dashed'}, itemStyle: {color: '#ffab91'}},
        {...LINE_BASE, name: 'Average', data: data.thermalAvg, lineStyle: {width: 1.8, color: '#ff7043'}, itemStyle: {color: '#ff7043'}},
        {...LINE_BASE, name: 'Max (dashed)', data: data.thermalMax, lineStyle: {width: 1, color: '#bf360c', type: 'dashed'}, itemStyle: {color: '#bf360c'}},
      ],
      {});

    const nuclear = ts(
      [{...LINE_BASE, name: 'Average', data: data.nuclearAvg, lineStyle: {width: 1.6, color: '#ab47bc'}, areaStyle: {color: '#ab47bc', opacity: 0.15}, itemStyle: {color: '#ab47bc'}}],
      {});

    const ocgt = ts(
      [
        {
          type: 'bar',
          name: 'Eskom OCGT (peak)',
          data: data.ocgtEskomMax,
          stack: 'ocgt',
          large: true,
          animation: false,
          itemStyle: {color: '#42a5f5'},
        },
        {
          type: 'bar',
          name: 'Dispatchable IPP (peak)',
          data: data.ocgtIppMax,
          stack: 'ocgt',
          large: true,
          animation: false,
          itemStyle: {color: '#66bb6a'},
        },
        {
          ...LINE_BASE,
          name: 'Combined (daily avg)',
          data: data.ocgtTotalAvg,
          lineStyle: {width: 1.6, color: '#ef6c00'},
          itemStyle: {color: '#ef6c00'},
          z: 5,
        },
      ],
      {});

    // Default the dataZoom window to roughly the last 14 days of the
    // ~1-year hourly window we publish.
    const hourlyDefaultStart =
      data.ocgtEskomHourly.length > 0
        ? Math.max(0, ((data.ocgtEskomHourly.length - 14 * 24) / data.ocgtEskomHourly.length) * 100)
        : 0;
    const ocgtRolling7d = rollingSumAvg(data.ocgtEskomHourly, data.ocgtIppHourly);
    const ocgtHourly = ts(
      [
        {
          ...AREA_STACK,
          name: 'Eskom OCGT',
          data: data.ocgtEskomHourly,
          stack: 'ocgt_h',
          itemStyle: {color: '#42a5f5'},
          areaStyle: {color: '#42a5f5', opacity: 0.85},
        },
        {
          ...AREA_STACK,
          name: 'Dispatchable IPP',
          data: data.ocgtIppHourly,
          stack: 'ocgt_h',
          itemStyle: {color: '#66bb6a'},
          areaStyle: {color: '#66bb6a', opacity: 0.85},
        },
        {
          ...LINE_BASE,
          name: '7-day rolling avg, combined (dashed)',
          data: ocgtRolling7d,
          lineStyle: {width: 1.8, color: '#ef6c00', type: 'dashed'},
          itemStyle: {color: '#ef6c00'},
          z: 5,
        },
      ],
      // Open on the last ~14d of the ~1-year hourly window.
      {hourly: true, zoomStart: hourlyDefaultStart});

    const pumpedStorage = ts(
      [{...LINE_BASE, name: 'Pumped storage generation (daily avg)', data: data.pumpedAvg, lineStyle: {width: 1.4, color: '#0277bd'}, areaStyle: {color: '#0277bd', opacity: 0.12}, itemStyle: {color: '#0277bd'}}],
      {unit: 'MW', decimals: 1});

    const years = Object.keys(data.uclfOclfByYear);
    const uclfOclfYoy = {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: P.tooltipBg,
        borderColor: P.tooltipBorder,
        borderWidth: 1,
        textStyle: {color: P.tooltipText, fontSize: 12},
        formatter: (params: any[]) => {
          const day = months[+params[0].axisValue.slice(0, 2) - 1] + ' ' + +params[0].axisValue.slice(3);
          const lines = params
            .filter((p: any) => p.value != null)
            .map((p: any) => p.marker + ' ' + p.seriesName + ': <b>' + Number(p.value).toFixed(2) + '%</b>');
          return '<div style="font-weight:600;margin-bottom:4px">' + day + '</div>' + lines.join('<br/>');
        },
      },
      legend: {data: years, top: 0, left: 'center', selectedMode: true, icon: 'rect', itemWidth: 14, itemHeight: 10, itemGap: 18, textStyle: {fontSize: 11, color: P.legend}},
      grid: {top: 50, right: 18, bottom: 30, left: 56},
      xAxis: {
        type: 'category',
        data: data.uclfOclfXKeys,
        boundaryGap: false,
        axisLabel: {
          interval: 0,
          formatter: (v: string) => (v.endsWith('-01') ? months[+v.slice(0, 2) - 1] : ''),
          fontSize: 10,
          color: P.axisLabel,
        },
        axisTick: {alignWithLabel: true, interval: (_: number, v: string) => v.endsWith('-01')},
        axisLine: {lineStyle: {color: P.axisLine}},
        splitLine: {show: false},
      },
      yAxis: {
        type: 'value',
        axisLabel: {fontSize: 10, color: P.axisLabel, formatter: (v: number) => v + '%'},
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {lineStyle: {color: P.splitLine, type: 'dashed'}},
      },
      series: years.map((year, i) => ({
        name: year,
        type: 'line',
        data: data.uclfOclfByYear[year],
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        sampling: 'lttb',
        animation: false,
        lineStyle: {width: 1.4, color: YOY_PALETTE[i % YOY_PALETTE.length]},
        itemStyle: {color: YOY_PALETTE[i % YOY_PALETTE.length]},
      })),
    };

    // Weekly EAF (available) and total outages (planned + unplanned = 100 − EAF),
    // each overlaid year-over-year on a shared Jan→Dec week axis.
    const eafYoy = weeklyYoyOption(
      data.eafByYear, data.eafWeeks, {curColor: '#2e9e4f', yMin: 45, yMax: 90}, P, months);
    // Outage split as three lines over the full daily history, smoothed to a
    // 7-day trailing mean so the daily (UCLF) and weekly-held (PCLF/OCLF)
    // sources read as one consistent trend. Opens on the last ~3 months with a
    // zoom slider (the YoY view lives in the EAF chart).
    const outageLen = data.uclfAvg.length;
    const outagesYoy = ts(
      [
        {...LINE_BASE, name: 'Unplanned (UCLF)', data: rollingMean(data.uclfAvg), lineStyle: {width: 1.6, color: '#e53935'}, itemStyle: {color: '#e53935'}},
        {...LINE_BASE, name: 'Planned (PCLF)', data: rollingMean(data.pclfAvg), lineStyle: {width: 1.6, color: '#f1c40f'}, itemStyle: {color: '#f1c40f'}},
        {...LINE_BASE, name: 'Other (OCLF)', data: rollingMean(data.oclfAvg), lineStyle: {width: 1.4, color: '#37474f'}, itemStyle: {color: '#37474f'}},
      ],
      {unit: '%', decimals: 1, zoomStart: outageLen > 90 ? ((outageLen - 90) / outageLen) * 100 : 0});

    // Hourly detail for the last ~3 months (no lttb sampling — it misaligns
    // stacked areas). Both open on the full 3-month window.
    const stack = (name: string, d: Point[], color: string) => ({
      type: 'line', name, data: d, stack: 'h', symbol: 'none', showSymbol: false,
      large: true, animation: false, areaStyle: {color, opacity: 0.85}, lineStyle: {width: 0}, itemStyle: {color},
    });
    const STATION: Array<[string, string, string]> = [
      ['coal', 'Coal', '#6d4c41'], ['nuclear', 'Nuclear', '#ab47bc'], ['ocgt', 'OCGT (diesel/gas)', '#ef6c00'],
      ['hydro', 'Hydro', '#26a69a'], ['pumped', 'Pumped storage', '#5c6bc0'], ['imports', 'Imports', '#90a4ae'],
      ['wind', 'Wind', '#26c6da'], ['pv', 'PV', '#fdd835'], ['otherRe', 'Other RE', '#9ccc65'],
    ];
    const stationHourly = ts(
      STATION.map(([k, name, color]) => stack(name, data.stationHourly[k] ?? [], color)),
      {hourly: true, zoomStart: 0},
    );

    const oh = data.outageHourly;
    // Eskom's own published weekly EAF, windowed to the hourly chart's range —
    // a stepped reference against the derived hourly EAF.
    const ohStart = oh.eaf[0]?.[0] ?? 0;
    const officialEafWindow = data.officialEafWeekly.filter((p) => p[0] >= ohStart);
    const eafOutageHourly = ts(
      [
        stack('Unplanned (UCLF)', oh.uclf, '#e57373'),
        stack('Planned (PCLF)', oh.pclf, '#f1c40f'),
        stack('Other (OCLF)', oh.oclf, '#4f9fe0'),
        // Plain line, no lttb sampling — sampling here duplicated EAF in the
        // axis tooltip and isn't needed at hourly/3-month scale.
        {type: 'line', name: 'EAF', data: oh.eaf, symbol: 'none', showSymbol: false, large: true, animation: false, lineStyle: {width: 1.6, color: '#2e9e4f'}, itemStyle: {color: '#2e9e4f'}, z: 5},
        {type: 'line', name: 'EAF (Eskom weekly)', data: officialEafWindow, step: 'start', symbol: 'none', showSymbol: false, animation: false, lineStyle: {width: 1.4, color: '#8e44ad', type: 'dashed'}, itemStyle: {color: '#8e44ad'}, z: 6},
      ],
      {
        unit: '%',
        decimals: 1,
        hourly: true,
        zoomStart: 0,
        yAxis: {
          type: 'value', min: 0, max: 100,
          axisLabel: {fontSize: 10, color: P.axisLabel, formatter: (v: number) => v + '%'},
          axisLine: {show: false}, axisTick: {show: false},
          splitLine: {lineStyle: {color: P.splitLine, type: 'dashed'}},
        },
      },
    );
    // Available capacity (weekly avg) and peak demand (weekly max), MW, YoY.
    const capacityYoy = weeklyYoyOption(
      data.capacityByYear, data.eafWeeks, {curColor: '#2e9e4f', unit: 'MW'}, P, months);
    const peakDemandYoy = weeklyYoyOption(
      data.peakDemandByYear, data.eafWeeks, {curColor: '#d9534f', unit: 'MW'}, P, months);
    const genYoy = monthlyYoyOption(data.genByYear, {curColor: '#1976d2'}, P, months);
    const demandYoy = monthlyYoyOption(data.demandByYear, {curColor: '#d32f2f'}, P, months);

    const genDemand = ts(
      [
        {...LINE_BASE, name: 'Available Capacity (daily avg)', data: withGapNulls(data.availableCapacityAvg), connectNulls: false, lineStyle: {width: 1.6, color: '#43a047'}, itemStyle: {color: '#43a047'}},
        {...LINE_BASE, name: 'Generation (daily avg)', data: data.genAvg, lineStyle: {width: 1.6, color: '#1976d2'}, itemStyle: {color: '#1976d2'}},
        {...LINE_BASE, name: 'Demand (daily avg)', data: data.demandAvg, lineStyle: {width: 1.6, color: '#d32f2f'}, itemStyle: {color: '#d32f2f'}},
        {...LINE_BASE, name: 'Demand (daily peak, dashed)', data: data.demandMax, lineStyle: {width: 1, color: '#d32f2f', type: 'dashed'}, itemStyle: {color: '#d32f2f'}},
        {...LINE_BASE, name: 'Headroom (capacity − demand)', data: withGapNulls(data.headroomAvg), connectNulls: false, lineStyle: {width: 1.4, color: '#ab47bc'}, itemStyle: {color: '#ab47bc'}},
      ],
      {});

    const trade = ts(
      [
        {...LINE_BASE, name: 'Imports', data: data.importsAvg, lineStyle: {width: 1.4, color: '#26a69a'}, areaStyle: {color: '#26a69a', opacity: 0.12}, itemStyle: {color: '#26a69a'}},
        {...LINE_BASE, name: 'Exports', data: data.exportsAvg, lineStyle: {width: 1.4, color: '#ef6c00'}, areaStyle: {color: '#ef6c00', opacity: 0.12}, itemStyle: {color: '#ef6c00'}},
      ],
      {});

    return {clf, iosChart, mlrChart, ilsChart, totalReductionChart, pumpedStorage, eafYoy, outagesYoy, stationHourly, eafOutageHourly, capacityYoy, peakDemandYoy, genYoy, demandYoy, renewables, rooftopPv, rooftopPvPerHh, thermal, nuclear, ocgt, ocgtHourly, genDemand, uclfOclfYoy, trade};
  }, [data, P, rooftopColorByProv, isMobile]);

  if (err) return <div className={styles.loading}>Failed to load data: {err}</div>;
  if (!data || !charts) return <div className={styles.loading}>Loading…</div>;

  // Desktop grid order: first four = row 1 (cols 2–5), last four = row 2.
  // Mobile: chunked into 2×2 carousel pages, four per page.
  const stats: Array<{label: string; value: string; units: string}> = [
    {label: 'Coal', value: fmt(lastVal(data.thermalAvg)), units: 'MW'},
    {
      label: 'Renewables',
      value: fmt(
        (lastVal(data.windAvg) ?? 0) +
          (lastVal(data.pvAvg) ?? 0) +
          (lastVal(data.cspAvg) ?? 0) +
          (lastVal(data.otherReAvg) ?? 0),
      ),
      units: 'MW',
    },
    {label: 'Total Generation', value: fmt(data.latestGen), units: 'MW'},
    {label: 'Planned (PCLF)', value: fmt1(lastVal(data.pclfAvg)) + '%', units: 'of fleet'},
    {label: 'Nuclear', value: fmt(lastVal(data.nuclearAvg)), units: 'MW'},
    {
      label: 'OCGT',
      value: fmt((lastVal(data.ocgtEskomMax) ?? 0) + (lastVal(data.ocgtIppMax) ?? 0)),
      units: 'MW · peak',
    },
    {label: 'Total Demand', value: fmt(data.latestDemand), units: 'MW'},
    {label: 'Unplanned (UCLF)', value: fmt1(lastVal(data.uclfAvg)) + '%', units: 'of fleet'},
  ];
  const statPages: Array<typeof stats> = [];
  for (let i = 0; i < stats.length; i += 4) statPages.push(stats.slice(i, i + 4));

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1>Eskom Generation Dashboard</h1>
        <p>Latest reading: {displayTs}</p>
      </header>

      <div className={styles.topGrid}>
        <div className={clsx(styles.card, styles.gaugeCard)}>
          <div className={styles.gaugeMeta}>
            <div className={styles.gaugeLabel}>Energy Availability Factor</div>
          </div>
          <div style={{flex: 1, minHeight: 180, display: 'flex'}}>
            <Gauge value={data.latestEaf} />
          </div>
          {data.latestEafLabel && (
            <div className={styles.gaugePeriod}>{data.latestEafLabel}</div>
          )}
        </div>

        <div className={styles.statPages} ref={statPagesRef} onScroll={onStatScroll}>
          {statPages.map((page, p) => (
            <div key={p} className={styles.statPage}>
              {page.map((s) => (
                <div key={s.label} className={clsx(styles.card, styles.statCard)}>
                  <div className={styles.statLabel}>{s.label}</div>
                  <div className={styles.statValue}>{s.value}</div>
                  <div className={styles.statUnits}>{s.units}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className={styles.dots}>
        {statPages.map((_, i) => (
          <button
            key={i}
            type="button"
            className={clsx(styles.dot, i === statPage && styles.dotActive)}
            aria-label={`Stats page ${i + 1}`}
            onClick={() => scrollToStatPage(i)}
          />
        ))}
      </div>
      <div className={styles.asOf}>
        All values are the most recent day&rsquo;s average
        {data.latestEafLabel ? ' · ' + data.latestEafLabel.replace(/^daily avg /, '') : ''}
      </div>

      <div className={styles.chartPair}>
        <ChartCard title="Weekly EAF by year" option={charts.eafYoy} />
        <ChartCard title="Outages: planned / unplanned / other (7-day avg %)" option={charts.outagesYoy} />
      </div>
      <div className={styles.chartPair}>
        <ChartCard title="Station build-up — hourly generation mix (last 3 months)" option={charts.stationHourly} />
        <ChartCard title="EAF &amp; outages — hourly (last 3 months)" option={charts.eafOutageHourly} />
      </div>

      <h2 className={styles.sectionTitle}>Generation</h2>
      <div className={styles.chartPair}>
        <ChartCard title="Coal (min / avg / max)" option={charts.thermal} />
        <ChartCard title="Nuclear (hourly avg)" option={charts.nuclear} />
      </div>
      <div className={styles.chartGrid}>
        <ChartCard title="Renewables (hourly avg)" option={charts.renewables} />
        <ChartCard
          title="Generation, Demand & Available Capacity (daily avg, peak demand dashed)"
          option={charts.genDemand}
        />
      </div>
      <div className={styles.chartPair}>
        <ChartCard title="Available capacity by year (weekly avg)" option={charts.capacityYoy} />
        <ChartCard title="Peak demand by year (weekly peak)" option={charts.peakDemandYoy} />
      </div>
      <div className={styles.chartPair}>
        <ChartCard title="Monthly generation by year (avg MW)" option={charts.genYoy} />
        <ChartCard title="Monthly demand by year (avg MW)" option={charts.demandYoy} />
      </div>
      <div className={styles.chartGrid}>
        <ChartCard title="International Trade" option={charts.trade} />
      </div>

      <h2 className={styles.sectionTitle}>Peaking generation</h2>
      <div className={styles.chartGrid}>
        <ChartCard
          title="OCGT (Eskom + IPP peak, combined daily average)"
          option={charts.ocgt}
        />
        <ChartCard
          title="OCGT hourly (Eskom + IPP, last 1 year in slider, default last 14 days)"
          option={charts.ocgtHourly}
        />
        <ChartCard title="Pumped storage (daily avg generation)" option={charts.pumpedStorage} />
      </div>

      <h2 className={styles.sectionTitle}>Outages</h2>
      <div className={styles.chartGrid}>
        <ChartCard title="Capability loss factors (MW)" option={charts.clf} />
        <ChartCard title="UCLF + OCLF (year over year)" option={charts.uclfOclfYoy} />
      </div>

      <h2 className={styles.sectionTitle}>Demand reduction</h2>
      <div className={styles.chartPair}>
        <ChartCard title="Total load reduction (daily avg)" option={charts.totalReductionChart} />
        <ChartCard title="IOS — excl. ILS & MLR (daily avg)" option={charts.iosChart} />
      </div>
      <div className={styles.chartPair}>
        <ChartCard title="MLR — manual load reduction (daily avg)" option={charts.mlrChart} />
        <ChartCard title="ILS — interruptible load (daily avg)" option={charts.ilsChart} />
      </div>

      <h2 className={styles.sectionTitle}>Solar</h2>
      <div className={styles.chartPair}>
        <ChartCard title="Rooftop PV (installed MW by province)" option={charts.rooftopPv} />
        <ChartCard title="Rooftop PV (W per household)" option={charts.rooftopPvPerHh} />
      </div>

      <details className={clsx(styles.card, styles.provenance)}>
        <summary>Data sources</summary>
        <table>
          <thead>
            <tr>
              <th>Chart</th>
              <th>Staging columns</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.chartSources).map(([cid, refs]) => (
              <tr key={cid}>
                <td><code>{cid}</code></td>
                <td>
                  {refs.map((r, i) => (
                    <div key={i}><code>{r}</code></div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
