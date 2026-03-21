/**
 * AppletsRegistryPage — Applet Registry Browser (N-94).
 *
 * Wraps:
 *   GET /api/v1/applets    → list all registered applets with metadata
 *
 * Route: /applets-registry (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Applet {
  type: string;
  name?: string;
  description?: string;
  version?: string;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
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

function authHeaders(): Record<string, string> {
  const token =
    typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const AppletsRegistryPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applets, setApplets] = useState<Applet[]>([]);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Applet | null>(null);

  const loadApplets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/applets`, { headers: authHeaders() });
      if (!resp.ok) {
        setError(`Failed to load applets (${resp.status})`);
        return;
      }
      const data = await resp.json();
      const list: Applet[] = Array.isArray(data)
        ? data
        : Array.isArray(data.items)
          ? data.items
          : [];
      setApplets(list);
    } catch {
      setError('Network error loading applets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadApplets();
  }, [loadApplets]);

  const filtered = applets.filter((a) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      a.type.toLowerCase().includes(q) ||
      (a.name ?? '').toLowerCase().includes(q) ||
      (a.description ?? '').toLowerCase().includes(q)
    );
  });

  return (
    <MainLayout title="Applets Registry">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Applets Registry
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            All registered applet types with metadata and schemas.
          </p>
        </div>
        <button
          onClick={loadApplets}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* Search */}
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search applets…"
        className="mb-4 w-full max-w-sm rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
        data-testid="search-input"
      />

      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="applets-error">{error}</p>
      )}
      {loading && applets.length === 0 && (
        <p className="text-xs text-slate-500" data-testid="applets-loading">Loading…</p>
      )}
      {!loading && applets.length === 0 && !error && (
        <p className="text-xs text-slate-500" data-testid="no-applets">No applets found.</p>
      )}

      <div className="flex gap-6">
        {/* Left: applet list */}
        {filtered.length > 0 && (
          <div className="w-72 shrink-0" data-testid="applets-list">
            {filtered.map((a) => (
              <div
                key={a.type}
                onClick={() => setSelected(a)}
                className={`mb-1 cursor-pointer rounded border px-3 py-2 text-xs ${
                  selected?.type === a.type
                    ? 'border-indigo-600 bg-indigo-900/30 text-indigo-300'
                    : 'border-slate-700 text-slate-300 hover:bg-slate-800/50'
                }`}
                data-testid="applet-item"
              >
                <p className="font-mono font-semibold">{a.type}</p>
                {a.name && a.name !== a.type && (
                  <p className="text-slate-400">{a.name}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Right: detail panel */}
        {selected ? (
          <div className="flex-1 space-y-4" data-testid="applet-detail">
            <div className="rounded border border-slate-700 bg-slate-800/30 px-4 py-3">
              <p className="text-xs text-slate-500">Type</p>
              <p className="font-mono text-sm font-bold text-slate-200" data-testid="detail-type">
                {selected.type}
              </p>
            </div>

            {selected.description && (
              <div className="rounded border border-slate-700 bg-slate-800/30 px-4 py-3">
                <p className="text-xs text-slate-500">Description</p>
                <p className="mt-1 text-sm text-slate-300" data-testid="detail-description">
                  {selected.description}
                </p>
              </div>
            )}

            {selected.version && (
              <div className="inline-block rounded border border-slate-700 bg-slate-800/30 px-4 py-2">
                <p className="text-xs text-slate-500">Version</p>
                <p className="font-mono text-xs text-slate-300" data-testid="detail-version">
                  {selected.version}
                </p>
              </div>
            )}

            {selected.input_schema && (
              <section data-testid="input-schema-section">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Input Schema
                </h3>
                <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300">
                  {JSON.stringify(selected.input_schema, null, 2)}
                </pre>
              </section>
            )}

            {selected.output_schema && (
              <section data-testid="output-schema-section">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Output Schema
                </h3>
                <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300">
                  {JSON.stringify(selected.output_schema, null, 2)}
                </pre>
              </section>
            )}
          </div>
        ) : (
          filtered.length > 0 && (
            <p className="text-sm text-slate-500" data-testid="no-applet-selected">
              Select an applet to view details.
            </p>
          )
        )}
      </div>
    </MainLayout>
  );
};

export default AppletsRegistryPage;
