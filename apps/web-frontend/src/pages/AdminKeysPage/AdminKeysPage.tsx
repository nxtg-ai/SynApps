/**
 * AdminKeysPage — Admin API Key Registry (N-100).
 *
 * Covers:
 *   GET    /api/v1/admin/keys           → list admin keys
 *   POST   /api/v1/admin/keys           → create admin key (name, scopes, rate_limit)
 *   DELETE /api/v1/admin/keys/{key_id}  → delete/revoke admin key
 *
 * All endpoints require SYNAPPS_MASTER_KEY via X-API-Key header.
 *
 * Route: /admin-keys (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AdminKey {
  id: string;
  name: string;
  scopes?: string[];
  rate_limit?: number | null;
  created_at?: string | number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ||
    'http://localhost:8000'
  );
}

function masterHeaders(masterKey: string): Record<string, string> {
  return masterKey ? { 'X-API-Key': masterKey } : {};
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const AdminKeysPage: React.FC = () => {
  const [masterKey, setMasterKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [keys, setKeys] = useState<AdminKey[]>([]);

  // Create form
  const [createName, setCreateName] = useState('');
  const [createScopes, setCreateScopes] = useState('read write admin');
  const [createRateLimit, setCreateRateLimit] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<AdminKey | null>(null);

  // Delete
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Load keys
  // ---------------------------------------------------------------------------

  const loadKeys = useCallback(async () => {
    if (!masterKey.trim()) return;
    setLoading(true);
    setListError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/admin/keys`, {
        headers: masterHeaders(masterKey),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setListError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      const data = await resp.json();
      setKeys(Array.isArray(data) ? data : Array.isArray(data.keys) ? data.keys : []);
    } catch {
      setListError('Network error loading admin keys');
    } finally {
      setLoading(false);
    }
  }, [masterKey]);

  useEffect(() => {
    if (masterKey.trim()) {
      loadKeys();
    }
  }, [loadKeys, masterKey]);

  // ---------------------------------------------------------------------------
  // Create
  // ---------------------------------------------------------------------------

  const handleCreate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!createName.trim() || !masterKey.trim()) return;
      setCreating(true);
      setCreateError(null);
      setNewKey(null);
      try {
        const body: Record<string, unknown> = {
          name: createName.trim(),
          scopes: createScopes
            .split(/\s+/)
            .map((s) => s.trim())
            .filter(Boolean),
        };
        if (createRateLimit.trim()) body.rate_limit = Number(createRateLimit);

        const resp = await fetch(`${getBaseUrl()}/admin/keys`, {
          method: 'POST',
          headers: { ...masterHeaders(masterKey), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setCreateError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const created: AdminKey = await resp.json();
        setNewKey(created);
        setKeys((prev) => [created, ...prev]);
        setCreateName('');
        setCreateRateLimit('');
      } catch {
        setCreateError('Network error creating admin key');
      } finally {
        setCreating(false);
      }
    },
    [createName, createScopes, createRateLimit, masterKey],
  );

  // ---------------------------------------------------------------------------
  // Delete
  // ---------------------------------------------------------------------------

  const handleDelete = useCallback(
    async (keyId: string) => {
      setDeletingId(keyId);
      setDeleteError(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/admin/keys/${encodeURIComponent(keyId)}`,
          { method: 'DELETE', headers: masterHeaders(masterKey) },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setDeleteError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setKeys((prev) => prev.filter((k) => k.id !== keyId));
      } catch {
        setDeleteError('Network error deleting admin key');
      } finally {
        setDeletingId(null);
      }
    },
    [masterKey],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Admin Keys">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Admin API Keys
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Master-key-protected admin API key registry (read, write, admin scopes).
        </p>
      </div>

      {/* Master key + refresh */}
      <div className="mb-6 flex items-center gap-3">
        <input
          type="password"
          value={masterKey}
          onChange={(e) => setMasterKey(e.target.value)}
          placeholder="SYNAPPS_MASTER_KEY"
          className="w-64 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
          data-testid="master-key-input"
        />
        <button
          onClick={loadKeys}
          disabled={loading || !masterKey.trim()}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* Create form */}
      <section
        className="mb-6 rounded border border-slate-700 bg-slate-800/30 p-4"
        data-testid="create-section"
      >
        <h2 className="mb-3 text-sm font-semibold text-slate-300">Create Admin Key</h2>
        <form onSubmit={handleCreate} className="space-y-3" data-testid="create-form">
          <div className="flex flex-wrap gap-3">
            <input
              type="text"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="Key name"
              className="w-40 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="create-name-input"
            />
            <input
              type="text"
              value={createScopes}
              onChange={(e) => setCreateScopes(e.target.value)}
              placeholder="Scopes (read write admin)"
              className="w-48 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="create-scopes-input"
            />
            <input
              type="number"
              value={createRateLimit}
              onChange={(e) => setCreateRateLimit(e.target.value)}
              placeholder="Rate limit (req/min)"
              className="w-36 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="create-rate-limit-input"
            />
          </div>
          <button
            type="submit"
            disabled={creating || !createName.trim() || !masterKey.trim()}
            className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
            data-testid="create-btn"
          >
            {creating ? 'Creating…' : 'Create Key'}
          </button>
        </form>
        {createError && (
          <p className="mt-2 text-sm text-red-400" data-testid="create-error">
            {createError}
          </p>
        )}
        {newKey && (
          <div
            className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
            data-testid="create-success"
          >
            <>
              <p className="mb-1 font-semibold text-emerald-400">Admin key created!</p>
              <p className="text-slate-300">
                ID:{' '}
                <span className="font-mono" data-testid="new-key-id">
                  {newKey.id}
                </span>
              </p>
              {(newKey as Record<string, unknown>).key_value && (
                <p className="mt-1 text-slate-300">
                  Key value (shown once):{' '}
                  <span className="font-mono text-yellow-300" data-testid="new-key-value">
                    {String((newKey as Record<string, unknown>).key_value)}
                  </span>
                </p>
              )}
            </>
          </div>
        )}
      </section>

      {/* Key list */}
      {listError && (
        <p className="mb-4 text-sm text-red-400" data-testid="list-error">
          {listError}
        </p>
      )}
      {deleteError && (
        <p className="mb-4 text-sm text-red-400" data-testid="delete-error">
          {deleteError}
        </p>
      )}
      {loading && keys.length === 0 && (
        <p className="text-xs text-slate-500" data-testid="list-loading">
          Loading…
        </p>
      )}
      {!loading && keys.length === 0 && !listError && masterKey.trim() && (
        <p className="text-xs text-slate-500" data-testid="no-keys">
          No admin keys found.
        </p>
      )}
      {keys.length > 0 && (
        <div className="overflow-x-auto" data-testid="keys-table">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-500">
                <th className="pb-2 pr-4 font-medium">ID</th>
                <th className="pb-2 pr-4 font-medium">Name</th>
                <th className="pb-2 pr-4 font-medium">Scopes</th>
                <th className="pb-2 pr-4 font-medium">Rate Limit</th>
                <th className="pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr
                  key={k.id}
                  className="border-b border-slate-700/40"
                  data-testid="key-row"
                >
                  <td className="py-2 pr-4 font-mono text-slate-500">{k.id}</td>
                  <td className="py-2 pr-4 text-slate-300">{k.name}</td>
                  <td className="py-2 pr-4 text-slate-400">
                    {Array.isArray(k.scopes) ? k.scopes.join(', ') : '—'}
                  </td>
                  <td className="py-2 pr-4 text-slate-400">
                    {k.rate_limit != null ? `${k.rate_limit} rpm` : 'default'}
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => handleDelete(k.id)}
                      disabled={deletingId === k.id}
                      className="rounded bg-red-900/60 px-2 py-0.5 text-xs text-red-300 hover:bg-red-900 disabled:opacity-50"
                      data-testid="delete-btn"
                    >
                      {deletingId === k.id ? 'Deleting…' : 'Delete'}
                    </button>
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

export default AdminKeysPage;
