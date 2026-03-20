/**
 * WebhookDebuggerPage -- Real-time webhook payload inspector and retry tool.
 *
 * Shows incoming webhook deliveries in a live log table with auto-refresh,
 * lets users inspect headers / request body / response body, and retry
 * failed deliveries.
 *
 * Route: /webhooks/debug (ProtectedRoute)
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WebhookDebugEntry {
  entry_id: string;
  flow_id: string | null;
  received_at: number;
  method: string;
  path: string;
  headers: Record<string, string>;
  body: string;
  body_size: number;
  status_code: number;
  response_body: string;
  duration_ms: number;
  retry_count: number;
  last_retry_at: number | null;
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

function formatTimestamp(epoch: number): string {
  return new Date(epoch * 1000).toLocaleTimeString();
}

function methodBadgeClass(method: string): string {
  switch (method.toUpperCase()) {
    case 'GET':
      return 'bg-green-600 text-white';
    case 'POST':
      return 'bg-blue-600 text-white';
    case 'PUT':
      return 'bg-yellow-600 text-white';
    case 'DELETE':
      return 'bg-red-600 text-white';
    default:
      return 'bg-slate-600 text-white';
  }
}

function statusBadgeClass(code: number): string {
  if (code >= 200 && code < 300) return 'bg-green-700 text-white';
  if (code >= 300 && code < 400) return 'bg-yellow-600 text-white';
  return 'bg-red-700 text-white';
}

function tryFormatJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const WebhookDebuggerPage: React.FC = () => {
  const [entries, setEntries] = useState<WebhookDebugEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchEntries = useCallback(async () => {
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/webhooks/debug?limit=50`, {
        headers: authHeaders(),
      });
      if (resp.ok) {
        const data = await resp.json();
        setEntries(data.items ?? []);
      }
    } catch {
      // Network error — keep current entries
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(fetchEntries, 3000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, fetchEntries]);

  const handleRetry = useCallback(
    async (entryId: string) => {
      try {
        const resp = await fetch(`${getBaseUrl()}/api/v1/webhooks/debug/${entryId}/retry`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        });
        if (resp.ok) {
          await fetchEntries();
        }
      } catch {
        // Retry failed — ignore
      }
    },
    [fetchEntries],
  );

  const handleClearAll = useCallback(async () => {
    try {
      await fetch(`${getBaseUrl()}/api/v1/webhooks/debug`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      setEntries([]);
      setSelectedId(null);
    } catch {
      // Clear failed — ignore
    }
  }, []);

  const selected = entries.find((e) => e.entry_id === selectedId) ?? null;

  if (loading) {
    return (
      <MainLayout title="Webhook Debugger">
        <div
          className="flex items-center justify-center py-20 text-slate-400"
          aria-label="Loading webhook data"
        >
          Loading...
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout title="Webhook Debugger">
      {/* Toolbar */}
      <div className="mb-4 flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="accent-blue-500"
          />
          Auto-refresh
        </label>
        <button
          onClick={handleClearAll}
          className="rounded bg-red-700 px-3 py-1 text-sm text-white hover:bg-red-600"
          data-testid="clear-all-btn"
        >
          Clear All
        </button>
      </div>

      {entries.length === 0 ? (
        <div className="py-20 text-center text-slate-500" data-testid="empty-state">
          No webhook activity yet. Trigger a webhook to see it here.
        </div>
      ) : (
        <div className="flex gap-4">
          {/* Log table */}
          <div className="flex-1 overflow-auto">
            <table className="w-full text-left text-sm text-slate-200" data-testid="log-table">
              <thead className="border-b border-slate-700 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Method</th>
                  <th className="px-3 py-2">Path</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Duration</th>
                  <th className="px-3 py-2">Retries</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.entry_id}
                    onClick={() => setSelectedId(entry.entry_id)}
                    className={`cursor-pointer border-b border-slate-800 hover:bg-slate-800 ${
                      selectedId === entry.entry_id ? 'bg-slate-800' : ''
                    }`}
                    data-testid="log-row"
                  >
                    <td className="px-3 py-2 whitespace-nowrap">
                      {formatTimestamp(entry.received_at)}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${methodBadgeClass(entry.method)}`}
                        data-testid="method-badge"
                      >
                        {entry.method}
                      </span>
                    </td>
                    <td className="max-w-xs truncate px-3 py-2 font-mono text-xs">{entry.path}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${statusBadgeClass(entry.status_code)}`}
                        data-testid="status-badge"
                      >
                        {entry.status_code}
                      </span>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {entry.duration_ms.toFixed(1)}ms
                    </td>
                    <td className="px-3 py-2">{entry.retry_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Inspector panel */}
          {selected && (
            <div
              className="w-96 shrink-0 overflow-auto rounded border border-slate-700 bg-slate-900 p-4"
              data-testid="inspector-panel"
            >
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-200">Inspector</h3>
                <button
                  onClick={() => handleRetry(selected.entry_id)}
                  className="rounded bg-blue-700 px-3 py-1 text-xs text-white hover:bg-blue-600"
                  data-testid="retry-btn"
                >
                  Retry
                </button>
              </div>

              <section className="mb-4">
                <h4 className="mb-1 text-xs font-semibold uppercase text-slate-400">Headers</h4>
                <ul className="space-y-0.5 font-mono text-xs text-slate-300" data-testid="headers-list">
                  {Object.entries(selected.headers).map(([k, v]) => (
                    <li key={k}>
                      <span className="text-slate-500">{k}:</span> {v}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="mb-4">
                <h4 className="mb-1 text-xs font-semibold uppercase text-slate-400">
                  Request Body
                </h4>
                <pre
                  className="max-h-48 overflow-auto rounded bg-slate-950 p-2 font-mono text-xs text-slate-300"
                  data-testid="request-body"
                >
                  {tryFormatJson(selected.body)}
                </pre>
              </section>

              <section>
                <h4 className="mb-1 text-xs font-semibold uppercase text-slate-400">
                  Response Body
                </h4>
                <pre
                  className="max-h-48 overflow-auto rounded bg-slate-950 p-2 font-mono text-xs text-slate-300"
                  data-testid="response-body"
                >
                  {tryFormatJson(selected.response_body)}
                </pre>
              </section>
            </div>
          )}
        </div>
      )}
    </MainLayout>
  );
};

export default WebhookDebuggerPage;
