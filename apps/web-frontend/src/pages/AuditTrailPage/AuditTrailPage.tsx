/**
 * AuditTrailPage — Compliance Audit Log Viewer (N-75).
 *
 * Wraps the N-30 backend API:
 *   GET /api/v1/audit?actor=&action=&resource_type=&resource_id=&since=&until=&limit=
 *     → { count: number, entries: AuditEntry[] }
 *
 * Route: /audit-trail (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: string;
}

interface AuditResult {
  count: number;
  entries: AuditEntry[];
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

function buildQuery(params: Record<string, string>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v.trim())
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v.trim())}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

const ACTION_COLORS: Record<string, string> = {
  workflow_created: 'bg-emerald-900/40 text-emerald-300 border-emerald-700',
  workflow_updated: 'bg-blue-900/40 text-blue-300 border-blue-700',
  workflow_deleted: 'bg-red-900/40 text-red-300 border-red-700',
  run_started:      'bg-blue-900/40 text-blue-300 border-blue-700',
  run_completed:    'bg-emerald-900/40 text-emerald-300 border-emerald-700',
  run_failed:       'bg-red-900/40 text-red-300 border-red-700',
};

function actionBadge(action: string): string {
  return ACTION_COLORS[action] ?? 'bg-slate-800 text-slate-300 border-slate-600';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const AuditTrailPage: React.FC = () => {
  const [actor, setActor] = useState('');
  const [action, setAction] = useState('');
  const [resourceType, setResourceType] = useState('');
  const [resourceId, setResourceId] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [limit, setLimit] = useState('100');

  const [result, setResult] = useState<AuditResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setLoading(true);
      setError(null);
      setResult(null);
      const qs = buildQuery({ actor, action, resource_type: resourceType, resource_id: resourceId, since, until, limit });
      try {
        const resp = await fetch(`${getBaseUrl()}/audit${qs}`, {
          headers: authHeaders(),
        });
        if (!resp.ok) {
          setError(`Failed to fetch audit log (${resp.status})`);
          return;
        }
        const data: AuditResult = await resp.json();
        setResult(data);
      } catch {
        setError('Network error fetching audit log');
      } finally {
        setLoading(false);
      }
    },
    [actor, action, resourceType, resourceId, since, until, limit],
  );

  const handleClear = useCallback(() => {
    setActor('');
    setAction('');
    setResourceType('');
    setResourceId('');
    setSince('');
    setUntil('');
    setLimit('100');
    setResult(null);
    setError(null);
  }, []);

  return (
    <MainLayout title="Audit Trail">
      <h1 className="mb-2 text-2xl font-bold text-slate-100" data-testid="page-title">
        Audit Trail
      </h1>
      <p className="mb-8 text-sm text-slate-400">
        Compliance log of all create, update, delete, and execution events. Filter by actor, action
        type, resource, or time range.
      </p>

      {/* Filter form */}
      <form
        onSubmit={handleSearch}
        className="mb-6 rounded border border-slate-700 bg-slate-800/40 p-5"
        data-testid="filter-form"
      >
        <p className="mb-4 text-sm font-semibold text-slate-300">Filters</p>
        <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs text-slate-400">Actor (email)</label>
            <input
              type="text"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="user@example.com"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="actor-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Action</label>
            <input
              type="text"
              value={action}
              onChange={(e) => setAction(e.target.value)}
              placeholder="workflow_created"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="action-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Resource Type</label>
            <input
              type="text"
              value={resourceType}
              onChange={(e) => setResourceType(e.target.value)}
              placeholder="flow"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="resource-type-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Resource ID</label>
            <input
              type="text"
              value={resourceId}
              onChange={(e) => setResourceId(e.target.value)}
              placeholder="flow-abc123"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="resource-id-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Since (ISO)</label>
            <input
              type="text"
              value={since}
              onChange={(e) => setSince(e.target.value)}
              placeholder="2024-01-01T00:00:00Z"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="since-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Until (ISO)</label>
            <input
              type="text"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              placeholder="2024-12-31T23:59:59Z"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="until-input"
            />
          </div>
        </div>

        <div className="mb-4 flex items-center gap-4">
          <div>
            <label className="mb-1 block text-xs text-slate-400">Limit</label>
            <select
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-blue-500 focus:outline-none"
              data-testid="limit-select"
            >
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="250">250</option>
              <option value="500">500</option>
              <option value="1000">1000</option>
            </select>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={loading}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            data-testid="search-btn"
          >
            {loading ? 'Loading…' : 'Search'}
          </button>
          <button
            type="button"
            onClick={handleClear}
            className="rounded bg-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-600"
            data-testid="clear-btn"
          >
            Clear
          </button>
        </div>
      </form>

      {error && (
        <div
          className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
          data-testid="audit-error"
        >
          {error}
        </div>
      )}

      {result && (
        <div data-testid="results-panel">
          <p className="mb-3 text-sm text-slate-400" data-testid="result-count">
            {result.count} {result.count === 1 ? 'entry' : 'entries'} returned
          </p>

          {result.entries.length === 0 ? (
            <p className="text-sm text-slate-500" data-testid="no-results">
              No audit entries match the selected filters.
            </p>
          ) : (
            <div className="overflow-x-auto" data-testid="audit-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Timestamp</th>
                    <th className="pb-2 pr-4 font-medium">Actor</th>
                    <th className="pb-2 pr-4 font-medium">Action</th>
                    <th className="pb-2 pr-4 font-medium">Resource</th>
                    <th className="pb-2 font-medium">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {result.entries.map((entry) => (
                    <tr
                      key={entry.id}
                      className="border-b border-slate-700/40 hover:bg-slate-800/30"
                      data-testid="audit-row"
                    >
                      <td className="py-1.5 pr-4 font-mono text-slate-400 whitespace-nowrap">
                        {formatTs(entry.timestamp)}
                      </td>
                      <td className="py-1.5 pr-4 text-slate-300">{entry.actor}</td>
                      <td className="py-1.5 pr-4">
                        <span
                          className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${actionBadge(entry.action)}`}
                          data-testid="action-badge"
                        >
                          {entry.action}
                        </span>
                      </td>
                      <td className="py-1.5 pr-4">
                        <span className="text-slate-400">{entry.resource_type}/</span>
                        <span className="font-mono text-slate-300">{entry.resource_id}</span>
                      </td>
                      <td className="py-1.5 text-slate-400">{entry.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </MainLayout>
  );
};

export default AuditTrailPage;
