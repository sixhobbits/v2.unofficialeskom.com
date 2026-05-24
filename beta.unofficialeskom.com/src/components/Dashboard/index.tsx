import {useEffect, useMemo, useState} from 'react';
import type {ReactNode} from 'react';
import ReactECharts from 'echarts-for-react';
import {useColorMode} from '@docusaurus/theme-common';
import useBaseUrl from '@docusaurus/useBaseUrl';
import clsx from 'clsx';

import {PALETTES, timeSeriesOption, eafGaugeOption, type Palette} from './options';
import styles from './styles.module.css';

type Point = [number, number | null];

type DashboardData = {
  latestTs: number | null;
  thermalMin: Point[];
  thermalAvg: Point[];
  thermalMax: Point[];
  nuclearAvg: Point[];
  ocgtEskomMax: Point[];
  ocgtIppMax: Point[];
  ocgtTotalAvg: Point[];
  ocgtEskomHourly: Point[];
  ocgtIppHourly: Point[];
  genAvg: Point[];
  genMax: Point[];
  demandAvg: Point[];
  demandMax: Point[];
  availableCapacityAvg: Point[];
  headroomAvg: Point[];
  eafAvg: Point[];
  pclfAvg: Point[];
  uclfAvg: Point[];
  oclfAvg: Point[];
  importsAvg: Point[];
  exportsAvg: Point[];
  latestGen: number;
  latestDemand: number;
  latestEaf: number | null;
  latestEafLabel: string;
  windAvg: Point[];
  pvAvg: Point[];
  cspAvg: Point[];
  otherReAvg: Point[];
  uclfOclfXKeys: string[];
  uclfOclfByYear: Record<string, Array<number | null>>;
  rooftopProvinces: string[];
  rooftopSeries: Record<string, Point[]>;
  rooftopProvincesPerHh: string[];
  rooftopSeriesPerHh: Record<string, Point[]>;
  chartSources: Record<string, string[]>;
};

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

function ChartCard({title, option}: {title: string; option: any}) {
  return (
    <div className={styles.card}>
      <div className={styles.chartTitle}>{title}</div>
      <ReactECharts
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

// ISO-week label "YYYY-Wnn" for a Date (UTC).
function isoWeekKey(d: Date): {key: string; week: number; year: number} {
  // Copy date, set to nearest Thursday: current date + 4 - current day number
  // (where Mon=1 .. Sun=7). Per ISO-8601.
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dayNum = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((+t - +yearStart) / 86400000 + 1) / 7);
  return {
    key: `${t.getUTCFullYear()}-W${String(week).padStart(2, '0')}`,
    week,
    year: t.getUTCFullYear(),
  };
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

function weeklyAvg(daily: Array<[number, number | null]>): Array<{key: string; week: number; avg: number}> {
  const buckets = new Map<string, {week: number; vals: number[]}>();
  for (const [ts, v] of daily) {
    if (v == null) continue;
    const {key, week} = isoWeekKey(new Date(ts));
    const b = buckets.get(key);
    if (b) b.vals.push(v);
    else buckets.set(key, {week, vals: [v]});
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([key, {week, vals}]) => ({
      key,
      week,
      avg: vals.reduce((s, v) => s + v, 0) / vals.length,
    }));
}

export default function Dashboard(): ReactNode {
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
      .then((json) => !cancelled && setData(json))
      .catch((e) => !cancelled && setErr(String(e)));
    return () => {
      cancelled = true;
    };
  }, [dataUrl]);

  const displayTs = useMemo(() => {
    if (!data?.latestTs) return 'Unknown';
    return new Date(data.latestTs).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
  }, [data?.latestTs]);

  const rooftopColorByProv = useMemo(() => {
    const map: Record<string, string> = {};
    (data?.rooftopProvinces || []).forEach((prov, i) => {
      map[prov] = ROOFTOP_PALETTE[i % ROOFTOP_PALETTE.length];
    });
    return map;
  }, [data?.rooftopProvinces]);

  const charts = useMemo(() => {
    if (!data) return null;

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const outageStack = timeSeriesOption(
      [
        {...AREA_STACK, name: 'EAF (available)', data: data.eafAvg, itemStyle: {color: '#43a047'}, areaStyle: {color: '#43a047', opacity: 0.85}},
        {...AREA_STACK, name: 'PCLF (planned)', data: data.pclfAvg, itemStyle: {color: '#1976d2'}, areaStyle: {color: '#1976d2', opacity: 0.85}},
        {...AREA_STACK, name: 'UCLF (unplanned)', data: data.uclfAvg, itemStyle: {color: '#d32f2f'}, areaStyle: {color: '#d32f2f', opacity: 0.85}},
        {...AREA_STACK, name: 'OCLF (other)', data: data.oclfAvg, itemStyle: {color: '#9e9e9e'}, areaStyle: {color: '#9e9e9e', opacity: 0.85}},
      ],
      {
        unit: '%',
        decimals: 1,
        yAxis: {
          type: 'value',
          min: 50,
          max: 100,
          axisLabel: {fontSize: 10, color: P.axisLabel, formatter: (v: number) => v + '%'},
          axisLine: {show: false},
          axisTick: {show: false},
          splitLine: {lineStyle: {color: P.splitLine, type: 'dashed'}},
        },
      },
      P,
    );

    const renewables = timeSeriesOption(
      [
        {...LINE_BASE, name: 'Wind', data: data.windAvg, lineStyle: {width: 1.4, color: '#26c6da'}, itemStyle: {color: '#26c6da'}},
        {...LINE_BASE, name: 'PV', data: data.pvAvg, lineStyle: {width: 1.4, color: '#fdd835'}, itemStyle: {color: '#fdd835'}},
        {...LINE_BASE, name: 'CSP', data: data.cspAvg, lineStyle: {width: 1.4, color: '#ef6c00'}, itemStyle: {color: '#ef6c00'}},
        {...LINE_BASE, name: 'Other RE', data: data.otherReAvg, lineStyle: {width: 1.4, color: '#9ccc65'}, itemStyle: {color: '#9ccc65'}},
      ],
      {},
      P,
    );

    const rooftopPv = timeSeriesOption(
      (data.rooftopProvinces || []).map((prov) => ({
        type: 'line', stack: 'rooftop', name: prov, data: data.rooftopSeries[prov] || [],
        showSymbol: false, animation: false, smooth: false, step: 'end',
        lineStyle: {width: 0}, areaStyle: {color: rooftopColorByProv[prov], opacity: 0.85},
        itemStyle: {color: rooftopColorByProv[prov]},
      })),
      {unit: 'MW', decimals: 1},
      P,
    );

    const rooftopPvPerHh = timeSeriesOption(
      (data.rooftopProvincesPerHh || []).map((prov) => ({
        type: 'line', stack: 'rooftop_per_hh', name: prov, data: data.rooftopSeriesPerHh[prov] || [],
        showSymbol: false, animation: false, smooth: false, step: 'end',
        lineStyle: {width: 0}, areaStyle: {color: rooftopColorByProv[prov], opacity: 0.85},
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
      },
      P,
    );

    const thermal = timeSeriesOption(
      [
        {...LINE_BASE, name: 'Min (dashed)', data: data.thermalMin, lineStyle: {width: 1, color: '#ffab91', type: 'dashed'}, itemStyle: {color: '#ffab91'}},
        {...LINE_BASE, name: 'Average', data: data.thermalAvg, lineStyle: {width: 1.8, color: '#ff7043'}, itemStyle: {color: '#ff7043'}},
        {...LINE_BASE, name: 'Max (dashed)', data: data.thermalMax, lineStyle: {width: 1, color: '#bf360c', type: 'dashed'}, itemStyle: {color: '#bf360c'}},
      ],
      {},
      P,
    );

    const nuclear = timeSeriesOption(
      [{...LINE_BASE, name: 'Average', data: data.nuclearAvg, lineStyle: {width: 1.6, color: '#ab47bc'}, areaStyle: {color: '#ab47bc', opacity: 0.15}, itemStyle: {color: '#ab47bc'}}],
      {},
      P,
    );

    const ocgt = timeSeriesOption(
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
      {},
      P,
    );

    // Default the dataZoom window to roughly the last 14 days of the
    // ~1-year hourly window we publish.
    const hourlyDefaultStart =
      data.ocgtEskomHourly.length > 0
        ? Math.max(0, ((data.ocgtEskomHourly.length - 14 * 24) / data.ocgtEskomHourly.length) * 100)
        : 0;
    const ocgtRolling7d = rollingSumAvg(data.ocgtEskomHourly, data.ocgtIppHourly);
    const ocgtHourly = timeSeriesOption(
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
      {hourly: true},
      P,
    );
    // Override the default dataZoom (which times the visible window to the
    // last 25% via start:75) so the hourly chart opens on the last ~14d.
    (ocgtHourly as any).dataZoom = [
      {
        type: 'slider',
        start: hourlyDefaultStart,
        end: 100,
        bottom: 8,
        height: 22,
        throttle: 0,
        borderColor: P.dzBorder,
        fillerColor: P.dzFill,
        handleSize: '110%',
        handleStyle: {color: P.dzHandle, borderColor: P.dzBorderH, borderWidth: 1.5},
        moveHandleSize: 6,
        textStyle: {color: P.dzText, fontSize: 10},
        brushSelect: false,
      },
    ];

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

    const weeks = weeklyAvg(data.eafAvg);
    // Drop trailing incomplete week so we don't compare a partial week
    // against a full one in the rolled-forward comparison.
    const completeWeeks = weeks.slice(0, weeks.length - 1);
    const cur52 = completeWeeks.slice(-52);
    const prev52 = completeWeeks.slice(-104, -52);
    const eafYoy = {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: P.tooltipBg,
        borderColor: P.tooltipBorder,
        borderWidth: 1,
        textStyle: {color: P.tooltipText, fontSize: 12},
        formatter: (params: any[]) => {
          const idx = params[0].dataIndex;
          const curWk = cur52[idx]?.key ?? '';
          const prvWk = prev52[idx]?.key ?? '';
          const lines = params.map((p: any) => {
            const wk = p.seriesName.startsWith('Current') ? curWk : prvWk;
            return p.marker + ' ' + wk + ': <b>' + (p.value != null ? Number(p.value).toFixed(1) + '%' : '–') + '</b>';
          });
          return lines.join('<br/>');
        },
      },
      legend: {
        data: ['Current 52 weeks', 'Previous 52 weeks (dashed)'],
        top: 0,
        left: 'center',
        selectedMode: true,
        icon: 'rect',
        itemWidth: 14,
        itemHeight: 10,
        itemGap: 18,
        textStyle: {fontSize: 11, color: P.legend},
      },
      grid: {top: 50, right: 18, bottom: 40, left: 56},
      xAxis: {
        type: 'category',
        data: cur52.map((w) => 'W' + String(w.week).padStart(2, '0')),
        boundaryGap: false,
        axisLabel: {
          interval: (i: number, v: string) => v === 'W01' || i === cur52.length - 1 || i % 8 === 0,
          fontSize: 10,
          color: P.axisLabel,
        },
        axisTick: {show: false},
        axisLine: {lineStyle: {color: P.axisLine}},
        splitLine: {show: false},
      },
      yAxis: {
        type: 'value',
        min: 50,
        max: 100,
        axisLabel: {fontSize: 10, color: P.axisLabel, formatter: (v: number) => v + '%'},
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {lineStyle: {color: P.splitLine, type: 'dashed'}},
      },
      series: [
        {
          name: 'Previous 52 weeks (dashed)',
          type: 'line',
          data: prev52.map((w) => w.avg),
          symbol: 'none',
          showSymbol: false,
          animation: false,
          lineStyle: {width: 1.5, color: '#90a4ae', type: 'dashed'},
          itemStyle: {color: '#90a4ae'},
        },
        {
          name: 'Current 52 weeks',
          type: 'line',
          data: cur52.map((w) => w.avg),
          symbol: 'none',
          showSymbol: false,
          animation: false,
          lineStyle: {width: 2.2, color: '#43a047'},
          itemStyle: {color: '#43a047'},
        },
      ],
    };

    const genDemand = timeSeriesOption(
      [
        {...LINE_BASE, name: 'Available Capacity (daily avg)', data: withGapNulls(data.availableCapacityAvg), connectNulls: false, lineStyle: {width: 1.6, color: '#43a047'}, itemStyle: {color: '#43a047'}},
        {...LINE_BASE, name: 'Generation (daily avg)', data: data.genAvg, lineStyle: {width: 1.6, color: '#1976d2'}, itemStyle: {color: '#1976d2'}},
        {...LINE_BASE, name: 'Demand (daily avg)', data: data.demandAvg, lineStyle: {width: 1.6, color: '#d32f2f'}, itemStyle: {color: '#d32f2f'}},
        {...LINE_BASE, name: 'Demand (daily peak, dashed)', data: data.demandMax, lineStyle: {width: 1, color: '#d32f2f', type: 'dashed'}, itemStyle: {color: '#d32f2f'}},
        {...LINE_BASE, name: 'Headroom (capacity − demand)', data: withGapNulls(data.headroomAvg), connectNulls: false, lineStyle: {width: 1.4, color: '#ab47bc'}, itemStyle: {color: '#ab47bc'}},
      ],
      {},
      P,
    );

    const trade = timeSeriesOption(
      [
        {...LINE_BASE, name: 'Imports', data: data.importsAvg, lineStyle: {width: 1.4, color: '#26a69a'}, areaStyle: {color: '#26a69a', opacity: 0.12}, itemStyle: {color: '#26a69a'}},
        {...LINE_BASE, name: 'Exports', data: data.exportsAvg, lineStyle: {width: 1.4, color: '#ef6c00'}, areaStyle: {color: '#ef6c00', opacity: 0.12}, itemStyle: {color: '#ef6c00'}},
      ],
      {},
      P,
    );

    return {outageStack, eafYoy, renewables, rooftopPv, rooftopPvPerHh, thermal, nuclear, ocgt, ocgtHourly, genDemand, uclfOclfYoy, trade};
  }, [data, P, rooftopColorByProv]);

  if (err) return <div className={styles.loading}>Failed to load data: {err}</div>;
  if (!data || !charts) return <div className={styles.loading}>Loading…</div>;

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
          <ReactECharts
            option={eafGaugeOption(data.latestEaf, P)}
            notMerge
            lazyUpdate
            style={{height: 140, width: '100%', flex: 1}}
            opts={{renderer: 'canvas'}}
          />
        </div>

        {/* Row 1: col2..col5 */}
        <div className={clsx(styles.card, styles.statCard)}>
          <div className={styles.statLabel}>Coal</div>
          <div className={styles.statValue}>{fmt(lastVal(data.thermalAvg))}</div>
          <div className={styles.statUnits}>MW</div>
        </div>
        <div className={clsx(styles.card, styles.statCard)}>
          <div className={styles.statLabel}>Renewables</div>
          <div className={styles.statValue}>
            {fmt(
              (lastVal(data.windAvg) ?? 0) +
                (lastVal(data.pvAvg) ?? 0) +
                (lastVal(data.cspAvg) ?? 0) +
                (lastVal(data.otherReAvg) ?? 0),
            )}
          </div>
          <div className={styles.statUnits}>MW</div>
        </div>
        <div className={clsx(styles.card, styles.statCard)}>
          <div className={styles.statLabel}>Total Generation</div>
          <div className={styles.statValue}>{fmt(data.latestGen)}</div>
          <div className={styles.statUnits}>MW</div>
        </div>
        <div className={clsx(styles.card, styles.statCard)}>
          <div className={styles.statLabel}>Planned (PCLF)</div>
          <div className={styles.statValue}>{fmt1(lastVal(data.pclfAvg))}%</div>
          <div className={styles.statUnits}>of fleet</div>
        </div>

        {/* Row 2: col2..col5 */}
        <div className={clsx(styles.card, styles.statCard)}>
          <div className={styles.statLabel}>Nuclear</div>
          <div className={styles.statValue}>{fmt(lastVal(data.nuclearAvg))}</div>
          <div className={styles.statUnits}>MW</div>
        </div>
        <div className={clsx(styles.card, styles.statCard)}>
          <div className={styles.statLabel}>OCGT</div>
          <div className={styles.statValue}>
            {fmt((lastVal(data.ocgtEskomMax) ?? 0) + (lastVal(data.ocgtIppMax) ?? 0))}
          </div>
          <div className={styles.statUnits}>MW · peak</div>
        </div>
        <div className={clsx(styles.card, styles.statCard)}>
          <div className={styles.statLabel}>Total Demand</div>
          <div className={styles.statValue}>{fmt(data.latestDemand)}</div>
          <div className={styles.statUnits}>MW</div>
        </div>
        <div className={clsx(styles.card, styles.statCard)}>
          <div className={styles.statLabel}>Unplanned (UCLF)</div>
          <div className={styles.statValue}>{fmt1(lastVal(data.uclfAvg))}%</div>
          <div className={styles.statUnits}>of fleet</div>
        </div>
      </div>
      <div className={styles.asOf}>
        All values are the most recent day&rsquo;s average
        {data.latestEafLabel ? ' · ' + data.latestEafLabel.replace(/^daily avg /, '') : ''}
      </div>

      <div className={styles.chartPair}>
        <ChartCard title="Outage Breakdown" option={charts.outageStack} />
        <ChartCard title="Weekly EAF (this year vs last)" option={charts.eafYoy} />
      </div>
      <div className={styles.chartPair}>
        <ChartCard title="Coal (min / avg / max)" option={charts.thermal} />
        <ChartCard title="Nuclear (hourly avg)" option={charts.nuclear} />
      </div>
      <div className={styles.chartGrid}>
        <ChartCard
          title="OCGT (Eskom + IPP peak, combined daily average)"
          option={charts.ocgt}
        />
        <ChartCard
          title="OCGT hourly (Eskom + IPP, last 1 year in slider, default last 14 days)"
          option={charts.ocgtHourly}
        />
        <ChartCard
          title="Generation, Demand & Available Capacity (daily avg, peak demand dashed)"
          option={charts.genDemand}
        />
        <ChartCard title="Renewables (hourly avg)" option={charts.renewables} />
        <ChartCard title="Rooftop PV (installed MW by province)" option={charts.rooftopPv} />
        <ChartCard title="Rooftop PV (W per household)" option={charts.rooftopPvPerHh} />
        <ChartCard title="UCLF + OCLF (year over year)" option={charts.uclfOclfYoy} />
        <ChartCard title="International Trade" option={charts.trade} />
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
