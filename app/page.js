import ClientHome from './client';
import { getLastSyncTime } from './lastSync';
import { isSyncOverdue } from './utils';

export const dynamic = 'force-dynamic';

export default async function Home() {
  let timestamp = null;
  try {
    timestamp = await getLastSyncTime();
  } catch {
    // Store unreachable or unconfigured — render "Never" rather than crash
  }

  // Decided on the server, per request, so the browser renders the same answer
  const isOverdue = timestamp !== null && isSyncOverdue(timestamp);

  return <ClientHome lastModified={timestamp} isOverdue={isOverdue} />;
}
