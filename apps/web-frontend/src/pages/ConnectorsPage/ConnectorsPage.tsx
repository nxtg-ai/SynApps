/**
 * ConnectorsPage — Connector Health Dashboard (N-83).
 *
 * Wraps:
 *   GET  /api/v1/connectors/health            → all connector statuses
 *   POST /api/v1/connectors/{name}/probe      → probe single connector
 *
 * Route: /connectors (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConnectorResult {
  name: string;
  status: string;
  dashboard_status: string;
  avg_latency_ms?: number;
  consecutive_failures?: number;
  error_count_5m?: number;
  last_check?: string;
  last_success?: string;
  total_probes?: number;
  [key: string]: unknown;
}

interface ConnectorsHealthResponse {
  connectors: ConnectorResult[];
  summary: {
    healthy: number;
    degraded: number;
    down: number;
    disabled: number;
  };
  total: number;
  disable_threshold?: number;
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

function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'healthy': return 'text-emerald-400';
    case 'degraded': return 'text-yellow-400';
    case 'down': return 'text-red-400';
    case 'disabled': return 'text-slate-500';
    default: return 'text-slate-400';
  }
}

function statusBg(status: string): string {
  switch (status.toLowerCase()) {
    case 'healthy': return 'bg-emerald-900/40 text-emerald-300';
    case 'degraded': return 'bg-yellow-900/40 text-yellow-300';
    case 'down': return 'bg-red-900/40 text-red-300';
    case 'disabled': return 'bg-slate-700/40 text-slate-400';
    default: return 'bg-slate-700/40 text-slate-400';
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const ConnectorsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ConnectorsHealthResponse | null>(null);
  const [probingName, setProbingName] = useState<string | null>(null);
  const [probeResults, setProbeResults] = useState<Record<string, ConnectorResult>>({});

  const loadConnectors = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/connectors/health`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to load connectors (${resp.status})`);
        return;
      }
      setData(await resp.json());
    } catch {
      setError('Network error loading connectors');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConnectors();
  }, [loadConnectors]);

  const handleProbe = useCallback(
    async (name: string) => {
      setProbingName(name);
      try {
        const resp = await fetch(`${getBaseUrl()}/connectors/${encodeURIComponent(name)}/probe`, {
          method: 'POST',
          headers: authHeaders(),
        });
        if (!resp.ok) return;
        const result: ConnectorResult = await resp.json();
        setProbeResults((prev) => ({ ...prev, [name]: result }));
      } catch {
        // probe failed silently — user can retry
      } finally {
        setProbingName(null);
      }
    },
    [],
  );

  const connectors = data?.connectors ?? [];

  return (
    <MainLayout title="Connectors">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Connector Health
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Live health status for all registered service connectors.
          </p>
        </div>
        <button
          onClick={loadConnectors}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="connectors-error">{error}</p>
      )}

      {loading && !data && (
        <p className="text-xs text-slate-500" data-testid="connectors-loading">Loading…</p>
      )}

      {data && (
        <>
          {/* Summary row */}
          <div
            className="mb-6 grid grid-cols-4 gap-3"
            data-testid="summary-row"
          >
            {[
              { label: 'Healthy', value: data.summary.healthy, cls: 'text-emerald-400' },
              { label: 'Degraded', value: data.summary.degraded, cls: 'text-yellow-400' },
              { label: 'Down', value: data.summary.down, cls: 'text-red-400' },
              { label: 'Disabled', value: data.summary.disabled, cls: 'text-slate-500' },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded border border-slate-700 bg-slate-800/40 p-3 text-center"
                data-testid={`summary-${s.label.toLowerCase()}`}
              >
                <p className="text-xs text-slate-500">{s.label}</p>
                <p className={`mt-1 text-xl font-bold ${s.cls}`}>{s.value}</p>
              </div>
            ))}
          </div>

          {connectors.length === 0 ? (
            <p className="text-xs text-slate-500" data-testid="no-connectors">
              No connectors registered.
            </p>
          ) : (
            <div className="overflow-x-auto" data-testid="connectors-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Connector</th>
                    <th className="pb-2 pr-4 font-medium">Status</th>
                    <th className="pb-2 pr-4 font-medium">Avg Latency</th>
                    <th className="pb-2 pr-4 font-medium">Errors (5m)</th>
                    <th className="pb-2 pr-4 font-medium">Consecutive Fails</th>
                    <th className="pb-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {connectors.map((c) => {
                    const probed = probeResults[c.name];
                    const displayed = probed ?? c;
                    return (
                      <tr
                        key={c.name}
                        className="border-b border-slate-700/40"
                        data-testid="connector-row"
                      >
                        <td className="py-1.5 pr-4 font-mono text-slate-300">{c.name}</td>
                        <td className="py-1.5 pr-4">
                          <span
                            className={`rounded px-1.5 py-0.5 text-xs ${statusBg(displayed.dashboard_status)}`}
                            data-testid="status-badge"
                          >
                            {displayed.dashboard_status}
                          </span>
                        </td>
                        <td className="py-1.5 pr-4 text-slate-400">
                          {displayed.avg_latency_ms != null
                            ? `${Math.round(displayed.avg_latency_ms)}ms`
                            : '—'}
                        </td>
                        <td className="py-1.5 pr-4">
                          <span className={displayed.error_count_5m ? 'text-red-400' : 'text-slate-400'}>
                            {displayed.error_count_5m ?? 0}
                          </span>
                        </td>
                        <td className="py-1.5 pr-4">
                          <span className={displayed.consecutive_failures ? 'text-yellow-400' : 'text-slate-400'}>
                            {displayed.consecutive_failures ?? 0}
                          </span>
                        </td>
                        <td className="py-1.5">
                          <button
                            onClick={() => handleProbe(c.name)}
                            disabled={probingName === c.name}
                            className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                            data-testid="probe-btn"
                          >
                            {probingName === c.name ? 'Probing…' : 'Probe'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </MainLayout>
  );
};

export default ConnectorsPage;
