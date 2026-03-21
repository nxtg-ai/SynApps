/**
 * ConnectorProbePage — Connector health probing (N-111).
 *
 * Covers:
 *   GET  /connectors/health               → all connectors health summary
 *   POST /connectors/{name}/probe         → probe single connector
 *
 * Route: /connector-probe (ProtectedRoute)
 */
import React, { useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConnectorResult {
  name: string;
  status: string;
  dashboard_status: string;
  consecutive_failures?: number;
  total_probes?: number;
  avg_latency_ms?: number;
  error_count_5m?: number;
  latency_ms?: number;
  error?: string;
  [key: string]: unknown;
}

interface HealthSummary {
  healthy: number;
  degraded: number;
  down: number;
  disabled: number;
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

const ConnectorProbePage: React.FC = () => {
  // All connectors health
  const [connectors, setConnectors] = useState<ConnectorResult[]>([]);
  const [summary, setSummary] = useState<HealthSummary | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);

  // Single probe
  const [connectorName, setConnectorName] = useState('');
  const [probeLoading, setProbeLoading] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [probeResult, setProbeResult] = useState<ConnectorResult | null>(null);

  useEffect(() => {
    loadHealth();
  }, []);

  async function loadHealth() {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/connectors/health`, {
        headers: authHeaders(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setHealthError(data.detail ?? `Error ${resp.status}`); return; }
      const raw = data.connectors ?? data;
      setConnectors(Array.isArray(raw) ? raw : []);
      setSummary(data.summary ?? null);
    } catch {
      setHealthError('Network error');
    } finally {
      setHealthLoading(false);
    }
  }

  async function handleProbe(e: React.FormEvent) {
    e.preventDefault();
    if (!connectorName.trim()) return;
    setProbeLoading(true);
    setProbeError(null);
    setProbeResult(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/connectors/${connectorName.trim()}/probe`,
        { method: 'POST', headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setProbeError(data.detail ?? `Error ${resp.status}`); return; }
      setProbeResult(data as ConnectorResult);
    } catch {
      setProbeError('Network error');
    } finally {
      setProbeLoading(false);
    }
  }

  const statusColor = (s: string) =>
    s === 'healthy' || s === 'ok'
      ? 'text-emerald-400'
      : s === 'degraded'
      ? 'text-amber-400'
      : 'text-red-400';

  return (
    <MainLayout title="Connector Probe">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Connector Probe
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Health checks and manual probing for registered connectors.
          </p>
        </div>
        <button
          onClick={loadHealth}
          disabled={healthLoading}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh Health
        </button>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4" data-testid="summary-cards">
          <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center text-xs">
            <p className="text-slate-500">Healthy</p>
            <p className="mt-1 font-bold text-emerald-400" data-testid="summary-healthy">{summary.healthy}</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center text-xs">
            <p className="text-slate-500">Degraded</p>
            <p className="mt-1 font-bold text-amber-400" data-testid="summary-degraded">{summary.degraded}</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center text-xs">
            <p className="text-slate-500">Down</p>
            <p className="mt-1 font-bold text-red-400" data-testid="summary-down">{summary.down}</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center text-xs">
            <p className="text-slate-500">Disabled</p>
            <p className="mt-1 font-bold text-slate-400" data-testid="summary-disabled">{summary.disabled}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">

        {/* ---- All Connectors Health ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4 lg:col-span-2" data-testid="health-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">All Connectors</h2>
          {healthError && (
            <p className="mb-2 text-xs text-red-400" data-testid="health-error">{healthError}</p>
          )}
          {healthLoading && (
            <p className="text-xs text-slate-500" data-testid="health-loading">Loading…</p>
          )}
          {!healthLoading && connectors.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="no-connectors">No connectors registered.</p>
          )}
          {connectors.length > 0 && (
            <div className="overflow-x-auto" data-testid="connectors-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Name</th>
                    <th className="pb-2 pr-4 font-medium">Status</th>
                    <th className="pb-2 pr-4 font-medium">Dashboard</th>
                    <th className="pb-2 pr-4 font-medium">Avg Latency</th>
                    <th className="pb-2 font-medium">Failures</th>
                  </tr>
                </thead>
                <tbody>
                  {connectors.map((c) => (
                    <tr key={c.name} className="border-b border-slate-700/40" data-testid="connector-row">
                      <td className="py-2 pr-4 text-slate-300" data-testid="connector-name">{c.name}</td>
                      <td className={`py-2 pr-4 font-semibold ${statusColor(c.status)}`} data-testid="connector-status">{c.status}</td>
                      <td className={`py-2 pr-4 ${statusColor(c.dashboard_status)}`}>{c.dashboard_status}</td>
                      <td className="py-2 pr-4 text-slate-400">
                        {c.avg_latency_ms !== undefined ? `${c.avg_latency_ms.toFixed(0)}ms` : '—'}
                      </td>
                      <td className="py-2 text-slate-400">{c.consecutive_failures ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ---- Single Probe ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4 lg:col-span-2" data-testid="probe-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Probe Single Connector</h2>
          <form onSubmit={handleProbe} className="flex gap-3" data-testid="probe-form">
            <input
              className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Connector name (e.g. openai)"
              value={connectorName}
              onChange={(e) => setConnectorName(e.target.value)}
              required
              data-testid="connector-name-input"
            />
            <button
              type="submit"
              disabled={probeLoading || !connectorName.trim()}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="probe-btn"
            >
              {probeLoading ? 'Probing…' : 'Probe'}
            </button>
          </form>
          {probeError && (
            <p className="mt-2 text-xs text-red-400" data-testid="probe-error">{probeError}</p>
          )}
          {probeResult && (
            <div className="mt-3 rounded border border-slate-700 bg-slate-900/50 p-3" data-testid="probe-result">
              <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <div>
                  <p className="text-slate-500">Name</p>
                  <p className="mt-0.5 text-slate-200" data-testid="probe-result-name">{probeResult.name}</p>
                </div>
                <div>
                  <p className="text-slate-500">Status</p>
                  <p className={`mt-0.5 font-semibold ${statusColor(probeResult.status)}`} data-testid="probe-result-status">
                    {probeResult.status}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500">Dashboard</p>
                  <p className={`mt-0.5 ${statusColor(probeResult.dashboard_status)}`} data-testid="probe-result-dashboard">
                    {probeResult.dashboard_status}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500">Avg Latency</p>
                  <p className="mt-0.5 text-slate-300" data-testid="probe-result-latency">
                    {probeResult.avg_latency_ms !== undefined
                      ? `${probeResult.avg_latency_ms.toFixed(0)}ms`
                      : '—'}
                  </p>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default ConnectorProbePage;
