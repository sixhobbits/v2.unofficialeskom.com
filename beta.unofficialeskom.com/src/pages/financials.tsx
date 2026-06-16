import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import BrowserOnly from '@docusaurus/BrowserOnly';

export default function FinancialsPage(): ReactNode {
  return (
    <Layout
      title="Financials"
      description="Eskom annual financial results: revenue, EBITDA, and net profit from 2012–2025 AFS PDFs">
      <BrowserOnly fallback={<div style={{padding: '2rem'}}>Loading…</div>}>
        {() => {
          const Financials = require('@site/src/components/Financials').default;
          return <Financials />;
        }}
      </BrowserOnly>
    </Layout>
  );
}
