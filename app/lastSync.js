import { list } from '@vercel/blob';

// Upload time of the ICS, or null if it doesn't exist yet. Blob public URLs
// are CDN-cached, so list() metadata, not a HEAD on the public URL, is the
// real last sync time.
export async function getLastSyncTime() {
  const blobPath = process.env.BLOB_PATH;
  if (!blobPath) return null;
  const { blobs } = await list({ prefix: blobPath });
  return blobs.find((blob) => blob.pathname === blobPath)?.uploadedAt ?? null;
}
