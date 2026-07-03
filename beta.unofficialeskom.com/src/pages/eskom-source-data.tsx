import type {ReactNode} from 'react';
import Layout from '@theme/Layout';

import {useDashboardData} from '../lib/dashboardData';
import styles from './eskom-source-data.module.css';

// Every graph on the Eskom Data Portal (https://www.eskom.co.za/dataportal/),
// flattened across its six sections. The whole table is data-driven: it reads
// `portalCatalog` out of dashboard-data.json, which the bruin pipeline rebuilds
// every run. The CSV / PowerBI links are re-discovered each run (they move),
// and the freshness columns show the newest data point our generic scrapers
// (raw.portal_csv* / raw.portal_powerbi*) ingested for that graph.

type Cell = {
  url: string | null; // discovered download / embed link, null if none offered
  latest: string | null; // newest dated data point (YYYY-MM-DD), null if undated
  rows: number; // parsed point count
  published: string | null; // when Eskom last published this source (YYYY-MM-DD), null if unknown
};

type Graph = {
  section: string;
  name: string;
  slug: string;
  page: string;
  csv: Cell;
  powerbi: Cell;
  // Graph-level summary of the freshest data we hold, regardless of source.
  latest: string | null;
  rows: number;
};

const SECTION_ORDER = [
  'Demand side',
  'Supply side',
  'OCGT usage',
  'Renewables',
  'Outages',
  'Emissions',
];

// The download / embed links Eskom offers for a graph. We don't surface which
// one our freshness came from — just give the reader every way in.
function SourceLinks({csv, powerbi}: {csv: Cell; powerbi: Cell}): ReactNode {
  const links: ReactNode[] = [];
  if (powerbi.url)
    links.push(
      <a key="pbi" href={powerbi.url} target="_blank" rel="noopener noreferrer">
        PowerBI
      </a>,
    );
  if (csv.url)
    links.push(
      <a key="csv" href={csv.url} target="_blank" rel="noopener noreferrer">
        CSV
      </a>,
    );
  if (!links.length) return <span className={styles.none}>—</span>;
  return <span className={styles.cell}>{links}</span>;
}

// Graph-level summary of the most recent data we hold, regardless of source:
//   dated rows                 -> latest date (fresh)
//   rows but no date axis       -> "Ingested" (e.g. outage-interval bins)
//   a link but zero parsed rows -> "No data" (e.g. Eskom's CSV link 404s)
//   no link offered at all      -> "—"
function LatestCell({graph}: {graph: Graph}): ReactNode {
  if (graph.latest) return <span className={styles.fresh}>{graph.latest}</span>;
  if (graph.rows > 0)
    return (
      <span className={styles.ingested} title={`${graph.rows} rows, no date axis`}>
        Ingested
      </span>
    );
  if (graph.csv.url || graph.powerbi.url) return <span className={styles.nodata}>No data</span>;
  return <span className={styles.none}>—</span>;
}

type WeeklyReport = {
  name: string;
  year: number | null;
  week: number | null;
  period: string | null;
  pdfUrl: string | null;
  grabbedAt: number | null;
};

function fmtDate(ms: number | null): string {
  if (ms == null) return '–';
  return new Date(ms).toISOString().slice(0, 10);
}

export default function EskomSourceDataPage(): ReactNode {
  const {data, err} = useDashboardData();
  const catalog = (data?.portalCatalog ?? []) as Graph[];
  const reports = (data?.weeklyReports ?? []) as WeeklyReport[];
  const loaded = data != null || err != null;

  const scraped = catalog.filter((g) => g.rows).length;

  return (
    <Layout
      title="Eskom Source Data"
      description="Every graph published on the Eskom Data Portal, with live CSV and PowerBI links and the freshness of the data we scrape.">
      <main className={styles.wrap}>
        <h1>Eskom Source Data</h1>
        <p className={styles.lede}>
          Every dataset published on the{' '}
          <a
            href="https://www.eskom.co.za/dataportal/"
            target="_blank"
            rel="noopener noreferrer">
            Eskom Data Portal
          </a>
          , flattened from its six sections into one list. Each row links to the
          portal page, the embedded PowerBI report, and the raw CSV download.
          Links are re-discovered on every pipeline run, so they stay current
          even when Eskom moves the files.
        </p>
        <p className={styles.lede}>
          <strong>PowerBI new data</strong> and <strong>CSV new data</strong>{' '}
          show the last date we received a version of that source we hadn't seen
          before — i.e. when Eskom actually published new data, not just when we
          ran. <strong>Data up to</strong> is the newest data point we hold for
          that graph, whichever source it came from:{' '}
          <span className={styles.fresh}>a date</span> for time series,{' '}
          <span className={styles.ingested}>Ingested</span> for datasets with no
          date axis (e.g. outage-interval bins),{' '}
          <span className={styles.nodata}>No data</span> when the source is
          currently empty (e.g. a broken Eskom link), and{' '}
          <span className={styles.none}>—</span> when Eskom offers no download.
          {loaded && catalog.length
            ? ` Scraping ${scraped} of ${catalog.length} graphs.`
            : ''}
        </p>

        <section className={styles.section}>
          <h2>Download the warehouse</h2>
          <p className={styles.lede}>
            The full scraped dataset is available for download. These files contain
            historical data that cycles off Eskom's portal and cannot be re-scraped.
            Pipeline source code:{' '}
            <a href="https://github.com/sixhobbits/v2.unofficialeskom.com" target="_blank" rel="noopener noreferrer">
              github.com/sixhobbits/v2.unofficialeskom.com
            </a>.
          </p>
          <table className={styles.table}>
            <thead>
              <tr><th>File</th><th>Size</th><th>Contents</th><th>Download</th></tr>
            </thead>
            <tbody>
              <tr>
                <td><code>warehouse/eskom.duckdb</code></td>
                <td>~490 MB</td>
                <td>All scraped portal data (CSV + PowerBI), staging tables, dashboard views</td>
                <td><a href="/data/warehouse/eskom.duckdb">Download</a></td>
              </tr>
              <tr>
                <td><code>warehouse/media_presentations/index.duckdb</code></td>
                <td>~60 MB</td>
                <td>Weekly media presentations, integrated reports, AFS financials metadata</td>
                <td><a href="/data/warehouse/media_presentations/index.duckdb">Download</a></td>
              </tr>
              <tr>
                <td><code>warehouse/integrated_results/pdfs/</code></td>
                <td>~310 MB</td>
                <td>Eskom annual integrated reports and AFS PDFs (2010–2025)</td>
                <td><a href="/data/warehouse/integrated_results/pdfs/">Browse</a></td>
              </tr>
              <tr>
                <td><code>warehouse/media_presentations/pdfs/</code></td>
                <td>~110 MB</td>
                <td>Media-room presentation PDFs</td>
                <td><a href="/data/warehouse/media_presentations/pdfs/">Browse</a></td>
              </tr>
              <tr>
                <td><code>sources/eskom.sqlite</code></td>
                <td>~40 MB</td>
                <td>Bulk hourly grid metrics 2017–present (built from monthly CSV exports)</td>
                <td><a href="/data/sources/eskom.sqlite">Download</a></td>
              </tr>
              <tr>
                <td><code>sources/eskom_metrics.sqlite</code></td>
                <td>~40 MB</td>
                <td>Monthly EAF/PCLF/UCLF/OCLF snapshots from legacy scraper</td>
                <td><a href="/data/sources/eskom_metrics.sqlite">Download</a></td>
              </tr>
              <tr>
                <td><code>sources/eskom_metrics_extra.sqlite</code></td>
                <td>~3 MB</td>
                <td>Legacy demand/capacity hourly data, 2022–2026</td>
                <td><a href="/data/sources/eskom_metrics_extra.sqlite">Download</a></td>
              </tr>
            </tbody>
          </table>
          <p className={styles.lede} style={{marginTop: '0.75rem'}}>
            DuckDB files can be opened with <a href="https://duckdb.org" target="_blank" rel="noopener noreferrer">DuckDB</a>{' '}
            (<code>duckdb eskom.duckdb</code>) or any DuckDB-compatible client (Python, R, etc.).
          </p>
        </section>

        {!loaded && <p className={styles.lede}>Loading…</p>}

        {SECTION_ORDER.map((section) => {
          const graphs = catalog.filter((g) => g.section === section);
          if (!graphs.length) return null;
          return (
            <section key={section} className={styles.section}>
              <h2>{section}</h2>
              <div className={styles.tableScroll}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Graph</th>
                      <th>Portal page</th>
                      <th>Source links</th>
                      <th>PowerBI new data</th>
                      <th>CSV new data</th>
                      <th>Data up to</th>
                    </tr>
                  </thead>
                  <tbody>
                    {graphs.map((g) => (
                      <tr key={g.slug}>
                        <td>{g.name}</td>
                        <td>
                          <a href={g.page} target="_blank" rel="noopener noreferrer">
                            Open
                          </a>
                        </td>
                        <td>
                          <SourceLinks csv={g.csv} powerbi={g.powerbi} />
                        </td>
                        <td>
                          {g.powerbi.published
                            ? <span className={styles.fresh}>{g.powerbi.published}</span>
                            : <span className={styles.none}>—</span>}
                        </td>
                        <td>
                          {g.csv.published
                            ? <span className={styles.fresh}>{g.csv.published}</span>
                            : <span className={styles.none}>—</span>}
                        </td>
                        <td>
                          <LatestCell graph={g} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}

        {reports.length > 0 && (
          <section className={styles.section}>
            <h2>NTCSA Weekly System Status Reports</h2>
            <p className={styles.lede}>
              Weekly adequacy PDFs from the{' '}
              <a
                href="https://www.ntcsa.co.za/system-status-reports/"
                target="_blank"
                rel="noopener noreferrer">
                NTCSA system status reports
              </a>{' '}
              page. We pull each PDF directly (via the site&rsquo;s WordPress feed,
              bypassing the JavaScript viewer), extract the rooftop-PV table and
              the 52-week adequacy outlook.
            </p>
            <div className={styles.tableScroll}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Week</th>
                    <th>Covers</th>
                    <th>Report</th>
                    <th>Grabbed</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((r) => (
                    <tr key={r.name}>
                      <td>{r.year && r.week ? `${r.year} W${r.week}` : r.name}</td>
                      <td className={styles.fresh}>{r.period || '–'}</td>
                      <td>
                        {r.pdfUrl ? (
                          <a href={r.pdfUrl} target="_blank" rel="noopener noreferrer">
                            PDF
                          </a>
                        ) : (
                          <span className={styles.none}>—</span>
                        )}
                      </td>
                      <td className={styles.fresh}>{fmtDate(r.grabbedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </Layout>
  );
}
