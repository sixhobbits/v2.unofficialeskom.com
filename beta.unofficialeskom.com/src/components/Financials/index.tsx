import {useEffect, useState} from 'react';
import type {ReactNode} from 'react';
import ReactECharts from 'echarts-for-react';
import {useColorMode} from '@docusaurus/theme-common';
import useBaseUrl from '@docusaurus/useBaseUrl';

import card from '../Dashboard/styles.module.css';

type AnnualFinancials = {
  years: number[];
  revenue: (number | null)[];
  ebitda: (number | null)[];
  net_profit: (number | null)[];
  primary_energy: (number | null)[];
  employee_costs: (number | null)[];
  depreciation: (number | null)[];
  profit_before_tax: (number | null)[];
};

type DashboardData = {
  annualFinancials?: AnnualFinancials;
};

function barOption(
  years: number[],
  series: {name: string; data: (number | null)[]; color: string}[],
  isDark: boolean,
  unit = 'R million',
) {
  const textColor = isDark ? '#ccc' : '#555';
  const gridColor = isDark ? '#444' : '#e5e5e5';
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: {type: 'shadow'},
      formatter: (params: any[]) => {
        const yr = params[0]?.name;
        const lines = params.map((p: any) => {
          const v = p.value == null ? '–' : `${(p.value).toLocaleString()} ${unit}`;
          return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px"></span>${p.seriesName}: <b>${v}</b>`;
        });
        return `<b>${yr}</b><br/>${lines.join('<br/>')}`;
      },
    },
    legend: {
      top: 8,
      textStyle: {color: textColor},
    },
    grid: {top: 48, left: 60, right: 16, bottom: 40, containLabel: false},
    xAxis: {
      type: 'category',
      data: years.map(String),
      axisLabel: {color: textColor},
      axisLine: {lineStyle: {color: gridColor}},
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: textColor,
        formatter: (v: number) => `${(v / 1000).toFixed(0)}B`,
      },
      splitLine: {lineStyle: {color: gridColor}},
    },
    series: series.map((s) => ({
      name: s.name,
      type: 'bar',
      data: s.data,
      itemStyle: {color: s.color},
      barMaxWidth: 40,
    })),
  };
}

function lineOption(
  years: number[],
  series: {name: string; data: (number | null)[]; color: string}[],
  isDark: boolean,
  unit = 'R million',
) {
  const textColor = isDark ? '#ccc' : '#555';
  const gridColor = isDark ? '#444' : '#e5e5e5';
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      formatter: (params: any[]) => {
        const yr = params[0]?.name;
        const lines = params.map((p: any) => {
          const v = p.value == null ? '–' : `${(p.value).toLocaleString()} ${unit}`;
          return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px"></span>${p.seriesName}: <b>${v}</b>`;
        });
        return `<b>${yr}</b><br/>${lines.join('<br/>')}`;
      },
    },
    legend: {
      top: 8,
      textStyle: {color: textColor},
    },
    grid: {top: 48, left: 60, right: 16, bottom: 40, containLabel: false},
    xAxis: {
      type: 'category',
      data: years.map(String),
      axisLabel: {color: textColor},
      axisLine: {lineStyle: {color: gridColor}},
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: textColor,
        formatter: (v: number) => `${(v / 1000).toFixed(0)}B`,
      },
      splitLine: {lineStyle: {color: gridColor}},
    },
    series: series.map((s) => ({
      name: s.name,
      type: 'line',
      data: s.data,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: {color: s.color, width: 2},
      itemStyle: {color: s.color},
    })),
  };
}

function Stat({label, value, note}: {label: string; value: string; note?: string}) {
  return (
    <div style={{flex: '1 1 160px', minWidth: 140, padding: '12px 16px', border: '1px solid var(--ifm-color-emphasis-300)', borderRadius: 8}}>
      <div style={{fontSize: '0.75rem', opacity: 0.6, marginBottom: 2}}>{label}</div>
      <div style={{fontSize: '1.3rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums'}}>{value}</div>
      {note && <div style={{fontSize: '0.7rem', opacity: 0.5, marginTop: 2}}>{note}</div>}
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '–';
  const abs = Math.abs(v);
  const sign = v < 0 ? '−' : '';
  if (abs >= 1_000_000) return `${sign}R${(abs / 1_000_000).toFixed(2)}T`;
  if (abs >= 1_000) return `${sign}R${(abs / 1_000).toFixed(1)}B`;
  return `${sign}R${abs.toLocaleString()}M`;
}

export default function Financials(): ReactNode {
  const {colorMode} = useColorMode();
  const isDark = colorMode === 'dark';
  const dataUrl = useBaseUrl('/dashboard-data.json');
  const [data, setData] = useState<AnnualFinancials | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(dataUrl)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<DashboardData>;
      })
      .then((j) => !cancelled && setData(j.annualFinancials ?? null))
      .catch((e) => !cancelled && setErr(String(e)));
    return () => { cancelled = true; };
  }, [dataUrl]);

  if (err) return <div style={{padding: '2rem', color: 'red'}}>Error: {err}</div>;
  if (!data || !data.years?.length) return <div style={{padding: '2rem'}}>Loading financial data…</div>;

  const {years, revenue, ebitda, net_profit, primary_energy, employee_costs, depreciation} = data;
  const latest = years[years.length - 1];
  const latestIdx = years.length - 1;

  const revenueChart = barOption(
    years,
    [{name: 'Revenue', data: revenue ?? [], color: '#1565c0'}],
    isDark,
  );

  const profitChart = lineOption(
    years,
    [
      {name: 'EBITDA', data: ebitda ?? [], color: '#2e7d32'},
      {name: 'Net profit', data: net_profit ?? [], color: '#c62828'},
    ],
    isDark,
  );

  const costsChart = barOption(
    years,
    [
      {name: 'Primary energy', data: (primary_energy ?? []).map((v) => v != null ? -v : null), color: '#e65100'},
      {name: 'Employee costs', data: (employee_costs ?? []).map((v) => v != null ? -v : null), color: '#4527a0'},
      {name: 'Depreciation', data: (depreciation ?? []).map((v) => v != null ? -v : null), color: '#00695c'},
    ],
    isDark,
  );

  return (
    <main style={{maxWidth: 960, margin: '0 auto', padding: '1.5rem 1rem'}}>
      <h1 style={{marginBottom: '0.25rem'}}>Eskom Annual Financials</h1>
      <p style={{opacity: 0.65, marginBottom: '1.5rem', fontSize: '0.9rem'}}>
        Key income statement lines extracted from published AFS PDFs. All values in R million (nominal). Financial years end 31 March.
      </p>

      <div style={{display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: '2rem'}}>
        <Stat label={`FY${latest} Revenue`} value={fmt(revenue?.[latestIdx])} note="Group" />
        <Stat label={`FY${latest} EBITDA`} value={fmt(ebitda?.[latestIdx])} />
        <Stat label={`FY${latest} Net profit`} value={fmt(net_profit?.[latestIdx])} />
        <Stat label={`FY${latest} Primary energy`} value={fmt(primary_energy?.[latestIdx])} note="Cost" />
      </div>

      <div className={card.card} style={{marginBottom: '1.5rem'}}>
        <h3 className={card.title}>Revenue (R million)</h3>
        <ReactECharts option={revenueChart} style={{height: 280}} notMerge />
      </div>

      <div className={card.card} style={{marginBottom: '1.5rem'}}>
        <h3 className={card.title}>EBITDA &amp; Net profit (R million)</h3>
        <ReactECharts option={profitChart} style={{height: 280}} notMerge />
      </div>

      <div className={card.card} style={{marginBottom: '1.5rem'}}>
        <h3 className={card.title}>Operating costs breakdown (R million, shown as positive)</h3>
        <ReactECharts option={costsChart} style={{height: 280}} notMerge />
      </div>

      <p style={{fontSize: '0.75rem', opacity: 0.5}}>
        Source: Eskom Annual Financial Statements. Values extracted via pdfplumber structured parsing from income statement tables.
        Some metrics unavailable for years prior to 2016 when EBITDA was not separately disclosed.
        FY2013 not shown (only interim report available).
      </p>
    </main>
  );
}
