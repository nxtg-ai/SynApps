/**
 * UsageDetailPage — Per-key usage inspector (N-119).
 *
 * Covers:
 *   GET /api/v1/usage/{key_id} → detailed usage for a specific consumer key
 *     Returns: requests_today/week/month, errors_month, bandwidth_bytes,
 *              error_rate_pct, quota, by_endpoint, by_hour, last_request_at
 *
 * Route: /usage-detail (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UsageDetail {
  key_id: string;
  requests_today: number;
  requests_week: number;
  requests_month: number;
  errors_month: number;
  bandwidth_bytes: number;
  error_rate_pct: number;
  quota?: number | null;
  by_endpoint: Record<string, number>;
  by_hour: Record<string, number>;
  last_request_at?: string | null;
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

function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const UsageDetailPage: React.FC = () => {
  const [keyId, setKeyId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<UsageDetail | null>(null);

  async function handleFetch(e: React.FormEvent) {
    e.preventDefault();
    if (!keyId.trim()) return;
    setLoading(true);
    setError(null);
    setDetail(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/usage/${encodeURIComponent(keyId.trim())}`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setDetail(data as UsageDetail);
    } catch {
      setError('Network error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <MainLayout title="Usage Detail">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Usage Detail
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Per-key bandwidth, request counts, and endpoint breakdown.
        </p>
      </div>

      {/* Lookup form */}
      <form onSubmit={handleFetch} className="mb-6 flex items-end gap-3" data-testid="lookup-form">
        <div>
          <label className="mb-1 block text-xs text-slate-400">API Key ID</label>
          <input
            className="w-80 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
            placeholder="key-id or consumer-id"
            value={keyId}
            onChange={(e) => setKeyId(e.target.value)}
            required
            data-testid="key-id-input"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !keyId.trim()}
          className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
          data-testid="fetch-btn"
        >
          {loading ? 'Loading…' : 'Fetch Usage'}
        </button>
      </form>

      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="fetch-error">{error}</p>
      )}

      {detail && (
        <div className="space-y-6" data-testid="usage-detail">
          {/* Summary cards */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4" data-testid="summary-cards">
            <div className="rounded border border-slate-700 bg-slate-800/30 p-4 text-center">
              <p className="text-xs text-slate-500">Today</p>
              <p className="mt-1 text-2xl font-bold text-slate-200" data-testid="requests-today">
                {detail.requests_today}
              </p>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/30 p-4 text-center">
              <p className="text-xs text-slate-500">This Week</p>
              <p className="mt-1 text-2xl font-bold text-slate-200" data-testid="requests-week">
                {detail.requests_week}
              </p>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/30 p-4 text-center">
              <p className="text-xs text-slate-500">This Month</p>
              <p className="mt-1 text-2xl font-bold text-slate-200" data-testid="requests-month">
                {detail.requests_month}
              </p>
              {detail.quota != null && (
                <p className="mt-0.5 text-xs text-slate-500">
                  quota: {detail.quota}
                </p>
              )}
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/30 p-4 text-center">
              <p className="text-xs text-slate-500">Error Rate</p>
              <p
                className={`mt-1 text-2xl font-bold ${detail.error_rate_pct > 5 ? 'text-red-400' : 'text-emerald-400'}`}
                data-testid="error-rate"
              >
                {detail.error_rate_pct}%
              </p>
            </div>
          </div>

          {/* Bandwidth + errors */}
          <div className="flex flex-wrap gap-6 text-sm" data-testid="meta-row">
            <div>
              <span className="text-slate-500">Bandwidth: </span>
              <span className="font-medium text-slate-300" data-testid="bandwidth">
                {fmtBytes(detail.bandwidth_bytes)}
              </span>
            </div>
            <div>
              <span className="text-slate-500">Errors this month: </span>
              <span className="font-medium text-red-400" data-testid="errors-month">
                {detail.errors_month}
              </span>
            </div>
            {detail.last_request_at && (
              <div>
                <span className="text-slate-500">Last request: </span>
                <span className="text-slate-400" data-testid="last-request-at">
                  {detail.last_request_at}
                </span>
              </div>
            )}
          </div>

          {/* By endpoint */}
          {Object.keys(detail.by_endpoint).length > 0 && (
            <section data-testid="by-endpoint-section">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">By Endpoint</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-700 text-left text-slate-500">
                      <th className="pb-2 pr-6 font-medium">Endpoint</th>
                      <th className="pb-2 font-medium">Requests</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(detail.by_endpoint)
                      .sort(([, a], [, b]) => b - a)
                      .map(([ep, count]) => (
                        <tr key={ep} className="border-b border-slate-700/40" data-testid="endpoint-row">
                          <td className="py-2 pr-6 font-mono text-slate-300" data-testid="endpoint-path">
                            {ep}
                          </td>
                          <td className="py-2 text-slate-400" data-testid="endpoint-count">
                            {count}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* By hour */}
          {Object.keys(detail.by_hour).length > 0 && (
            <section data-testid="by-hour-section">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">By Hour</h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(detail.by_hour)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([hour, count]) => (
                    <div
                      key={hour}
                      className="rounded border border-slate-700 bg-slate-800/30 px-2 py-1 text-xs"
                      data-testid="hour-bucket"
                    >
                      <span className="text-slate-500">{hour}: </span>
                      <span className="font-medium text-slate-300">{count}</span>
                    </div>
                  ))}
              </div>
            </section>
          )}
        </div>
      )}

      {!loading && !detail && !error && (
        <p className="text-sm text-slate-500" data-testid="empty-state">
          Enter an API Key ID and click Fetch Usage.
        </p>
      )}
    </MainLayout>
  );
};

export default UsageDetailPage;
