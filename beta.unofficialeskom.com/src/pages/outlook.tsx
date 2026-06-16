import type {ReactNode} from 'react';
import {Redirect} from '@docusaurus/router';

// The Outlook tab was renamed to Status; keep old links working.
export default function OutlookRedirect(): ReactNode {
  return <Redirect to="/status" />;
}
