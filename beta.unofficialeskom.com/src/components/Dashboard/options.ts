export type Palette = {
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
  legend: string;
  axisLabel: string;
  axisLine: string;
  splitLine: string;
  dzBorder: string;
  dzText: string;
  dzHandle: string;
  dzBorderH: string;
  dzFill: string;
};

export const PALETTES: {dark: Palette; light: Palette} = {
  dark: {
    tooltipBg: '#1a1a2e',
    tooltipBorder: '#3a3a4a',
    tooltipText: '#e6e6ed',
    legend: '#b8bcd0',
    axisLabel: '#aaa',
    axisLine: '#3a3a4a',
    splitLine: '#2a2a3a',
    dzBorder: '#3a3a4a',
    dzText: '#aaa',
    dzHandle: '#1e1e2e',
    dzBorderH: '#7cb2e8',
    dzFill: 'rgba(124,178,232,0.22)',
  },
  light: {
    tooltipBg: '#ffffff',
    tooltipBorder: '#e0e0e0',
    tooltipText: '#333333',
    legend: '#666666',
    axisLabel: '#888888',
    axisLine: '#e0e0e0',
    splitLine: '#f0f0f0',
    dzBorder: '#e0e0e0',
    dzText: '#888888',
    dzHandle: '#ffffff',
    dzBorderH: '#1f77b4',
    dzFill: 'rgba(31,119,180,0.18)',
  },
};

const DAY_MS = 86_400_000;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Deterministic, calendar-aligned x-axis tick positions for a [start, end]
// window (ms, UTC). ECharts' native time scale mixes month-boundary ticks with
// its own day-level fill, which produces uneven runs like "May 6 8 15 22" —
// third time this axis has regressed, so we now place ticks ourselves via
// axisLabel.customValues and never let the auto-picker run. All ticks sit on
// UTC midnights / month starts, matching the tooltip's UTC dates.
export function calendarTicks(start: number, end: number): number[] {
  const days = (end - start) / DAY_MS;
  const ticks: number[] = [];
  if (days <= 14) {
    // Daily ticks.
    const d = new Date(start);
    const t0 = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
    for (let t = t0; t <= end; t += DAY_MS) if (t >= start) ticks.push(t);
    return ticks;
  }
  // Fixed day-of-month anchors: even spacing that stays month-aligned. Wider
  // windows drop to month starts only, then every Nth month.
  const anchors = days <= 35 ? [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]
    : days <= 100 ? [1, 8, 15, 22]
    : days <= 200 ? [1, 15]
    : [1];
  const monthStep = days <= 740 ? 1 : days <= 1600 ? 3 : days <= 3200 ? 6 : 12;
  const s = new Date(start);
  const m = new Date(Date.UTC(s.getUTCFullYear(), s.getUTCMonth(), 1));
  for (; m.getTime() <= end; m.setUTCMonth(m.getUTCMonth() + 1)) {
    if (days > 200 && m.getUTCMonth() % monthStep !== 0) continue;
    for (const a of anchors) {
      const t = Date.UTC(m.getUTCFullYear(), m.getUTCMonth(), a);
      if (t >= start && t <= end) ticks.push(t);
    }
  }
  return ticks;
}

// Label for a calendarTicks() value: month name on the 1st (year on Jan 1),
// plain day-of-month otherwise. UTC, matching the tick positions.
export function calendarTickLabel(value: number): string {
  const d = new Date(value);
  if (d.getUTCDate() === 1) {
    return d.getUTCMonth() === 0 ? String(d.getUTCFullYear()) : MONTHS[d.getUTCMonth()];
  }
  return String(d.getUTCDate());
}

type SeriesItem = {
  name: string;
  data: Array<[number, number | null]> | Array<number | null>;
  decimals?: number;
  unit?: string;
  [k: string]: unknown;
};

export function timeSeriesOption(
  series: SeriesItem[],
  opts: {unit?: string; decimals?: number; yAxis?: any; hourly?: boolean; monthly?: boolean; isMobile?: boolean; zoomStart?: number} = {},
  P: Palette,
) {
  const unit = opts.unit ?? 'MW';
  const decimals = opts.decimals ?? 0;
  const yAxis = opts.yAxis;
  const hourly = !!opts.hourly;
  const monthly = !!opts.monthly;
  const isMobile = !!opts.isMobile;
  // Default the zoom window to the last 30 days (= the "1M" preset) for the
  // daily/hourly charts, by value off the newest timestamp across all series.
  // Skip for monthly charts (Long-term page) — 30 days there is ~1 point, so
  // those keep the percent-based default (opts.zoomStart, usually full history).
  let _maxTs = -Infinity;
  let _minTs = Infinity;
  for (const s of series) {
    const d = (s as any).data;
    const last = Array.isArray(d) && d.length ? d[d.length - 1] : null;
    const first = Array.isArray(d) && d.length ? d[0] : null;
    const tl = Array.isArray(last) ? last[0] : null;
    const tf = Array.isArray(first) ? first[0] : null;
    if (typeof tl === 'number' && tl > _maxTs) _maxTs = tl;
    if (typeof tf === 'number' && tf < _minTs) _minTs = tf;
  }
  const _use1M = !monthly && isFinite(_maxTs);
  // Ticks for the initial zoom window (1M for daily/hourly charts, full
  // history for monthly). ChartCard recomputes these on every dataZoom.
  const _tickWin: [number, number] | null =
    _use1M ? [_maxTs - 30 * DAY_MS, _maxTs]
    : isFinite(_minTs) && isFinite(_maxTs) ? [_minTs, _maxTs]
    : null;
  const fmtTooltip = (params: any[]) => {
    if (!params || !params.length) return '';
    const lines = params.map((p) => {
      const s = series[p.seriesIndex] || ({} as SeriesItem);
      const d = s.decimals != null ? s.decimals : decimals;
      const u = s.unit || unit;
      const val =
        p.value && p.value[1] != null
          ? Number(p.value[1]).toLocaleString('en-ZA', {
              minimumFractionDigits: d,
              maximumFractionDigits: d,
            }) +
            ' ' +
            u
          : '-';
      return p.marker + ' ' + p.seriesName + ': <b>' + val + '</b>';
    });
    const ts = params[0].value && params[0].value[0];
    const d = ts != null ? new Date(ts) : null;
    const ymd =
      d &&
      d.getUTCFullYear() +
        '-' +
        String(d.getUTCMonth() + 1).padStart(2, '0') +
        // Monthly points represent the whole month — drop the day to avoid
        // implying it's the 1st.
        (monthly
          ? ''
          : '-' +
            String(d.getUTCDate()).padStart(2, '0') +
            (hourly ? ' ' + String(d.getUTCHours()).padStart(2, '0') + ':00 UTC' : ''));
    const header = d ? ymd : params[0].axisValueLabel;
    return (
      '<div style="font-weight:600;margin-bottom:4px">' +
      header +
      '</div>' +
      lines.join('<br/>')
    );
  };
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: P.tooltipBg,
      borderColor: P.tooltipBorder,
      borderWidth: 1,
      textStyle: {color: P.tooltipText, fontSize: 12},
      formatter: fmtTooltip,
    },
    legend: {
      type: 'scroll',
      show: true,
      data: series.map((s) => s.name),
      top: 0,
      left: 'center',
      selectedMode: true,
      icon: 'rect',
      itemWidth: 14,
      itemHeight: 10,
      itemGap: 18,
      textStyle: {fontSize: 11, color: P.legend},
    },
    grid: {top: 50, right: 18, bottom: isMobile ? 90 : 70, left: 56},
    xAxis: {
      type: 'time',
      // Deterministic calendar-aligned labels via customValues — see
      // calendarTicks(). Do NOT go back to the native auto-picker (object
      // formatter / minInterval): both were tried and both produce uneven or
      // duplicated labels. ChartCard's dataZoom handler keeps customValues in
      // sync with the visible window.
      axisLabel: {
        fontSize: 10,
        color: P.axisLabel,
        hideOverlap: true,
        margin: 10,
        formatter: (value: number) => calendarTickLabel(value),
        ...(_tickWin ? {customValues: calendarTicks(_tickWin[0], _tickWin[1])} : {}),
      },
      axisLine: {lineStyle: {color: P.axisLine}},
      axisTick: {show: false},
      splitLine: {show: false},
    },
    yAxis: yAxis || {
      type: 'value',
      axisLabel: {
        fontSize: 10,
        color: P.axisLabel,
        formatter: (v: number) => v.toLocaleString('en-ZA'),
      },
      axisLine: {show: false},
      axisTick: {show: false},
      splitLine: {lineStyle: {color: P.splitLine, type: 'dashed'}},
    },
    dataZoom: [
      {
        type: 'slider',
        // Daily/hourly charts open on the last 30 days (= 1M preset), by value.
        // Monthly charts fall back to the percent-based zoomStart (full history).
        ...(_use1M
          ? {startValue: _maxTs - 30 * 86_400_000, endValue: _maxTs}
          : {start: opts.zoomStart ?? 75, end: 100}),
        // The slider always spans the full history, so on a phone one pixel of
        // handle travel is ~a week — a small window is impossible to grab.
        // Don't let the handles collapse past a day; fine selection comes from
        // the range preset buttons instead.
        minValueSpan: 24 * 3600 * 1000,
        bottom: isMobile ? 14 : 8,
        height: isMobile ? 44 : 30,
        throttle: 0,
        borderColor: P.dzBorder,
        fillerColor: P.dzFill,
        handleSize: isMobile ? '120%' : '130%',
        handleStyle: {
          color: P.dzHandle,
          borderColor: P.dzBorderH,
          borderWidth: isMobile ? 2 : 1.5,
        },
        moveHandleSize: isMobile ? 20 : 12,
        textStyle: {color: P.dzText, fontSize: isMobile ? 12 : 11},
        brushSelect: false,
      },
      // No 'inside' zoom on purpose: it captures touch/scroll gestures per
      // graph, which makes scrolling the page past a chart infuriating. Fine
      // ranges come from the preset buttons + the slider's day-level minimum.
    ],
    series,
  };
}
