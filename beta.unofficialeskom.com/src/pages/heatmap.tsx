import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import BrowserOnly from '@docusaurus/BrowserOnly';

export default function HeatmapPage(): ReactNode {
  return (
    <Layout
      title="Loadshedding Heatmap"
      description="Daily loadshedding stage heatmap calendar 2014–present, from EskomSePush data">
      <BrowserOnly fallback={<div style={{padding: '2rem'}}>Loading…</div>}>
        {() => {
          const Heatmap = require('@site/src/components/Heatmap').default;
          return <Heatmap />;
        }}
      </BrowserOnly>
    </Layout>
  );
}
