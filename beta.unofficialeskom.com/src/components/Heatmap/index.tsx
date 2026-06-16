import {useEffect, useRef, useState} from 'react';
import type {ReactNode} from 'react';
import ReactECharts from 'echarts-for-react';
import {useColorMode} from '@docusaurus/theme-common';
import useBaseUrl from '@docusaurus/useBaseUrl';

type DayEntry = [string, number]; // ['2025-02-23', 6]

type Loadshedding = {
  days: DayEntry[];
  streakSinceMs: number | null;
};

type DashboardData = {
  loadshedding?: Loadshedding;
};

const STAGE_COLORS = ['#ebedf0', '#fff59d', '#ffc107', '#ff6f00', '#e53935', '#b71c1c', '#4a0000'];
const STAGE_LABELS = ['None', 'Stage 1', 'Stage 2', 'Stage 3', 'Stage 4', 'Stage 5', 'Stage 6'];

const DARK_STAGE_COLORS = ['#30363d', '#fff59d', '#ffc107', '#ff6f00', '#e53935', '#b71c1c', '#4a0000'];

function calendarOption(
  year: number,
  data: DayEntry[],
  isDark: boolean,
): object {
  const textColor = isDark ? '#aaa' : '#666';
  const borderColor = isDark ? '#444' : '#ddd';
  const colors = isDark ? DARK_STAGE_COLORS : STAGE_COLORS;

  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p: {data: DayEntry}) => {
        const [date, stage] = p.data;
        const label = stage === 0 ? 'No loadshedding' : `Stage ${stage}`;
        return `<b>${date}</b><br/>${label}`;
      },
    },
    visualMap: {
      show: false,
      type: 'piecewise',
      pieces: [
        {min: 0, max: 0, color: colors[0]},
        {min: 1, max: 1, color: colors[1]},
        {min: 2, max: 2, color: colors[2]},
        {min: 3, max: 3, color: colors[3]},
        {min: 4, max: 4, color: colors[4]},
        {min: 5, max: 5, color: colors[5]},
        {min: 6, max: 10, color: colors[6]},
      ],
    },
    calendar: {
      top: 24,
      left: 36,
      right: 12,
      bottom: 8,
      cellSize: ['auto', 13],
      range: String(year),
      itemStyle: {borderWidth: 0.5, borderColor},
      dayLabel: {
        show: true,
        firstDay: 1,
        nameMap: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
        color: textColor,
        fontSize: 10,
      },
      monthLabel: {color: textColor, nameMap: 'en', fontSize: 11},
      yearLabel: {show: false},
      splitLine: {show: false},
    },
    series: [
      {
        type: 'heatmap',
        coordinateSystem: 'calendar',
        data,
      },
    ],
  };
}

function formatDuration(ms: number): string {
  const totalHours = Math.floor(ms / 3_600_000);
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  if (days > 0) return `${days.toLocaleString()} days, ${hours} hours`;
  return `${totalHours} hours`;
}

function StreakBanner({streakSinceMs, isDark}: {streakSinceMs: number | null; isDark: boolean}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  if (!streakSinceMs) return null;
  const elapsed = now - streakSinceMs;
  const sinceDate = new Date(streakSinceMs).toLocaleDateString('en-ZA', {
    day: 'numeric', month: 'long', year: 'numeric',
  });

  return (
    <div style={{
      background: isDark ? '#1a2e1a' : '#e8f5e9',
      border: `1px solid ${isDark ? '#2e7d32' : '#a5d6a7'}`,
      borderRadius: 8,
      padding: '12px 20px',
      marginBottom: '1.5rem',
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      flexWrap: 'wrap',
    }}>
      <span style={{fontSize: '2rem'}}>🟢</span>
      <div>
        <div style={{fontWeight: 700, fontSize: '1.05rem'}}>
          No loadshedding for {formatDuration(elapsed)}
        </div>
        <div style={{fontSize: '0.85rem', opacity: 0.7}}>
          Since {sinceDate}
        </div>
      </div>
    </div>
  );
}

function StageLegend({isDark}: {isDark: boolean}) {
  const colors = isDark ? DARK_STAGE_COLORS : STAGE_COLORS;
  return (
    <div style={{display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: '1.5rem', alignItems: 'center'}}>
      <span style={{fontSize: '0.8rem', opacity: 0.6}}>Stage:</span>
      {STAGE_LABELS.map((label, i) => (
        <div key={i} style={{display: 'flex', alignItems: 'center', gap: 5}}>
          <div style={{
            width: 13, height: 13, borderRadius: 2,
            background: colors[i],
            border: `1px solid ${isDark ? '#444' : '#ccc'}`,
          }} />
          <span style={{fontSize: '0.78rem', opacity: 0.75}}>{label}</span>
        </div>
      ))}
    </div>
  );
}

export default function Heatmap(): ReactNode {
  const {colorMode} = useColorMode();
  const isDark = colorMode === 'dark';
  const dataUrl = useBaseUrl('/dashboard-data.json');
  const [data, setData] = useState<Loadshedding | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(dataUrl)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() as Promise<DashboardData>; })
      .then((j) => !cancelled && setData(j.loadshedding ?? null))
      .catch((e) => !cancelled && setErr(String(e)));
    return () => { cancelled = true; };
  }, [dataUrl]);

  if (err) return <div style={{padding: '2rem', color: 'red'}}>Error: {err}</div>;
  if (!data?.days?.length) return <div style={{padding: '2rem'}}>Loading…</div>;

  // Group days by year
  const byYear = new Map<number, DayEntry[]>();
  for (const [date, stage] of data.days) {
    const year = parseInt(date.slice(0, 4), 10);
    if (!byYear.has(year)) byYear.set(year, []);
    byYear.get(year)!.push([date, stage]);
  }

  // All years from first to current, newest first
  const currentYear = new Date().getFullYear();
  const firstYear = Math.min(...byYear.keys());
  const years: number[] = [];
  for (let y = currentYear; y >= firstYear; y--) years.push(y);

  return (
    <main style={{maxWidth: 1000, margin: '0 auto', padding: '1.5rem 1rem'}}>
      <h1 style={{marginBottom: '0.25rem'}}>Loadshedding heatmap</h1>
      <p style={{opacity: 0.65, marginBottom: '1.5rem', fontSize: '0.9rem'}}>
        Daily maximum loadshedding stage, 2014–present. Data from{' '}
        <a href="https://sepush.co.za" target="_blank" rel="noopener noreferrer">EskomSePush</a>.
      </p>

      <StreakBanner streakSinceMs={data.streakSinceMs} isDark={isDark} />
      <StageLegend isDark={isDark} />

      <div ref={containerRef}>
        {years.map((year) => {
          const yearData = byYear.get(year) ?? [];
          const hasShedding = yearData.some(([, s]) => s > 0);
          const maxStage = yearData.reduce((m, [, s]) => Math.max(m, s), 0);
          return (
            <div key={year} style={{marginBottom: '1.5rem'}}>
              <div style={{display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4}}>
                <h3 style={{margin: 0}}>{year}</h3>
                {!hasShedding && (
                  <span style={{fontSize: '0.8rem', opacity: 0.5}}>No loadshedding</span>
                )}
                {hasShedding && (
                  <span style={{fontSize: '0.8rem', opacity: 0.6}}>
                    {yearData.filter(([, s]) => s > 0).length} days affected · peak stage {maxStage}
                  </span>
                )}
              </div>
              <div style={{overflowX: 'auto'}}>
                <div style={{minWidth: 660}}>
                  <ReactECharts
                    option={calendarOption(year, yearData, isDark)}
                    style={{height: 130}}
                    notMerge
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p style={{fontSize: '0.75rem', opacity: 0.5, marginTop: '2rem'}}>
        Stage changes sourced from the EskomSePush Google Sheet history. Each cell shows the
        maximum stage active during that day. Days before 2014-03-06 have no recorded data.
        Updated daily.
      </p>
    </main>
  );
}
