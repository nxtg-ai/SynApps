/**
 * ProviderStatusPage — AI Provider Status Dashboard (N-91).
 *
 * Wraps:
 *   GET /api/v1/providers               → auto-discovered providers
 *   GET /api/v1/llm/providers           → LLM provider catalog
 *   GET /api/v1/image/providers         → Image provider catalog
 *   GET /api/v1/providers/{name}/health → per-provider health check
 *
 * Route: /providers (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DiscoveredProvider {
  name: string;
  status?: string;
  capabilities?: string[];
  [key: string]: unknown;
}

interface CatalogProvider {
  name: string;
  models?: string[];
  [key: string]: unknown;
}

interface ProviderHealth {
  name?: string;
  status?: string;
  latency_ms?: number;
  error?: string;
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

function statusBadgeColor(status?: string): string {
  switch ((status ?? '').toLowerCase()) {
    case 'healthy':
    case 'ok':
    case 'available':
      return 'bg-emerald-900/40 text-emerald-400';
    case 'degraded':
    case 'warning':
      return 'bg-yellow-900/40 text-yellow-400';
    case 'down':
    case 'error':
    case 'unavailable':
      return 'bg-red-900/40 text-red-400';
    default:
      return 'bg-slate-700 text-slate-400';
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const ProviderStatusPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [discovered, setDiscovered] = useState<DiscoveredProvider[]>([]);
  const [llmProviders, setLlmProviders] = useState<CatalogProvider[]>([]);
  const [imageProviders, setImageProviders] = useState<CatalogProvider[]>([]);

  // Per-provider health
  const [healthChecking, setHealthChecking] = useState<string | null>(null);
  const [healthResults, setHealthResults] = useState<Record<string, ProviderHealth>>({});
  const [healthError, setHealthError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [discResp, llmResp, imgResp] = await Promise.all([
        fetch(`${getBaseUrl()}/providers`, { headers: authHeaders() }),
        fetch(`${getBaseUrl()}/llm/providers`, { headers: authHeaders() }),
        fetch(`${getBaseUrl()}/image/providers`, { headers: authHeaders() }),
      ]);

      if (!discResp.ok) {
        setError(`Failed to load providers (${discResp.status})`);
        return;
      }
      const discData = await discResp.json();
      setDiscovered(Array.isArray(discData.providers) ? discData.providers : []);

      if (llmResp.ok) {
        const llmData = await llmResp.json();
        setLlmProviders(
          Array.isArray(llmData.items) ? llmData.items : Array.isArray(llmData) ? llmData : [],
        );
      }

      if (imgResp.ok) {
        const imgData = await imgResp.json();
        setImageProviders(
          Array.isArray(imgData.items) ? imgData.items : Array.isArray(imgData) ? imgData : [],
        );
      }
    } catch {
      setError('Network error loading providers');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const checkHealth = useCallback(async (name: string) => {
    setHealthChecking(name);
    setHealthError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/providers/${encodeURIComponent(name)}/health`,
        { headers: authHeaders() },
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setHealthError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      const result: ProviderHealth = await resp.json();
      setHealthResults((prev) => ({ ...prev, [name]: result }));
    } catch {
      setHealthError('Network error checking health');
    } finally {
      setHealthChecking(null);
    }
  }, []);

  return (
    <MainLayout title="Provider Status">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Provider Status
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            AI provider registry, model catalogs, and health status.
          </p>
        </div>
        <button
          onClick={loadAll}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="providers-error">{error}</p>
      )}
      {loading && (
        <p className="text-xs text-slate-500" data-testid="providers-loading">Loading…</p>
      )}
      {healthError && (
        <p className="mb-4 text-sm text-red-400" data-testid="health-error">{healthError}</p>
      )}

      {/* Discovered providers */}
      <section className="mb-8" data-testid="discovered-section">
        <h2 className="mb-3 text-sm font-semibold text-slate-400 uppercase tracking-wide">
          Auto-Discovered Providers ({discovered.length})
        </h2>
        {!loading && discovered.length === 0 && !error && (
          <p className="text-xs text-slate-500" data-testid="no-discovered">
            No providers discovered.
          </p>
        )}
        {discovered.length > 0 && (
          <div className="overflow-x-auto rounded border border-slate-700" data-testid="discovered-table">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-800/50 text-left text-slate-500">
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Capabilities</th>
                  <th className="px-3 py-2 font-medium">Health</th>
                </tr>
              </thead>
              <tbody>
                {discovered.map((p) => {
                  const health = healthResults[p.name];
                  return (
                    <tr
                      key={p.name}
                      className="border-b border-slate-700/40"
                      data-testid="discovered-row"
                    >
                      <td className="px-3 py-2 font-mono text-slate-300">{p.name}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs ${statusBadgeColor(p.status)}`}
                          data-testid="provider-status-badge"
                        >
                          {p.status ?? 'unknown'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-slate-400">
                        {Array.isArray(p.capabilities)
                          ? p.capabilities.join(', ')
                          : '—'}
                      </td>
                      <td className="px-3 py-2">
                        {health ? (
                          <span
                            className={`rounded px-1.5 py-0.5 text-xs ${statusBadgeColor(health.status)}`}
                            data-testid="health-badge"
                          >
                            {health.status ?? 'checked'}
                            {health.latency_ms != null && ` (${health.latency_ms}ms)`}
                          </span>
                        ) : (
                          <button
                            onClick={() => checkHealth(p.name)}
                            disabled={healthChecking === p.name}
                            className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                            data-testid="health-check-btn"
                          >
                            {healthChecking === p.name ? 'Checking…' : 'Check'}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* LLM + Image catalogs */}
      <div className="grid gap-6 md:grid-cols-2">
        <section data-testid="llm-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-400 uppercase tracking-wide">
            LLM Providers ({llmProviders.length})
          </h2>
          {llmProviders.length === 0 ? (
            <p className="text-xs text-slate-500" data-testid="no-llm-providers">
              No LLM providers found.
            </p>
          ) : (
            <div className="space-y-1" data-testid="llm-list">
              {llmProviders.map((p) => (
                <div
                  key={p.name}
                  className="flex items-center justify-between rounded border border-slate-700/60 px-3 py-2"
                  data-testid="llm-row"
                >
                  <span className="font-mono text-xs text-slate-300">{p.name}</span>
                  {Array.isArray(p.models) && (
                    <span className="text-xs text-slate-500">
                      {p.models.length} model{p.models.length !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <section data-testid="image-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-400 uppercase tracking-wide">
            Image Providers ({imageProviders.length})
          </h2>
          {imageProviders.length === 0 ? (
            <p className="text-xs text-slate-500" data-testid="no-image-providers">
              No image providers found.
            </p>
          ) : (
            <div className="space-y-1" data-testid="image-list">
              {imageProviders.map((p) => (
                <div
                  key={p.name}
                  className="flex items-center justify-between rounded border border-slate-700/60 px-3 py-2"
                  data-testid="image-row"
                >
                  <span className="font-mono text-xs text-slate-300">{p.name}</span>
                  {Array.isArray(p.models) && (
                    <span className="text-xs text-slate-500">
                      {p.models.length} model{p.models.length !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default ProviderStatusPage;
