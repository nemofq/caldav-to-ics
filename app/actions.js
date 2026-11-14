'use server';

import { Schedules } from '@vercel/schedules';
import { getLastSyncTime } from './lastSync';

// The schedule's name in vercel.json
const SCHEDULE = 'sync';

// Anyone who can open the page can press Sync Now, so runs are spaced out. A
// failed sync uploads nothing, so it can be retried straight away.
const COOLDOWN_MINUTES = 10;

// `pnpm run dev` has no scheduler: it serves the sync function here instead
const DEV_SYNC_URL = 'http://127.0.0.1:5328/api/sync';

// Returns an error message, or null once the sync has been started
export async function startSync() {
  try {
    const lastSync = await getLastSyncTime();
    if (lastSync && Date.now() - new Date(lastSync).getTime() < COOLDOWN_MINUTES * 60_000) {
      return `Already synced in the last ${COOLDOWN_MINUTES} minutes`;
    }

    if (process.env.NODE_ENV === 'development') {
      const response = await fetch(DEV_SYNC_URL, { method: 'POST' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    } else {
      // The sync function is private, so the page asks the scheduler to run
      // it. This returns once the run is accepted, not when the sync is done.
      await Schedules.invoke({ name: SCHEDULE });
    }
    return null;
  } catch (error) {
    console.error('Could not start the sync:', error);
    return 'Could not start the sync';
  }
}
