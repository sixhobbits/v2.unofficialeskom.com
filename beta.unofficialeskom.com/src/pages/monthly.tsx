import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import BrowserOnly from '@docusaurus/BrowserOnly';

export default function MonthlyPage(): ReactNode {
  return (
    <Layout
      title="Long term"
      description="Monthly-aggregate Eskom metrics over the full history — a clone of the long-term dashboard">
      <BrowserOnly fallback={<div style={{padding: '2rem'}}>Loading…</div>}>
        {() => {
          const Monthly = require('@site/src/components/Monthly').default;
          return <Monthly />;
        }}
      </BrowserOnly>
    </Layout>
  );
}
