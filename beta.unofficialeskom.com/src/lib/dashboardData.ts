/**
 * Single shared access layer for dashboard-data.json.
 *
 * Every page component MUST read the payload through useDashboardData() and
 * never off the raw JSON: the file keeps one filename across deploys and
 * browsers cache it, so any visitor can hold NEW JS + an OLD cached JSON that
 * predates a field. normalize() guarantees every known field exists with a
 * safe default, which turns that mismatch into a degraded card instead of an
 * unhandled render error that white-screens the whole page (2026-06-01
 * incident). Adding a field to the payload? Add it here, with its default —
 * components then never need their own `?? []` guards.
 */
import {useEffect, useState} from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';

export type Point = [number, number | null];
export type ByYear = Record<string, Array<number | null>>;

export type DashboardData = {
  latestTs: number | null;
  latestGen: number | null;
  latestDemand: number | null;
  latestEaf: number | null;
  latestEafLabel: string;
  thermalMin: Point[]; thermalAvg: Point[]; thermalMax: Point[];
  nuclearAvg: Point[];
  ocgtEskomMax: Point[]; ocgtIppMax: Point[]; ocgtTotalAvg: Point[];
  ocgtEskomHourly: Point[]; ocgtIppHourly: Point[];
  ocgtMonthlyAvg: Point[]; ocgtMonthlyMax: Point[];
  genAvg: Point[]; genMax: Point[];
  demandAvg: Point[]; demandMax: Point[];
  availableCapacityAvg: Point[]; headroomAvg: Point[];
  pclfAvg: Point[]; uclfAvg: Point[]; oclfAvg: Point[];
  clfPlanned: Point[]; clfUnplanned: Point[]; clfOther: Point[]; clfTotal: Point[];
  iosAvg: Point[]; mlrAvg: Point[]; ilsAvg: Point[]; totalReductionAvg: Point[];
  iosMax: Point[]; mlrMax: Point[]; ilsMax: Point[]; totalReductionMax: Point[];
  pumpedAvg: Point[]; hydroAvg: Point[];
  importsAvg: Point[]; exportsAvg: Point[];
  windAvg: Point[]; pvAvg: Point[]; cspAvg: Point[]; otherReAvg: Point[];
  reInstalledMonthly: Point[];
  officialEafWeekly: Point[]; officialEafMonthly: Point[];
  recentPumpedHourly: Point[];
  uclfOclfXKeys: string[];
  uclfOclfByYear: ByYear;
  eafWeeks: number[];
  eafByYear: ByYear;
  yoyMonths: number[];
  genByYear: ByYear; demandByYear: ByYear;
  capacityByYear: ByYear; peakDemandByYear: ByYear;
  rooftopProvinces: string[];
  rooftopSeries: Record<string, Point[]>;
  rooftopProvincesPerHh: string[];
  rooftopSeriesPerHh: Record<string, Point[]>;
  stationHourly: Record<string, Point[]>;
  outageHourly: {eaf: Point[]; pclf: Point[]; uclf: Point[]; oclf: Point[]};
  chartSources: Record<string, string[]>;
  // Complex nested payloads — normalized to null when absent; the consuming
  // page applies its own per-field defaults (see Outlook).
  portalCatalog: any[];
  weeklyReports: any[];
  outlook: any | null;
  annualFinancials: any | null;
  loadshedding: any | null;
};

const arr = (v: unknown): any[] => (Array.isArray(v) ? v : []);
const rec = (v: unknown): Record<string, any> =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, any>) : {};
const num = (v: unknown): number | null => (typeof v === 'number' ? v : null);

export function normalize(raw: any): DashboardData {
  const j = rec(raw);
  const oh = rec(j.outageHourly);
  return {
    latestTs: num(j.latestTs),
    latestGen: num(j.latestGen),
    latestDemand: num(j.latestDemand),
    latestEaf: num(j.latestEaf),
    latestEafLabel: typeof j.latestEafLabel === 'string' ? j.latestEafLabel : '',
    thermalMin: arr(j.thermalMin), thermalAvg: arr(j.thermalAvg), thermalMax: arr(j.thermalMax),
    nuclearAvg: arr(j.nuclearAvg),
    ocgtEskomMax: arr(j.ocgtEskomMax), ocgtIppMax: arr(j.ocgtIppMax), ocgtTotalAvg: arr(j.ocgtTotalAvg),
    ocgtEskomHourly: arr(j.ocgtEskomHourly), ocgtIppHourly: arr(j.ocgtIppHourly),
    ocgtMonthlyAvg: arr(j.ocgtMonthlyAvg), ocgtMonthlyMax: arr(j.ocgtMonthlyMax),
    genAvg: arr(j.genAvg), genMax: arr(j.genMax),
    demandAvg: arr(j.demandAvg), demandMax: arr(j.demandMax),
    availableCapacityAvg: arr(j.availableCapacityAvg), headroomAvg: arr(j.headroomAvg),
    pclfAvg: arr(j.pclfAvg), uclfAvg: arr(j.uclfAvg), oclfAvg: arr(j.oclfAvg),
    clfPlanned: arr(j.clfPlanned), clfUnplanned: arr(j.clfUnplanned),
    clfOther: arr(j.clfOther), clfTotal: arr(j.clfTotal),
    iosAvg: arr(j.iosAvg), mlrAvg: arr(j.mlrAvg), ilsAvg: arr(j.ilsAvg),
    totalReductionAvg: arr(j.totalReductionAvg),
    iosMax: arr(j.iosMax), mlrMax: arr(j.mlrMax), ilsMax: arr(j.ilsMax),
    totalReductionMax: arr(j.totalReductionMax),
    pumpedAvg: arr(j.pumpedAvg), hydroAvg: arr(j.hydroAvg),
    importsAvg: arr(j.importsAvg), exportsAvg: arr(j.exportsAvg),
    windAvg: arr(j.windAvg), pvAvg: arr(j.pvAvg), cspAvg: arr(j.cspAvg), otherReAvg: arr(j.otherReAvg),
    reInstalledMonthly: arr(j.reInstalledMonthly),
    officialEafWeekly: arr(j.officialEafWeekly), officialEafMonthly: arr(j.officialEafMonthly),
    recentPumpedHourly: arr(j.recentPumpedHourly),
    uclfOclfXKeys: arr(j.uclfOclfXKeys),
    uclfOclfByYear: rec(j.uclfOclfByYear),
    eafWeeks: arr(j.eafWeeks),
    eafByYear: rec(j.eafByYear),
    yoyMonths: arr(j.yoyMonths),
    genByYear: rec(j.genByYear), demandByYear: rec(j.demandByYear),
    capacityByYear: rec(j.capacityByYear), peakDemandByYear: rec(j.peakDemandByYear),
    rooftopProvinces: arr(j.rooftopProvinces),
    rooftopSeries: rec(j.rooftopSeries),
    rooftopProvincesPerHh: arr(j.rooftopProvincesPerHh),
    rooftopSeriesPerHh: rec(j.rooftopSeriesPerHh),
    stationHourly: rec(j.stationHourly),
    outageHourly: {eaf: arr(oh.eaf), pclf: arr(oh.pclf), uclf: arr(oh.uclf), oclf: arr(oh.oclf)},
    chartSources: rec(j.chartSources),
    portalCatalog: arr(j.portalCatalog),
    weeklyReports: arr(j.weeklyReports),
    outlook: j.outlook ?? null,
    annualFinancials: j.annualFinancials ?? null,
    loadshedding: j.loadshedding ?? null,
  };
}

/**
 * Fetch + normalize dashboard-data.json. The ?v= cache-buster is the build id
 * (baked at `yarn build` time via customFields), so freshly deployed JS always
 * fetches a matching JSON instead of reusing a cached payload from a previous
 * deploy. normalize() still guards the remaining mismatch windows (CDN lag,
 * long-lived tabs).
 */
export function useDashboardData(): {data: DashboardData | null; err: string | null} {
  const {siteConfig} = useDocusaurusContext();
  const buildId = String(siteConfig.customFields?.buildId ?? '');
  const base = useBaseUrl('/dashboard-data.json');
  const dataUrl = buildId ? `${base}?v=${buildId}` : base;
  const [data, setData] = useState<DashboardData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(dataUrl)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => !cancelled && setData(normalize(j)))
      .catch((e) => !cancelled && setErr(String(e)));
    return () => {
      cancelled = true;
    };
  }, [dataUrl]);

  return {data, err};
}

export function useIsMobile(maxWidth = 720): boolean {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`);
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [maxWidth]);
  return isMobile;
}
