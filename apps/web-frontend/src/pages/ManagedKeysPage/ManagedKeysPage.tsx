/**
 * ManagedKeysPage — Fernet-Encrypted Managed API Key Manager (N-99).
 *
 * Covers:
 *   GET    /api/v1/managed-keys                         → list keys
 *   POST   /api/v1/managed-keys                         → create key
 *   GET    /api/v1/managed-keys/{id}                    → key detail
 *   POST   /api/v1/managed-keys/{id}/rotate             → rotate key
 *   POST   /api/v1/managed-keys/{id}/revoke             → revoke key
 *   DELETE /api/v1/managed-keys/{id}                    → delete key
 *
 * All endpoints require the SYNAPPS_MASTER_KEY via X-API-Key header.
 *
 * Route: /managed-keys (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ManagedKey {
  id: string;
  name: string;
  scopes?: string[];
  expires_in?: number | null;
  rate_limit?: number | null;
  active?: boolean;
  created_at?: string | number;
  expires_at?: string | number | null;
  usage_count?: number;
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

const ManagedKeysPage: React.FC = () => {
  // ── Master key ─────────────────────────────────────────────────────────────
  const [masterKey, setMasterKey] = useState('');

  // ── List state ─────────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [keys, setKeys] = useState<ManagedKey[]>([]);
  const [includeInactive, setIncludeInactive] = useState(false);

  // ── Create form ────────────────────────────────────────────────────────────
  const [createName, setCreateName] = useState('');
  const [createScopes, setCreateScopes] = useState('read write');
  const [createExpiresIn, setCreateExpiresIn] = useState('');
  const [createRateLimit, setCreateRateLimit] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<ManagedKey | null>(null);

  // ── Selected key + actions ─────────────────────────────────────────────────
  const [selectedKey, setSelectedKey] = useState<ManagedKey | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Rotate
  const [gracePeriod, setGracePeriod] = useState('3600');
  const [rotating, setRotating] = useState(false);
  const [rotateError, setRotateError] = useState<string | null>(null);
  const [rotateResult, setRotateResult] = useState<ManagedKey | null>(null);

  // Revoke / Delete
  const [actionError, setActionError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // ---------------------------------------------------------------------------
  // Load keys
  // ---------------------------------------------------------------------------

  const loadKeys = useCallback(async () => {
    if (!masterKey.trim()) return;
    setLoading(true);
    setListError(null);
    try {
      const params = includeInactive ? '?include_inactive=true' : '';
      const resp = await fetch(`${getBaseUrl()}/managed-keys${params}`, {
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
      setListError('Network error loading managed keys');
    } finally {
      setLoading(false);
    }
  }, [masterKey, includeInactive]);

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
        if (createExpiresIn.trim()) body.expires_in = Number(createExpiresIn);
        if (createRateLimit.trim()) body.rate_limit = Number(createRateLimit);

        const resp = await fetch(`${getBaseUrl()}/managed-keys`, {
          method: 'POST',
          headers: { ...masterHeaders(masterKey), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setCreateError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const created: ManagedKey = await resp.json();
        setNewKey(created);
        setKeys((prev) => [created, ...prev]);
        setCreateName('');
        setCreateExpiresIn('');
        setCreateRateLimit('');
      } catch {
        setCreateError('Network error creating managed key');
      } finally {
        setCreating(false);
      }
    },
    [createName, createScopes, createExpiresIn, createRateLimit, masterKey],
  );

  // ---------------------------------------------------------------------------
  // Load key detail
  // ---------------------------------------------------------------------------

  const loadDetail = useCallback(
    async (keyId: string) => {
      setDetailLoading(true);
      setDetailError(null);
      setSelectedKey(null);
      setRotateResult(null);
      setActionError(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/managed-keys/${encodeURIComponent(keyId)}`, {
          headers: masterHeaders(masterKey),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setDetailError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setSelectedKey(await resp.json());
      } catch {
        setDetailError('Network error loading key detail');
      } finally {
        setDetailLoading(false);
      }
    },
    [masterKey],
  );

  // ---------------------------------------------------------------------------
  // Rotate
  // ---------------------------------------------------------------------------

  const handleRotate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!selectedKey) return;
      setRotating(true);
      setRotateError(null);
      setRotateResult(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/managed-keys/${encodeURIComponent(selectedKey.id)}/rotate`,
          {
            method: 'POST',
            headers: { ...masterHeaders(masterKey), 'Content-Type': 'application/json' },
            body: JSON.stringify({ grace_period: Number(gracePeriod) || 3600 }),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setRotateError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const result: ManagedKey = await resp.json();
        setRotateResult(result);
      } catch {
        setRotateError('Network error rotating key');
      } finally {
        setRotating(false);
      }
    },
    [selectedKey, masterKey, gracePeriod],
  );

  // ---------------------------------------------------------------------------
  // Revoke
  // ---------------------------------------------------------------------------

  const handleRevoke = useCallback(
    async (keyId: string) => {
      setRevoking(true);
      setActionError(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/managed-keys/${encodeURIComponent(keyId)}/revoke`,
          { method: 'POST', headers: masterHeaders(masterKey) },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setActionError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setKeys((prev) =>
          prev.map((k) => (k.id === keyId ? { ...k, active: false } : k)),
        );
        if (selectedKey?.id === keyId) {
          setSelectedKey((prev) => (prev ? { ...prev, active: false } : null));
        }
      } catch {
        setActionError('Network error revoking key');
      } finally {
        setRevoking(false);
      }
    },
    [masterKey, selectedKey],
  );

  // ---------------------------------------------------------------------------
  // Delete
  // ---------------------------------------------------------------------------

  const handleDelete = useCallback(
    async (keyId: string) => {
      setDeleting(true);
      setActionError(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/managed-keys/${encodeURIComponent(keyId)}`,
          { method: 'DELETE', headers: masterHeaders(masterKey) },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setActionError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setKeys((prev) => prev.filter((k) => k.id !== keyId));
        if (selectedKey?.id === keyId) setSelectedKey(null);
      } catch {
        setActionError('Network error deleting key');
      } finally {
        setDeleting(false);
      }
    },
    [masterKey, selectedKey],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Managed Keys">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Managed API Keys
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Admin-managed Fernet-encrypted API keys. Requires master key.
        </p>
      </div>

      {/* Master key input */}
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
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
            data-testid="include-inactive-checkbox"
          />
          Include inactive
        </label>
      </div>

      {/* Create form */}
      <section
        className="mb-6 rounded border border-slate-700 bg-slate-800/30 p-4"
        data-testid="create-section"
      >
        <h2 className="mb-3 text-sm font-semibold text-slate-300">Create Managed Key</h2>
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
              placeholder="Scopes (space-separated)"
              className="w-48 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="create-scopes-input"
            />
            <input
              type="number"
              value={createExpiresIn}
              onChange={(e) => setCreateExpiresIn(e.target.value)}
              placeholder="Expires in (s)"
              className="w-32 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="create-expires-input"
            />
            <input
              type="number"
              value={createRateLimit}
              onChange={(e) => setCreateRateLimit(e.target.value)}
              placeholder="Rate limit (req/min)"
              className="w-40 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
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
            <p className="mb-1 font-semibold text-emerald-400">Key created!</p>
            <p className="text-slate-300">
              ID:{' '}
              <span className="font-mono" data-testid="new-key-id">
                {newKey.id}
              </span>
            </p>
            {(newKey as Record<string, unknown>).key_value && (
              <p className="mt-1 text-slate-300">
                Key:{' '}
                <span className="font-mono text-yellow-300" data-testid="new-key-value">
                  {String((newKey as Record<string, unknown>).key_value)}
                </span>
              </p>
            )}
          </div>
        )}
      </section>

      {/* Two-column: list + detail */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Key list */}
        <div>
          {listError && (
            <p className="mb-3 text-sm text-red-400" data-testid="list-error">
              {listError}
            </p>
          )}
          {loading && keys.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="list-loading">
              Loading…
            </p>
          )}
          {!loading && keys.length === 0 && !listError && masterKey.trim() && (
            <p className="text-xs text-slate-500" data-testid="no-keys">
              No managed keys found.
            </p>
          )}
          {keys.length > 0 && (
            <div className="overflow-x-auto" data-testid="keys-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-1 pr-3 font-medium">Name</th>
                    <th className="pb-1 pr-3 font-medium">Status</th>
                    <th className="pb-1 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {keys.map((k) => (
                    <tr
                      key={k.id}
                      className="border-b border-slate-700/40"
                      data-testid="key-row"
                    >
                      <td className="py-1.5 pr-3">
                        <button
                          onClick={() => loadDetail(k.id)}
                          className="text-left text-slate-300 hover:text-indigo-400"
                          data-testid="key-name-btn"
                        >
                          {k.name}
                        </button>
                        <div className="mt-0.5 font-mono text-slate-500">{k.id}</div>
                      </td>
                      <td className="py-1.5 pr-3">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                            k.active !== false
                              ? 'bg-emerald-900/40 text-emerald-400'
                              : 'bg-slate-700 text-slate-400'
                          }`}
                          data-testid="key-status"
                        >
                          {k.active !== false ? 'active' : 'inactive'}
                        </span>
                      </td>
                      <td className="py-1.5">
                        <div className="flex gap-1">
                          <button
                            onClick={() => handleRevoke(k.id)}
                            disabled={revoking || k.active === false}
                            className="rounded bg-yellow-900/60 px-2 py-0.5 text-xs text-yellow-300 hover:bg-yellow-900 disabled:opacity-50"
                            data-testid="revoke-btn"
                          >
                            Revoke
                          </button>
                          <button
                            onClick={() => handleDelete(k.id)}
                            disabled={deleting}
                            className="rounded bg-red-900/60 px-2 py-0.5 text-xs text-red-300 hover:bg-red-900 disabled:opacity-50"
                            data-testid="delete-btn"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {actionError && (
            <p className="mt-3 text-sm text-red-400" data-testid="action-error">
              {actionError}
            </p>
          )}
        </div>

        {/* Detail panel */}
        <div>
          {detailLoading && (
            <p className="text-xs text-slate-500" data-testid="detail-loading">
              Loading key detail…
            </p>
          )}
          {detailError && (
            <p className="text-sm text-red-400" data-testid="detail-error">
              {detailError}
            </p>
          )}
          {!selectedKey && !detailLoading && !detailError && (
            <p className="text-xs text-slate-500" data-testid="no-key-selected">
              Click a key name to view details.
            </p>
          )}
          {selectedKey && (
            <div
              className="rounded border border-slate-700 bg-slate-800/30 p-4"
              data-testid="key-detail"
            >
              <h2 className="mb-3 text-sm font-semibold text-slate-100" data-testid="detail-name">
                {selectedKey.name}
              </h2>
              <dl className="mb-4 space-y-1 text-xs">
                <div className="flex gap-2">
                  <dt className="w-24 text-slate-500">ID</dt>
                  <dd className="font-mono text-slate-400" data-testid="detail-id">
                    {selectedKey.id}
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dt className="w-24 text-slate-500">Scopes</dt>
                  <dd className="text-slate-400" data-testid="detail-scopes">
                    {Array.isArray(selectedKey.scopes)
                      ? selectedKey.scopes.join(', ')
                      : String(selectedKey.scopes ?? '—')}
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dt className="w-24 text-slate-500">Active</dt>
                  <dd className="text-slate-400" data-testid="detail-active">
                    {selectedKey.active !== false ? 'Yes' : 'No'}
                  </dd>
                </div>
                {selectedKey.usage_count != null && (
                  <div className="flex gap-2">
                    <dt className="w-24 text-slate-500">Usage</dt>
                    <dd className="text-slate-400" data-testid="detail-usage-count">
                      {String(selectedKey.usage_count)}
                    </dd>
                  </div>
                )}
              </dl>

              {/* Rotate form */}
              <form
                onSubmit={handleRotate}
                className="space-y-2"
                data-testid="rotate-form"
              >
                <label className="block text-xs text-slate-400">Rotate (grace period in seconds):</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={gracePeriod}
                    onChange={(e) => setGracePeriod(e.target.value)}
                    className="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-200 focus:outline-none"
                    data-testid="grace-period-input"
                  />
                  <button
                    type="submit"
                    disabled={rotating}
                    className="rounded bg-indigo-700 px-3 py-1 text-xs text-white hover:bg-indigo-600 disabled:opacity-50"
                    data-testid="rotate-btn"
                  >
                    {rotating ? 'Rotating…' : 'Rotate'}
                  </button>
                </div>
              </form>
              {rotateError && (
                <p className="mt-2 text-xs text-red-400" data-testid="rotate-error">
                  {rotateError}
                </p>
              )}
              {rotateResult && (
                <div
                  className="mt-2 rounded border border-emerald-700/50 bg-emerald-900/20 p-2 text-xs"
                  data-testid="rotate-result"
                >
                  <span className="text-emerald-400">Rotated — new ID: </span>
                  <span className="font-mono text-slate-300" data-testid="rotated-id">
                    {rotateResult.id}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </MainLayout>
  );
};

export default ManagedKeysPage;
