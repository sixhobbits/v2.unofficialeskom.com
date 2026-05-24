import type {ReactNode} from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout title="Unofficial Eskom" description={siteConfig.tagline}>
      <main className="container margin-vert--lg" style={{maxWidth: 820}}>
        <h1>Unofficial Eskom</h1>
        <p>
          <a
            href="https://www.eskom.co.za"
            target="_blank"
            rel="noopener noreferrer">
            Eskom
          </a>{' '}
          is South Africa&rsquo;s electricity public utility. It publishes some
          information about the ongoing{' '}
          <a
            href="https://en.wikipedia.org/wiki/South_African_energy_crisis"
            target="_blank"
            rel="noopener noreferrer">
            energy crisis
          </a>
          , but the official data is often badly presented or hard to find.
          This site aggregates the most useful information and makes it easier
          to find, nicer to look at, and generally more accessible.
        </p>
        <p>
          See the{' '}
          <Link to="/dashboard">live generation dashboard</Link> for the
          current state of the grid. It refreshes daily from the Eskom data
          portal and other public sources.
        </p>
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
