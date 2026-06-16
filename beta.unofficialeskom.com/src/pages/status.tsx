import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import BrowserOnly from '@docusaurus/BrowserOnly';

export default function StatusPage(): ReactNode {
  return (
    <Layout
      title="Status"
      description="Eskom grid status: current EAF and outages, official demand forecast, recent peaking use, and live incident detection">
      <BrowserOnly fallback={<div style={{padding: '2rem'}}>Loading…</div>}>
        {() => {
          const Outlook = require('@site/src/components/Outlook').default;
          return <Outlook />;
        }}
      </BrowserOnly>
    </Layout>
  );
}
