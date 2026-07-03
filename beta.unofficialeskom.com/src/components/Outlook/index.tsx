import {useEffect, useMemo, useState} from 'react';
import type {ReactNode} from 'react';
import {useColorMode} from '@docusaurus/theme-common';
import clsx from 'clsx';

import {useDashboardData, useIsMobile} from '../../lib/dashboardData';
import {PALETTES, timeSeriesOption, type Palette} from '../Dashboard/options';
import {ChartCard} from '../Dashboard/index';
import {Gauge} from '../Dashboard/Gauge';
import card from '../Dashboard/styles.module.css';
import styles from './styles.module.css';

type Point = [number, number | null];
type ZoneColor = 'good' | 'warn' | 'bad';

type Check = {id: string; label: string; severity: 'high' | 'medium'; active: boolean; detail: string};

type Metric = {
  id: string;
  label: string;
  value: number | null;
  min: number;
  max: number;
  unit: string;
  decimals: number;
  zones: [number, ZoneColor][];
};

type Status = 'green' | 'yellow' | 'orange' | 'red';
type StatusForecast = {
  reportWeek: number | null;
  reportPeriod: string | null;
  counts: {green: number; yellow: number; orange: number; red: number; total: number};
  firstRisk: {weekStart: number; weekNum: number; status: Status} | null;
  weeks: {weekStart: number; weekNum: number; status: Status; likelyRiskMw: number}[];
};

type Outlook = {
  metrics: Metric[];
  forecast: {residual: Point[]; contracted: Point[]};
  demandCapacity: {contractedDemand: Point[]; residualDemand: Point[]; availableCapacity: Point[]};
  incidents: Check[];
  checks: Check[];
  latestNuclear: number | null;
  statusForecast: StatusForecast | null;
};

const STATUS_COLOR: Record<Status, string> = {
  green: '#43a047',
  yellow: '#fdd835',
  orange: '#fb8c00',
  red: '#e53935',
};
const STATUS_LABEL: Record<Status, string> = {
  green: 'Adequate',
  yellow: 'Tight (<1 GW short of reserves)',
  orange: 'Short of reserves (1–2 GW)',
  red: 'Short of demand + reserves',
};

const LINE_BASE = {
  type: 'line',
  symbol: 'none',
  showSymbol: false,
  animation: false,
  connectNulls: false,
} as const;

// dataZoom start (%) so the visible window opens on the last `days` of a
// series. Daily series → one point per day; hourly handled by the caller.
function startForLastDays(series: Point[], days: number, perDay: number): number {
  const n = series.length;
  if (n <= 0) return 0;
  return Math.max(0, ((n - days * perDay) / n) * 100);
}

// ---- Emissions-compliance milestones (manually curated public regulatory
// facts, each cited — NOT scraped). Eskom's coal fleet runs on time-limited
// exemptions from the Minimum Emission Standards (MES); most expire 1 Apr 2030.
const MES_DEADLINE = '2030-04-01T00:00:00+02:00'; // SAST — the headline cliff
const GEORGE_2025 =
  'https://www.gov.za/news/media-statements/minister-dion-george-announcement-decision-eskom%E2%80%99s-application-exemptions';
const CREECY_2024 =
  'https://www.engineeringnews.co.za/article/eskom-board-approves-plan-to-operate-camden-grootvlei-and-hendrina-to-2030-2024-05-20';
const ESKOM_22GW =
  'https://www.eskom.co.za/eskom-reaffirms-commitment-to-cleaner-air-through-decades-of-emissions-reduction-environmental-stewardship-and-sustainable-energy-practices/';

type Milestone = {date: string; what: string; plants: string; src: string; srcLabel: string};
const MES_MILESTONES: Milestone[] = [
  {date: '2030-04-01', what: 'MES exemption expires (5-year)',
    plants: 'Kendal, Lethabo, Tutuka, Majuba, Matimba, Medupi', src: GEORGE_2025, srcLabel: 'DFFE · 31 Mar 2025'},
  {date: '2030-03-31', what: 'Operate-to date at existing MES limits',
    plants: 'Camden, Grootvlei, Hendrina, Arnot, Kriel', src: CREECY_2024, srcLabel: 'DFFE/Eskom · May 2024'},
  {date: '2034-02-21', what: 'Planned shutdown (exemption to decommissioning)',
    plants: 'Duvha', src: GEORGE_2025, srcLabel: 'DFFE · 31 Mar 2025'},
  {date: '2034-07-20', what: 'Planned shutdown (exemption to decommissioning)',
    plants: 'Matla', src: GEORGE_2025, srcLabel: 'DFFE · 31 Mar 2025'},
];

// The dials grouped into the three questions a reader actually asks. Order
// within each group is the order the dials render left-to-right.
const DIAL_GROUPS: {title: string; intro: string; ids: string[]}[] = [
  {
    title: 'Baseload',
    intro:
      'How is our baseload? Coal, nuclear and the overall availability factor (EAF) should be reliably providing most of what we need.',
    ids: ['coal', 'nuclear', 'eaf'],
  },
  {
    title: 'Peaking',
    intro:
      'How is our emergency capacity? Diesel turbines (OCGT) and pumped storage are reserves to get through the 6pm peak if needed — and we shouldn’t be leaning on them outside peak times.',
    ids: ['ocgt-peak', 'ocgt-offpeak', 'pumped'],
  },
  {
    title: 'Outages',
    intro:
      'How are our outages? Some plants should be offline for planned maintenance, ideally few are out unplanned, and we want sufficient standby capacity (headroom) in reserve.',
    ids: ['pclf', 'uclf', 'headroom'],
  },
];

function fmtMilestone(iso: string): string {
  return new Date(iso + 'T00:00:00Z').toLocaleDateString('en-ZA', {
    day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
  });
}

export default function Outlook(): ReactNode {
  const {colorMode} = useColorMode();
  const P: Palette = PALETTES[colorMode === 'dark' ? 'dark' : 'light'];

  const {data, err} = useDashboardData();
  const isMobile = useIsMobile();

  // Live tick for the MES compliance countdown.
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const countdown = useMemo(() => {
    const ms = Math.max(0, Date.parse(MES_DEADLINE) - nowMs);
    const s = Math.floor(ms / 1000);
    return {
      days: Math.floor(s / 86400),
      hours: Math.floor((s % 86400) / 3600),
      mins: Math.floor((s % 3600) / 60),
      secs: s % 60,
      passed: ms === 0,
    };
  }, [nowMs]);

  // Defensive against a stale browser-cached dashboard-data.json that predates
  // a field we now read: a missing field must degrade the section, never
  // white-screen the whole page. Everything below reads through these safe
  // defaults rather than the raw payload.
  const o: Outlook = useMemo(() => {
    const raw = (data?.outlook ?? {}) as Partial<Outlook>;
    return {
      metrics: raw.metrics ?? [],
      forecast: {
        residual: raw.forecast?.residual ?? [],
        contracted: raw.forecast?.contracted ?? [],
      },
      demandCapacity: {
        contractedDemand: raw.demandCapacity?.contractedDemand ?? [],
        residualDemand: raw.demandCapacity?.residualDemand ?? [],
        availableCapacity: raw.demandCapacity?.availableCapacity ?? [],
      },
      incidents: raw.incidents ?? [],
      checks: raw.checks ?? [],
      latestNuclear: raw.latestNuclear ?? null,
      statusForecast: raw.statusForecast ?? null,
    };
  }, [data]);

  const charts = useMemo(() => {
    if (!data) return null;
    const ts = (series: any[], opts: any = {}) =>
      timeSeriesOption(series, {...opts, isMobile}, P);
    const arr = (a: Point[] | undefined): Point[] => a ?? [];

    // Forecast vs recent actuals on one time axis: capacity + demand for the
    // last week, demand forecast running 3 months forward. There's no forward
    // capacity feed, so capacity stops where the actuals do.
    const forecast = ts(
      [
        {...LINE_BASE, name: 'Available capacity (actual)', data: o.demandCapacity.availableCapacity,
          lineStyle: {width: 1.8, color: '#43a047'}, areaStyle: {color: '#43a047', opacity: 0.1}, itemStyle: {color: '#43a047'}},
        {...LINE_BASE, name: 'Demand — RSA contracted (actual)', data: o.demandCapacity.contractedDemand,
          lineStyle: {width: 1.8, color: '#1976d2'}, itemStyle: {color: '#1976d2'}},
        {...LINE_BASE, name: 'Demand forecast — RSA contracted', data: o.forecast.contracted,
          lineStyle: {width: 1.6, color: '#ef6c00', type: 'dashed'}, itemStyle: {color: '#ef6c00'}},
        {...LINE_BASE, name: 'Demand forecast — residual', data: o.forecast.residual,
          lineStyle: {width: 1.6, color: '#8e24aa', type: 'dashed'}, itemStyle: {color: '#8e24aa'}},
      ],
      // Full range: recent actuals + 3-month forecast.
      {hourly: true, zoomStart: 0},
    );

    const recent = 14 * 24;
    const ocgt = ts(
      [
        {...LINE_BASE, name: 'Eskom OCGT', data: arr(data.ocgtEskomHourly).slice(-recent), stack: 'ocgt',
          areaStyle: {color: '#42a5f5', opacity: 0.85}, lineStyle: {width: 0}, itemStyle: {color: '#42a5f5'}},
        {...LINE_BASE, name: 'Dispatchable IPP OCGT', data: arr(data.ocgtIppHourly).slice(-recent), stack: 'ocgt',
          areaStyle: {color: '#66bb6a', opacity: 0.85}, lineStyle: {width: 0}, itemStyle: {color: '#66bb6a'}},
      ],
      {hourly: true, zoomStart: 0},
    );

    const pumped = ts(
      [
        {...LINE_BASE, name: 'Pumped storage generation', data: arr(data.recentPumpedHourly),
          lineStyle: {width: 1.6, color: '#0277bd'}, areaStyle: {color: '#0277bd', opacity: 0.12}, itemStyle: {color: '#0277bd'}},
      ],
      {hourly: true, decimals: 1, zoomStart: 0},
    );

    // Demand-reduction charts (daily avg MW), same as the dashboard but opened
    // on the last 7 days; the slider still reaches the full history.
    const reduction = (series: Point[], color: string) =>
      ts(
        [{...LINE_BASE, name: 'Daily avg', data: series, lineStyle: {width: 1.4, color},
          areaStyle: {color, opacity: 0.12}, itemStyle: {color}}],
        {unit: 'MW', decimals: 1, zoomStart: startForLastDays(series, 7, 1)},
      );
    const totalReduction = reduction(arr(data.totalReductionAvg), '#d32f2f');
    const ios = reduction(arr(data.iosAvg), '#5e35b1');
    const mlr = reduction(arr(data.mlrAvg), '#ef6c00');
    const ils = reduction(arr(data.ilsAvg), '#00897b');

    return {forecast, ocgt, pumped, totalReduction, ios, mlr, ils};
  }, [data, o, P, isMobile]);

  if (err) return <div className={styles.loading}>Failed to load data: {err}</div>;
  if (!data || !charts) return <div className={styles.loading}>Loading…</div>;

  const inactive = o.checks.filter((c) => !c.active);
  const metricById = new Map(o.metrics.map((m) => [m.id, m]));
  const sf = o.statusForecast;
  const STATUSES: Status[] = ['green', 'yellow', 'orange', 'red'];

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1>Status</h1>
        <p>Where the grid is right now, what the official forecast expects, and anything anomalous.</p>
      </header>

      <h2 className={styles.sectionTitle}>Grid status</h2>
      {DIAL_GROUPS.map((g) => {
        const dials = g.ids.map((id) => metricById.get(id)).filter(Boolean) as Metric[];
        if (!dials.length) return null;
        return (
          <section key={g.title} className={styles.dialGroup}>
            <h3 className={styles.groupTitle}>{g.title}</h3>
            <p className={styles.groupIntro}>{g.intro}</p>
            <div className={styles.dialsGrid}>
              {dials.map((m) => (
                <div key={m.id} className={clsx(card.card, styles.dialCard)}>
                  <div className={styles.dialLabel}>{m.label}</div>
                  <div className={styles.dialBox}>
                    <Gauge
                      value={m.value}
                      min={m.min}
                      max={m.max}
                      unit={m.unit}
                      decimals={m.decimals}
                      zones={m.zones}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>
        );
      })}

      <h2 className={styles.sectionTitle}>Current incidents</h2>
      {o.incidents.length === 0 ? (
        <div className={styles.allClear}>No current incidents — all monitored thresholds are within normal range.</div>
      ) : (
        <div className={styles.incidentList}>
          {o.incidents.map((c) => (
            <div key={c.id} className={clsx(styles.incident, styles[c.severity])}>
              <span className={styles.incidentDot} />
              <div className={styles.incidentBody}>
                <span className={styles.incidentTitle}>{c.label}</span>
                <span className={styles.incidentDetail}>{c.detail}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {inactive.length > 0 && (
        <details className={clsx(card.card, styles.checks)}>
          <summary>Monitored checks, currently normal ({inactive.length})</summary>
          <div style={{marginTop: '0.5rem'}}>
            {inactive.map((c) => (
              <div key={c.id} className={styles.checkRow}>
                <span className={styles.checkMark}>✓</span>
                <span className={styles.checkLabel}>{c.label}</span>
                <span className={styles.checkDetail}>{c.detail}</span>
              </div>
            ))}
          </div>
        </details>
      )}

      {sf && sf.counts.total > 0 && (
        <>
          <h2 className={styles.sectionTitle}>Supply adequacy outlook</h2>
          <div className={clsx(card.card, styles.adequacyCard)}>
            <div className={styles.adequacyHead}>
              <span className={styles.adequacyTitle}>{sf.counts.total}-week forecast</span>
              <span className={styles.adequacySource}>
                NTCSA Weekly System Status Report
                {sf.reportWeek ? ` — week ${sf.reportWeek}` : ''}
                {sf.reportPeriod ? ` (${sf.reportPeriod})` : ''}
              </span>
            </div>
            <div className={styles.chips}>
              {STATUSES.map((s) => (
                <span key={s} className={styles.chip}>
                  <span className={styles.chipDot} style={{background: STATUS_COLOR[s]}} />
                  {sf.counts[s]} {s}
                </span>
              ))}
            </div>
            <div className={styles.weekStrip}>
              {sf.weeks.map((w) => (
                <span
                  key={w.weekStart}
                  className={styles.weekSeg}
                  style={{background: STATUS_COLOR[w.status]}}
                  title={`Week ${w.weekNum}: ${STATUS_LABEL[w.status]} · likely margin ${w.likelyRiskMw.toLocaleString('en-ZA')} MW`}
                />
              ))}
            </div>
            <div className={styles.stripLegend}>
              {sf.firstRisk
                ? `First at-risk week ahead: W${sf.firstRisk.weekNum} (${sf.firstRisk.status}).`
                : 'No at-risk weeks in the forecast — generation is forecast adequate every week.'}
            </div>
          </div>
        </>
      )}

      <h2 className={styles.sectionTitle}>Emissions compliance</h2>
      <div className={clsx(card.card, styles.complianceCard)}>
        <div className={styles.adequacyHead}>
          <span className={styles.adequacyTitle}>Coal fleet on borrowed time</span>
          <span className={styles.adequacySource}>Minimum Emission Standards (MES) exemptions</span>
        </div>
        <div className={styles.countdownRow}>
          {([[countdown.days, 'Days'], [countdown.hours, 'Hours'], [countdown.mins, 'Mins'], [countdown.secs, 'Secs']] as [number, string][]).map(
            ([n, label]) => (
              <div key={label} className={styles.cdTile}>
                <div className={styles.cdNum}>{n.toLocaleString('en-ZA')}</div>
                <div className={styles.cdUnit}>{label}</div>
              </div>
            ),
          )}
        </div>
        <p className={styles.cdCaption}>
          until the bulk of Eskom&rsquo;s coal-fleet MES exemptions expire (1 April 2030).
        </p>
        <p className={styles.cdContext}>
          ≈22 GW of coal capacity is at risk of shutdown after 2030 if SO₂ standards aren&rsquo;t
          met (
          <a href={ESKOM_22GW} target="_blank" rel="noopener noreferrer">Eskom, Jun 2025</a>
          ).
        </p>
        <table className={styles.milestoneTable}>
          <thead>
            <tr>
              <th>Date</th>
              <th>Milestone</th>
              <th>Stations</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {MES_MILESTONES.map((m) => (
              <tr key={m.date + m.plants}>
                <td className={styles.mDate}>{fmtMilestone(m.date)}</td>
                <td>{m.what}</td>
                <td>{m.plants}</td>
                <td className={styles.mSrc}>
                  <a href={m.src} target="_blank" rel="noopener noreferrer">{m.srcLabel}</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className={styles.sectionTitle}>Demand &amp; capacity forecast</h2>
      <div className={card.chartGrid}>
        <ChartCard
          title="Recent demand &amp; available capacity, with official 3-month demand forecast (hourly)"
          option={charts.forecast}
        />
      </div>

      <h2 className={styles.sectionTitle}>Recent peaking &amp; storage use</h2>
      <div className={card.chartPair}>
        <ChartCard title="OCGT generation (Eskom + IPP, last 14 days)" option={charts.ocgt} />
        <ChartCard title="Pumped storage generation (last 14 days)" option={charts.pumped} />
      </div>

      <h2 className={styles.sectionTitle}>Demand reduction</h2>
      <p className={styles.subnote}>Opens on the last 7 days — drag the slider to see the full history.</p>
      <div className={card.chartPair}>
        <ChartCard title="Total load reduction (daily avg)" option={charts.totalReduction} />
        <ChartCard title="IOS — excl. ILS &amp; MLR (daily avg)" option={charts.ios} />
      </div>
      <div className={card.chartPair}>
        <ChartCard title="MLR — manual load reduction (daily avg)" option={charts.mlr} />
        <ChartCard title="ILS — interruptible load (daily avg)" option={charts.ils} />
      </div>
    </div>
  );
}
