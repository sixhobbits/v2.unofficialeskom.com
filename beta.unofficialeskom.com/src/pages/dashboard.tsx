import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import BrowserOnly from '@docusaurus/BrowserOnly';

export default function DashboardPage(): ReactNode {
  return (
    <Layout
      title="Dashboard"
      description="Live Eskom generation, outage and renewables dashboard">
      <BrowserOnly fallback={<div style={{padding: '2rem'}}>Loading…</div>}>
        {() => {
          const Dashboard = require('@site/src/components/Dashboard').default;
          return <Dashboard />;
        }}
      </BrowserOnly>
    </Layout>
  );
}
