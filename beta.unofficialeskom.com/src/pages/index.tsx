import type {ReactNode} from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';

import styles from './index.module.css';

const SECTIONS: Array<{to: string; title: string; blurb: string}> = [
  {
    to: '/status',
    title: 'Status',
    blurb:
      'Where the grid is right now: availability and outage dials, Eskom’s own 52-week adequacy outlook, and automatically detected incidents.',
  },
  {
    to: '/dashboard',
    title: 'Dashboard',
    blurb:
      'Live charts over the full history: generation by source, planned and unplanned outages, demand vs capacity, peaking plant use, and rooftop solar.',
  },
  {
    to: '/monthly',
    title: 'Long term',
    blurb:
      'Monthly averages from 2017 to today, with year-over-year comparisons — the slow trends behind the daily noise.',
  },
  {
    to: '/updates',
    title: 'Analysis',
    blurb:
      'Written monthly recaps of what the data showed: what changed, what stood out, and what it means.',
  },
  {
    to: '/eskom-source-data',
    title: 'Source data',
    blurb:
      'Every file we ingest from Eskom — what each contains, how fresh it is, and which charts are built from it.',
  },
];

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout title="Unofficial Eskom" description={siteConfig.tagline}>
      <main className="container margin-vert--lg" style={{maxWidth: 880}}>
        <h1>Unofficial Eskom</h1>
        <p>
          <a
            href="https://www.eskom.co.za"
            target="_blank"
            rel="noopener noreferrer">
            Eskom
          </a>{' '}
          is South Africa&rsquo;s electricity public utility. It publishes a
          surprising amount of data about the state of the national grid &mdash;
          hourly generation by source, outage levels, demand forecasts, weekly
          system adequacy reports &mdash; but it&rsquo;s scattered across PowerBI
          embeds, CSV exports and PDFs, and much of it is badly presented or
          hard to find. That matters because of the ongoing{' '}
          <a
            href="https://en.wikipedia.org/wiki/South_African_energy_crisis"
            target="_blank"
            rel="noopener noreferrer">
            energy crisis
          </a>
          : whether the lights stay on is a question the published numbers can
          actually answer, if you can read them.
        </p>
        <p>
          This site collects that data automatically &mdash; most of it
          refreshed every hour &mdash; keeps the full history back to 2017, and
          presents it as fast, readable dashboards. Everything is built from
          Eskom&rsquo;s own published numbers, and every chart links back to the
          exact source files it was built from.
        </p>

        <div className={styles.cardGrid}>
          {SECTIONS.map((s) => (
            <Link key={s.to} to={s.to} className={styles.tabCard}>
              <h3>{s.title}</h3>
              <p>{s.blurb}</p>
            </Link>
          ))}
        </div>

        <h2>Sources</h2>
        <ul>
          <li>
            Eskom{' '}
            <a
              href="https://www.eskom.co.za/dataportal/"
              target="_blank"
              rel="noopener noreferrer">
              data portal
            </a>
          </li>
          <li>
            Eskom{' '}
            <a
              href="https://www.eskom.co.za/investors/integrated-results/"
              target="_blank"
              rel="noopener noreferrer">
              integrated results
            </a>
          </li>
          <li>
            Eskom{' '}
            <a
              href="https://www.eskom.co.za/media-room/presentations/"
              target="_blank"
              rel="noopener noreferrer">
              presentations
            </a>
          </li>
          <li>
            Eskom{' '}
            <a
              href="https://www.eskom.co.za/eskom-divisions/tx/system-adequacy-reports/"
              target="_blank"
              rel="noopener noreferrer">
              weekly system status reports
            </a>
          </li>
        </ul>
        <p>
          <small>Not endorsed by or affiliated with Eskom.</small>
        </p>
      </main>
    </Layout>
  );
}
