'use client';
import { useState } from 'react';
import { startSync } from './actions';
import { getRelativeTimeString } from './utils';

export default function ClientHome({ lastModified, isOverdue = false }) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isStarted, setIsStarted] = useState(false);

  const handleSync = async () => {
    setIsLoading(true);
    setError(null);
    setIsStarted(false);

    try {
      const startError = await startSync();
      if (startError) {
        setError(startError);
      } else {
        setIsStarted(true);
      }
    } catch {
      // The request never reached the server action
      setError('Could not reach the server');
    } finally {
      setIsLoading(false);
    }
  };

  const buttonStyle = {
    padding: '0.75rem 1.5rem',
    borderRadius: '6px',
    border: 'none',
    backgroundColor: isStarted ? '#000' : '#333',
    color: 'white',
    cursor: isLoading ? 'not-allowed' : 'pointer',
    opacity: isLoading ? 0.7 : 1,
    fontSize: '1rem',
    fontWeight: 700,
    minWidth: '120px',
  };

  const buttonLabel = isLoading ? 'Starting...' : isStarted ? 'Sync started' : 'Sync Now';

  const formattedTime = lastModified ? getRelativeTimeString(lastModified) : 'Never';

  // The sync runs in the background, so its result shows up on a later visit
  let statusNote = null;
  if (isStarted) {
    statusNote = 'Reload this page in a minute or two to see the new time.';
  } else if (isOverdue) {
    statusNote = "No sync since then. Check the schedule's runs in the Vercel dashboard.";
  }

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
        color: isOverdue ? '#c00' : '#333',
        fontWeight: 400,
        margin: 0,
      }}>Last Synced: {formattedTime}</p>
      {statusNote && (
        <p style={{
          fontSize: '0.95rem',
          color: isStarted ? '#666' : '#c00',
          margin: 0,
          maxWidth: '80%',
          textAlign: 'center',
        }}>{statusNote}</p>
      )}
      <button onClick={handleSync} disabled={isLoading} style={buttonStyle}>
        {buttonLabel}
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