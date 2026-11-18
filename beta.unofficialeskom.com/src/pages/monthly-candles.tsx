import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import Head from '@docusaurus/Head';
import BrowserOnly from '@docusaurus/BrowserOnly';

// Experimental and deliberately unlinked: not in the navbar, not indexed.
export default function MonthlyCandlesPage(): ReactNode {
  return (
    <Layout title="Candles (experimental)" description="Experimental views of long-term Eskom trends">
      <Head>
        <meta name="robots" content="noindex, nofollow" />
      </Head>
      <BrowserOnly fallback={<div style={{padding: '2rem'}}>Loading…</div>}>
        {() => {
          const Candles = require('@site/src/components/Candles').default;
          return <Candles />;
        }}
      </BrowserOnly>
    </Layout>
  );
}
