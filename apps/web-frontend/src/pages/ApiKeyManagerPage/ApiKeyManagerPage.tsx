/**
 * ApiKeyManagerPage -- Manage user API keys for X-API-Key authentication.
 *
 * Shows existing keys in a table (masked), allows creating new keys
 * (full key shown once), and revoking existing keys with confirmation.
 *
 * Route: /api-keys (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ApiKeyEntry {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: number;
  last_used_at: number | null;
}

interface CreateApiKeyResponse extends ApiKeyEntry {
  api_key: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string; REACT_APP_API_URL?: string } }).env
      ?.VITE_API_URL ||
    (import.meta as unknown as { env?: { REACT_APP_API_URL?: string } }).env?.REACT_APP_API_URL ||
    'http://localhost:8000'
  );
}

function getAuthToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function maskKey(prefix: string): string {
  if (prefix.length <= 8) return `${prefix}...`;
  return `${prefix.slice(0, 8)}...`;
}

function formatDate(epoch: number): string {
  return new Date(epoch * 1000).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ApiKeyManagerPage: React.FC = () => {
  const [keys, setKeys] = useState<ApiKeyEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create form state
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);

  // Newly created key (shown once)
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Delete confirmation
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const fetchKeys = useCallback(async () => {
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/auth/api-keys`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError('Failed to load API keys');
        return;
      }
      const data: { items: ApiKeyEntry[] } = await resp.json();
      setKeys(data.items ?? []);
    } catch {
      setError('Network error loading API keys');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = newKeyName.trim();
      if (!trimmed) return;

      setCreating(true);
      setError(null);
      setRevealedKey(null);
      setCopied(false);

      try {
        const resp = await fetch(`${getBaseUrl()}/api/v1/auth/api-keys`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: trimmed }),
        });

        if (!resp.ok) {
          setError('Failed to create API key');
          return;
        }

        const created: CreateApiKeyResponse = await resp.json();
        setRevealedKey(created.api_key);
        setNewKeyName('');
        await fetchKeys();
      } catch {
        setError('Network error creating API key');
      } finally {
        setCreating(false);
      }
    },
    [newKeyName, fetchKeys],
  );

  const handleDelete = useCallback(
    async (keyId: string) => {
      setError(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/api/v1/auth/api-keys/${keyId}`, {
          method: 'DELETE',
          headers: authHeaders(),
        });
        if (!resp.ok) {
          setError('Failed to revoke API key');
          return;
        }
        setKeys((prev) => prev.filter((k) => k.id !== keyId));
        setConfirmDeleteId(null);
      } catch {
        setError('Network error revoking API key');
      }
    },
    [],
  );

  const handleCopyKey = useCallback(async () => {
    if (!revealedKey) return;
    try {
      await navigator.clipboard.writeText(revealedKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API not available -- user can copy manually
    }
  }, [revealedKey]);

  if (loading) {
    return (
      <MainLayout title="API Keys">
        <div
          className="flex items-center justify-center py-20 text-slate-400"
          aria-label="Loading API keys"
        >
          Loading...
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout title="API Keys">
      <h1 className="mb-6 text-2xl font-bold text-slate-100" data-testid="page-title">
        API Key Management
      </h1>

      {/* Error banner */}
      {error && (
        <div
          className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
          data-testid="error-banner"
        >
          {error}
        </div>
      )}

      {/* Create form */}
      <form onSubmit={handleCreate} className="mb-6 flex items-end gap-3" data-testid="create-form">
        <div className="flex-1">
          <label htmlFor="key-name" className="mb-1 block text-sm text-slate-400">
            Key Name
          </label>
          <input
            id="key-name"
            type="text"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder="e.g. CI/CD Pipeline"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
            data-testid="key-name-input"
            maxLength={100}
            required
          />
        </div>
        <button
          type="submit"
          disabled={creating || !newKeyName.trim()}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          data-testid="create-btn"
        >
          {creating ? 'Creating...' : 'Create Key'}
        </button>
      </form>

      {/* Revealed key banner */}
      {revealedKey && (
        <div
          className="mb-6 rounded border border-green-700 bg-green-900/30 p-4"
          data-testid="revealed-key-banner"
        >
          <p className="mb-2 text-sm font-semibold text-green-300">
            Key created! Copy it now -- it will not be shown again.
          </p>
          <div className="flex items-center gap-2">
            <code
              className="flex-1 rounded bg-slate-900 px-3 py-2 font-mono text-sm text-green-200"
              data-testid="revealed-key-value"
            >
              {revealedKey}
            </code>
            <button
              onClick={handleCopyKey}
              className="rounded bg-green-700 px-3 py-2 text-sm text-white hover:bg-green-600"
              data-testid="copy-key-btn"
            >
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      {/* Key list */}
      {keys.length === 0 ? (
        <div className="py-20 text-center text-slate-500" data-testid="empty-state">
          No API keys yet. Create one above to get started.
        </div>
      ) : (
        <div className="overflow-auto">
          <table
            className="w-full text-left text-sm text-slate-200"
            data-testid="keys-table"
          >
            <thead className="border-b border-slate-700 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Key</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2">Last Used</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr
                  key={key.id}
                  className="border-b border-slate-800"
                  data-testid="key-row"
                >
                  <td className="px-3 py-2 font-medium">{key.name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-400" data-testid="masked-key">
                    {maskKey(key.key_prefix)}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs">
                    {formatDate(key.created_at)}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-400">
                    {key.last_used_at ? formatDate(key.last_used_at) : 'Never'}
                  </td>
                  <td className="px-3 py-2">
                    {confirmDeleteId === key.id ? (
                      <span className="flex items-center gap-2">
                        <span className="text-xs text-red-400">Revoke?</span>
                        <button
                          onClick={() => handleDelete(key.id)}
                          className="rounded bg-red-700 px-2 py-1 text-xs text-white hover:bg-red-600"
                          data-testid="confirm-delete-btn"
                        >
                          Yes
                        </button>
                        <button
                          onClick={() => setConfirmDeleteId(null)}
                          className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
                          data-testid="cancel-delete-btn"
                        >
                          No
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setConfirmDeleteId(key.id)}
                        className="rounded bg-red-800/60 px-2 py-1 text-xs text-red-300 hover:bg-red-700"
                        data-testid="delete-btn"
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </MainLayout>
  );
};

export default ApiKeyManagerPage;
