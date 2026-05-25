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
  opts: {unit?: string; decimals?: number; yAxis?: any; hourly?: boolean; isMobile?: boolean} = {},
  P: Palette,
) {
  const unit = opts.unit ?? 'MW';
  const decimals = opts.decimals ?? 0;
  const yAxis = opts.yAxis;
  const hourly = !!opts.hourly;
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
    const header = d
      ? d.getUTCFullYear() +
        '-' +
        String(d.getUTCMonth() + 1).padStart(2, '0') +
        '-' +
        String(d.getUTCDate()).padStart(2, '0') +
        (hourly
          ? ' ' +
            String(d.getUTCHours()).padStart(2, '0') +
            ':00 UTC'
          : '')
      : params[0].axisValueLabel;
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
    grid: {top: 50, right: yAxis ? 64 : 18, bottom: isMobile ? 90 : 70, left: 56},
    xAxis: {
      type: 'time',
      axisLabel: {
        fontSize: 10,
        color: P.axisLabel,
        hideOverlap: true,
        margin: 10,
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
        start: 75,
        end: 100,
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
    ],
    series,
  };
}

export function eafGaugeOption(value: number | null, P: Palette) {
  return {
    backgroundColor: 'transparent',
    series: [
      {
        type: 'gauge',
        progress: {show: true, width: 18},
        axisLine: {lineStyle: {width: 18}},
        axisTick: {show: false},
        splitLine: {length: 15, lineStyle: {width: 2, color: '#999'}},
        axisLabel: {distance: 25, color: '#999', fontSize: 12},
        anchor: {
          show: true,
          showAbove: true,
          size: 25,
          itemStyle: {borderWidth: 10},
        },
        title: {show: false},
        detail: {
          valueAnimation: true,
          fontSize: 36,
          offsetCenter: [0, '70%'],
          color: P.tooltipText,
          formatter: (v: number) => String(Math.round(v)),
        },
        data: [{value: value ?? 0}],
      },
    ],
  };
}
