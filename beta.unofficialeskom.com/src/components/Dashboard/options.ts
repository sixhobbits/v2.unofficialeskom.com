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
      // Let ECharts' native time axis choose tick density and assign each tick a
      // level (year/month/day/hour); the object formatter then labels each tick
      // once by its own level. This adapts to zoom automatically — roughly a tick
      // per day when the window is short, per week/month as it widens — and shows
      // a month name exactly once (on its first-of-month tick) instead of the old
      // hand-rolled "day ≤ 7 → month" rule, which printed "Jun" for every tick
      // that happened to land in the first week and odd day numbers elsewhere.
      // hideOverlap drops any labels that would collide at month boundaries.
      axisLabel: {
        fontSize: 10,
        color: P.axisLabel,
        hideOverlap: true,
        margin: 10,
        formatter: {
          year: '{yyyy}',
          month: '{MMM}',
          day: '{d}',
          hour: '{HH}:{mm}',
          minute: '{HH}:{mm}',
        },
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
        // Default window opens on the last 25% of history; pass zoomStart to
        // open wider/narrower instead of mutating the returned option.
        start: opts.zoomStart ?? 75,
        end: 100,
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
