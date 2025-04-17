'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { getRelativeTimeString } from './utils';

export default function ClientHome({ lastModified }) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isSynced, setIsSynced] = useState(false);
  const router = useRouter();

  const handleSync = async () => {
    setIsLoading(true);
    setError(null);
    setIsSynced(false);

    try {
      const response = await fetch('/api/sync', {
        method: 'POST',
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.message || 'Failed to sync');
      }
      
      setIsSynced(true);
      router.refresh();

    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const formattedTime = lastModified ? getRelativeTimeString(lastModified) : 'Never';

  return (
    <main style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      minHeight: '100dvh',
      width: '100%',
      margin: 0,
      padding: '2rem',
      gap: '1.5rem',
      backgroundColor: '#fff',
      boxSizing: 'border-box',
    }}>
      <h1 style={{
        fontSize: '2rem',
        fontWeight: 700,
        color: '#333',
        margin: 0,
      }}>CalDAV to ICS</h1>
      <p style={{
        fontSize: '1.1rem',
        color: '#333',
        fontWeight: 400,
      }}>Last Synced: {formattedTime}</p>
      <button
        onClick={handleSync}
        disabled={isLoading}
        style={{
          padding: '0.75rem 1.5rem',
          borderRadius: '6px',
          border: 'none',
          backgroundColor: isSynced ? '#000' : '#333',
          color: 'white',
          cursor: isLoading ? 'not-allowed' : 'pointer',
          opacity: isLoading ? 0.7 : 1,
          fontSize: '1rem',
          fontWeight: 700,
          minWidth: '120px',
        }}
      >
        {isLoading ? 'Syncing...' : isSynced ? 'Synced' : 'Sync Now'}
      </button>
      {error && (
        <p style={{ 
          color: '#ff0000', 
          maxWidth: '80%', 
          textAlign: 'center',
          fontSize: '1rem',
          fontWeight: 500,
        }}>Error: {error}</p>
      )}
    </main>
  );
} 