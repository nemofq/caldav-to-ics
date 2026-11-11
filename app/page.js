import { list } from '@vercel/blob';
import ClientHome from './client';
import { isSyncOverdue } from './utils';

export const dynamic = 'force-dynamic';

// Written by /api/sync next to the ICS after every authorized attempt
const STATUS_SUFFIX = '.status.json';

// Only these fields reach the browser: the status file's URL contains the
// secret BLOB_PATH, so it is read here and never passed on
async function readStatus(blob) {
  try {
    const response = await fetch(blob.url, { cache: 'no-store' });
    if (!response.ok) return null;
    const data = await response.json();
    return {
      attemptedAt: typeof data.attempted_at === 'string' ? data.attempted_at : null,
      ok: data.ok === true,
      error: typeof data.error === 'string' ? data.error : null,
      skippedCalendars: Number.isInteger(data.skipped_calendars) ? data.skipped_calendars : 0,
    };
  } catch {
    return null;
  }
}

export default async function Home() {
  // Blob public URLs are CDN-cached, so list() metadata — not a HEAD on the
  // public URL — is the real last sync time. Missing blob shows "Never".
  let timestamp = null;
  let status = null;
  const blobPath = process.env.BLOB_PATH;
  try {
    if (blobPath) {
      const { blobs } = await list({ prefix: blobPath });
      const ics = blobs.find((blob) => blob.pathname === blobPath);
      const statusBlob = blobs.find((blob) => blob.pathname === blobPath + STATUS_SUFFIX);
      if (ics) timestamp = ics.uploadedAt;
      if (statusBlob) status = await readStatus(statusBlob);
    }
  } catch {
    // Store unreachable or unconfigured — render "Never" rather than crash
  }

  // Decided on the server, per request, so the browser renders the same answer
  const isOverdue = timestamp !== null && isSyncOverdue(timestamp);

  // Only whether a secret is required reaches the browser, never its value
  const authRequired = Boolean(process.env.CRON_SECRET);

  return (
    <ClientHome
      lastModified={timestamp}
      isOverdue={isOverdue}
      status={status}
      authRequired={authRequired}
    />
  );
}
