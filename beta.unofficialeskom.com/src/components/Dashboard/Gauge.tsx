import {useEffect, useRef} from 'react';
import * as echarts from 'echarts';
import {useColorMode} from '@docusaurus/theme-common';

// Speedometer-style dial, ported from agent-echarts/charts/dial.
//
// ECharts gauge font sizes are absolute px and ignore the radius, so a
// desktop-sized gauge overflows on a phone. We measure the container and
// rebuild the option with every size derived from a `_px` reference
// (= min(width,height), what the radius is relative to) on each resize —
// the same trick as the reference's mountDial().

type ZoneColor = 'good' | 'warn' | 'bad';
// [upTo, color] zones, ascending; the last upTo should equal `max`. Ordering
// encodes direction: green→red means higher is worse, red→green higher better.
type Zone = [number, ZoneColor];

type Props = {
  value: number | null;
  min?: number;
  max?: number;
  unit?: string;
  decimals?: number;
  zones?: Zone[];
};

// EAF default: below 50% red, 50–70% amber, 70%+ green.
const EAF_ZONES: Zone[] = [
  [50, 'bad'],
  [70, 'warn'],
  [100, 'good'],
];

// Teardrop needle path from the official ECharts gauge-speed example.
const NEEDLE =
  'path://M2090.36389,615.30999 L2090.36389,615.30999 C2091.48372,615.30999 2092.40383,616.194028 2092.44859,617.312956 L2096.90698,728.755929 C2097.05155,732.369577 2094.2393,735.416212 2090.62566,735.56078 C2090.53845,735.564269 2090.45117,735.566014 2090.36389,735.566014 L2090.36389,735.566014 C2086.74736,735.566014 2083.81557,732.63423 2083.81557,729.017692 C2083.81557,728.930412 2083.81732,728.84314 2083.82081,728.755929 L2088.2792,617.312956 C2088.32396,616.194028 2089.24407,615.30999 2090.36389,615.30999 Z';

type Tokens = {
  text: string;
  textMuted: string;
  tickMinor: string;
  tickMajor: string;
  hub: string;
  hubBorder: string;
  good: string;
  warn: string;
  bad: string;
};

const FONT =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

const TOKENS: {dark: Tokens; light: Tokens} = {
  dark: {
    text: '#e6e8eb',
    textMuted: '#8b94a3',
    tickMinor: 'rgba(255,255,255,0.25)',
    tickMajor: 'rgba(255,255,255,0.5)',
    hub: '#0e1116',
    hubBorder: 'rgba(255,255,255,0.55)',
    good: '#34d399',
    warn: '#fbbf24',
    bad: '#f87171',
  },
  light: {
    text: '#1f2933',
    textMuted: '#64748b',
    tickMinor: 'rgba(15,23,42,0.25)',
    tickMajor: 'rgba(15,23,42,0.45)',
    hub: '#ffffff',
    hubBorder: 'rgba(15,23,42,0.45)',
    good: '#16a34a',
    warn: '#d97706',
    bad: '#dc2626',
  },
};

function dialOption(
  value: number,
  min: number,
  max: number,
  unit: string,
  decimals: number,
  zones: Zone[],
  px: number,
  t: Tokens,
  animate: boolean,
) {
  const arcW = Math.max(6, Math.round(px * 0.07));
  const segments = zones.map(([upTo, color]) => [
    (upTo - min) / (max - min),
    t[color],
  ]);
  const fmtNum = (v: number) =>
    v.toLocaleString('en-ZA', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});

  return {
    backgroundColor: 'transparent',
    textStyle: {fontFamily: FONT},
    // The intro animation is driven by a value UPDATE (0 → value): ECharts
    // animates the gauge pointer on update, not on first render, so a single
    // setOption at the real value makes the needle jump. animationDurationUpdate
    // drives both the needle sweep and the counting number; rebuilds on
    // resize/theme pass animate:false so they snap instead of re-spinning.
    animation: animate,
    animationDuration: animate ? 1400 : 0,
    animationDurationUpdate: animate ? 1400 : 0,
    animationEasing: 'cubicOut',
    animationEasingUpdate: 'cubicOut',
    series: [
      {
        type: 'gauge',
        min,
        max,
        splitNumber: 5,
        startAngle: 215,
        endAngle: -35,
        center: ['50%', '52%'],
        radius: '92%',
        axisLine: {roundCap: false, lineStyle: {width: arcW, color: segments}},
        progress: {show: false},
        // Needle takes the colour of the zone it points at.
        pointer: {
          icon: NEEDLE,
          length: '58%',
          width: Math.max(4, Math.round(px * 0.026)),
          offsetCenter: [0, '6%'],
          itemStyle: {color: 'auto'},
        },
        anchor: {
          show: true,
          showAbove: true,
          size: Math.max(8, Math.round(px * 0.05)),
          itemStyle: {
            color: t.hub,
            borderColor: t.hubBorder,
            borderWidth: Math.max(2, Math.round(px * 0.01)),
          },
        },
        axisTick: {
          distance: -arcW,
          splitNumber: 4,
          length: Math.round(arcW * 0.4),
          lineStyle: {color: t.tickMinor, width: 1},
        },
        splitLine: {
          distance: -arcW,
          length: arcW,
          lineStyle: {color: t.tickMajor, width: 2},
        },
        axisLabel: {
          distance: Math.round(arcW + px * 0.025),
          color: t.textMuted,
          fontSize: Math.max(8, Math.round(px * 0.038)),
          // Drop the min/max labels at the bottom arc ends — they're what the
          // readout collided with, and the arc already reads as min→max.
          formatter: (v: number) =>
            Math.abs(v - min) < 1e-9 || Math.abs(v - max) < 1e-9 ? '' : fmtNum(v),
        },
        // Value readout in the open bottom-centre gap.
        detail: {
          valueAnimation: animate,
          offsetCenter: [0, '60%'],
          formatter: (v: number) => '{val|' + fmtNum(v) + '}' + (unit ? '{unit|' + unit + '}' : ''),
          rich: {
            val: {fontSize: Math.round(px * 0.135), fontWeight: 700, color: t.text, fontFamily: FONT},
            unit: {fontSize: Math.round(px * 0.058), color: t.textMuted, padding: [0, 0, 0, Math.round(px * 0.012)]},
          },
        },
        title: {show: false},
        data: [{value}],
      },
    ],
  };
}

export function Gauge({
  value,
  min = 0,
  max = 100,
  unit = '%',
  decimals = 0,
  zones = EAF_ZONES,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const {colorMode} = useColorMode();
  const v = value ?? min;

  useEffect(() => {
    const dom = ref.current;
    if (!dom) return;
    const t = TOKENS[colorMode === 'dark' ? 'dark' : 'light'];
    const chart = echarts.init(dom, null, {renderer: 'canvas'});
    // Radius is relative to the smaller container dimension, so scale fonts
    // off that too — keeps the readout and labels inside the arc.
    const pxOf = () => Math.max(120, Math.min(dom.clientWidth, dom.clientHeight));
    const build = (value: number, animate: boolean) =>
      dialOption(value, min, max, unit, decimals, zones, pxOf(), t, animate);

    // Intro: render the needle parked at min, then update to the real value so
    // the pointer sweeps and the number counts up together (the update is what
    // ECharts animates).
    let lastPx = pxOf();
    chart.setOption(build(min, true), {notMerge: true});
    const raf = requestAnimationFrame(() => {
      chart.setOption({series: [{data: [{value: v}]}]});
    });

    // ResizeObserver fires once immediately at the current size — guard on a
    // real size change so that initial callback doesn't re-render and cut the
    // intro animation short. Rebuilds on resize snap (animate:false).
    const ro = new ResizeObserver(() => {
      chart.resize();
      const p = pxOf();
      if (Math.abs(p - lastPx) > 1) {
        lastPx = p;
        chart.setOption(build(v, false), {notMerge: true});
      }
    });
    ro.observe(dom);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      chart.dispose();
    };
    // zones is a stable literal per call site; stringify to avoid identity churn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v, min, max, unit, decimals, colorMode, JSON.stringify(zones)]);

  return <div ref={ref} style={{width: '100%', height: '100%', minHeight: 180}} />;
}
