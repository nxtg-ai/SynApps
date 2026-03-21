/**
 * ExecutionLogsPage — Per-Run Execution Log Viewer (N-79).
 *
 * Wraps the execution log API:
 *   GET /api/v1/executions/{run_id}/logs → { run_id, count, logs: LogEntry[] }
 *
 * Route: /execution-logs (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LogEntry {
  event: string;
  node_id: string;
  timestamp?: number;
  started_at?: number;
  duration_ms?: number;
  error?: string;
  [key: string]: unknown;
}

interface LogsResult {
  run_id: string;
  count: number;
  logs: LogEntry[];
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

function formatTs(ts: number | undefined): string {
  if (!ts) return '—';
  try {
    return new Date(ts * 1000).toLocaleTimeString();
  } catch {
    return String(ts);
  }
}

const EVENT_STYLES: Record<string, string> = {
  node_start:    'bg-blue-900/40 text-blue-300 border-blue-700',
  node_success:  'bg-emerald-900/40 text-emerald-300 border-emerald-700',
  node_error:    'bg-red-900/40 text-red-300 border-red-700',
  node_retry:    'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  node_fallback: 'bg-orange-900/40 text-orange-300 border-orange-700',
};

function eventStyle(event: string): string {
  return EVENT_STYLES[event] ?? 'bg-slate-800 text-slate-300 border-slate-600';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ExecutionLogsPage: React.FC = () => {
  const [runId, setRunId] = useState('');
  const [result, setResult] = useState<LogsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const handleSearch = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const id = runId.trim();
      if (!id) return;
      setLoading(true);
      setError(null);
      setResult(null);
      setExpandedIdx(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/executions/${id}/logs`, {
          headers: authHeaders(),
        });
        if (!resp.ok) {
          setError(resp.status === 404 ? 'No logs found for this run ID.' : `Failed to fetch logs (${resp.status})`);
          return;
        }
        const data: LogsResult = await resp.json();
        setResult(data);
      } catch {
        setError('Network error fetching execution logs');
      } finally {
        setLoading(false);
      }
    },
    [runId],
  );

  return (
    <MainLayout title="Execution Logs">
      <h1 className="mb-2 text-2xl font-bold text-slate-100" data-testid="page-title">
        Execution Logs
      </h1>
      <p className="mb-8 text-sm text-slate-400">
        Per-node structured event log for a workflow run — node start, success, error, retry, and
        fallback events.
      </p>

      {/* Search form */}
      <form
        onSubmit={handleSearch}
        className="mb-6 flex gap-3"
        data-testid="search-form"
      >
        <input
          type="text"
          value={runId}
          onChange={(e) => setRunId(e.target.value)}
          placeholder="Run ID (e.g. run-abc123)"
          className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          data-testid="run-id-input"
        />
        <button
          type="submit"
          disabled={!runId.trim() || loading}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          data-testid="search-btn"
        >
          {loading ? 'Loading…' : 'Fetch Logs'}
        </button>
      </form>

      {error && (
        <div
          className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
          data-testid="logs-error"
        >
          {error}
        </div>
      )}

      {result && (
        <div data-testid="logs-panel">
          <p className="mb-3 text-sm text-slate-400" data-testid="log-count">
            {result.count} {result.count === 1 ? 'event' : 'events'} for run{' '}
            <span className="font-mono text-slate-300">{result.run_id.slice(0, 16)}…</span>
          </p>

          {result.logs.length === 0 ? (
            <p className="text-sm text-slate-500" data-testid="no-logs">
              No log events recorded.
            </p>
          ) : (
            <div className="space-y-1" data-testid="log-list">
              {result.logs.map((entry, i) => (
                <div
                  key={i}
                  className="rounded border border-slate-700/50 bg-slate-800/40"
                  data-testid="log-entry"
                >
                  <button
                    className="flex w-full items-center gap-3 px-3 py-2 text-left text-xs"
                    onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                    data-testid="log-entry-toggle"
                  >
                    <span
                      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${eventStyle(entry.event)}`}
                      data-testid="event-badge"
                    >
                      {entry.event}
                    </span>
                    <span className="font-mono text-slate-300">{entry.node_id}</span>
                    {entry.duration_ms !== undefined && (
                      <span className="ml-auto text-slate-500">
                        {entry.duration_ms.toFixed(1)} ms
                      </span>
                    )}
                    {entry.event === 'node_error' && entry.error && (
                      <span className="ml-2 truncate text-red-400">{entry.error}</span>
                    )}
                  </button>

                  {expandedIdx === i && (
                    <div className="border-t border-slate-700/50 px-3 pb-3 pt-2" data-testid="log-entry-details">
                      <pre className="overflow-auto text-xs text-slate-300">
                        {JSON.stringify(entry, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </MainLayout>
  );
};

export default ExecutionLogsPage;
