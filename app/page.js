import { list } from '@vercel/blob';
import ClientHome from './client';
import { unstable_noStore } from 'next/cache';

export default async function Home() {
  unstable_noStore();
  
  const { blobs } = await list({ prefix: process.env.BLOB_PATH });
  const timestamp = blobs.length > 0 ? (blobs[0]?.updatedAt || blobs[0]?.uploadedAt) : null;

  return <ClientHome initialLastModified={timestamp} />;
}