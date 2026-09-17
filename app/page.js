import { list } from '@vercel/blob';
import ClientHome from './client';

export const dynamic = 'force-dynamic';

export default async function Home() {
  // Blob public URLs are CDN-cached, so list() metadata — not a HEAD on the
  // public URL — is the real last sync time. Missing blob shows "Never".
  let timestamp = null;
  try {
    const { blobs } = await list({ prefix: process.env.BLOB_PATH });
    if (blobs.length > 0) timestamp = blobs[0].uploadedAt;
  } catch {
    // Store unreachable or unconfigured — render "Never" rather than crash
  }

  return <ClientHome lastModified={timestamp} />;
}
