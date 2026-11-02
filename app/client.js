'use client';
import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getRelativeTimeString } from './utils';

// Hidden from view but still in the layout, so password managers associate
// the saved credential with a username (display:none fields can be ignored)
const visuallyHidden = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

export default function ClientHome({ lastModified, authRequired = false }) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isSynced, setIsSynced] = useState(false);
  // With CRON_SECRET set, /api/sync needs "Authorization: Bearer <secret>".
  // The secret is typed (or autofilled) into a real form so the browser's
  // password manager can save it; this page never stores it anywhere.
  const [showSecretForm, setShowSecretForm] = useState(authRequired);
  const secretInput = useRef(null);
  const router = useRouter();

  // Returns 'ok', 'unauthorized' or 'error'
  const requestSync = async (secret) => {
    setIsLoading(true);
    setError(null);
    setIsSynced(false);

    try {
      const response = await fetch('/api/sync', {
        method: 'POST',
        headers: secret ? { Authorization: `Bearer ${secret}` } : {},
      });

      if (response.status === 401) return 'unauthorized';

      // A crashed function returns Vercel's HTML error page, not JSON
      const isJson = response.headers.get('content-type')?.includes('application/json');
      const data = isJson ? await response.json() : null;

      if (!response.ok) {
        throw new Error(data?.message || `HTTP ${response.status}`);
      }

      setIsSynced(true);
      router.refresh();
      return 'ok';

    } catch (err) {
      setError(err.message);
      return 'error';
    } finally {
      setIsLoading(false);
    }
  };

  const handleSync = async () => {
    if (authRequired) {
      setShowSecretForm(true);
      return;
    }
    // Server didn't say a secret is needed, but it may still ask for one
    if (await requestSync() === 'unauthorized') {
      setShowSecretForm(true);
    }
  };

  const handleSecretSubmit = async (event) => {
    event.preventDefault();
    const input = secretInput.current;
    const result = await requestSync(input.value);

    if (result === 'ok') {
      // Clearing and removing the form after a successful submit is what
      // password managers treat as a successful sign-in, so they offer to save
      input.value = '';
      setShowSecretForm(false);
    } else if (result === 'unauthorized') {
      setError('Wrong CRON_SECRET');
      input.select();
    }
  };

  const buttonStyle = {
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
  };

  const buttonLabel = isLoading ? 'Syncing...' : isSynced ? 'Synced' : 'Sync Now';

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
      {showSecretForm ? (
        // method="post" keeps the secret out of the URL if the form is
        // submitted before the page's JavaScript has loaded
        <form
          method="post"
          onSubmit={handleSecretSubmit}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.75rem',
          }}
        >
          <input
            type="text"
            name="username"
            autoComplete="username"
            value="cron"
            readOnly
            tabIndex={-1}
            aria-hidden="true"
            style={visuallyHidden}
          />
          <label htmlFor="cron-secret" style={{ fontSize: '1rem', color: '#333' }}>
            CRON_SECRET
          </label>
          <input
            id="cron-secret"
            ref={secretInput}
            type="password"
            name="password"
            autoComplete="current-password"
            required
            style={{
              padding: '0.6rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid #ccc',
              fontSize: '1rem',
              width: '16rem',
              maxWidth: '100%',
            }}
          />
          <button type="submit" disabled={isLoading} style={buttonStyle}>
            {buttonLabel}
          </button>
        </form>
      ) : (
        <button onClick={handleSync} disabled={isLoading} style={buttonStyle}>
          {buttonLabel}
        </button>
      )}
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