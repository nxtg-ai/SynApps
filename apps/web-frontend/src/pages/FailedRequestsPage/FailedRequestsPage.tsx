/**
 * FailedRequestsPage — Failed Request Debugger UI (N-88).
 *
 * Wraps:
 *   GET /api/v1/requests/failed              → list recent failed requests
 *   GET /api/v1/requests/{id}/debug          → full request/response chain
 *   POST /api/v1/requests/{id}/replay        → replay the request
 *
 * Route: /failed-requests (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FailedRequestSummary {
  request_id: string;
  timestamp: string;
  method: string;
  path: string;
  response_status: number;
  duration_ms: number;
  client_ip?: string;
  [key: string]: unknown;
}

interface DebugDetail {
  request_id: string;
  timestamp: string;
  method: string;
  path: string;
  duration_ms: number;
  client_ip?: string;
  request_headers?: Record<string, string>;
  request_body?: string;
  response_status?: number;
  response_headers?: Record<string, string>;
  response_body?: string;
  [key: string]: unknown;
}

interface ReplayResult {
  original_request_id: string;
  replay_status: number;
  replay_headers?: Record<string, string>;
  replay_body?: unknown;
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

function statusColor(code: number): string {
  if (code >= 500) return 'text-red-400';
  if (code >= 400) return 'text-yellow-400';
  return 'text-emerald-400';
}

function methodColor(method: string): string {
  switch (method.toUpperCase()) {
    case 'GET': return 'text-emerald-400';
    case 'POST': return 'text-indigo-400';
    case 'PUT':
    case 'PATCH': return 'text-yellow-400';
    case 'DELETE': return 'text-red-400';
    default: return 'text-slate-400';
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const FailedRequestsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requests, setRequests] = useState<FailedRequestSummary[]>([]);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const [debugError, setDebugError] = useState<string | null>(null);
  const [debugDetail, setDebugDetail] = useState<DebugDetail | null>(null);

  const [replaying, setReplaying] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [replayResult, setReplayResult] = useState<ReplayResult | null>(null);

  const loadRequests = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/requests/failed`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to load requests (${resp.status})`);
        return;
      }
      const data: FailedRequestSummary[] = await resp.json();
      setRequests(data);
    } catch {
      setError('Network error loading failed requests');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  const selectRequest = useCallback(async (req: FailedRequestSummary) => {
    setSelectedId(req.request_id);
    setDebugDetail(null);
    setDebugError(null);
    setReplayResult(null);
    setReplayError(null);
    setDebugLoading(true);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/requests/${encodeURIComponent(req.request_id)}/debug`,
        { headers: authHeaders() },
      );
      if (!resp.ok) {
        setDebugError(`Failed to load debug info (${resp.status})`);
        return;
      }
      setDebugDetail(await resp.json());
    } catch {
      setDebugError('Network error loading debug info');
    } finally {
      setDebugLoading(false);
    }
  }, []);

  const handleReplay = useCallback(async () => {
    if (!selectedId) return;
    setReplaying(true);
    setReplayError(null);
    setReplayResult(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/requests/${encodeURIComponent(selectedId)}/replay`,
        { method: 'POST', headers: authHeaders() },
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setReplayError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setReplayResult(await resp.json());
    } catch {
      setReplayError('Network error during replay');
    } finally {
      setReplaying(false);
    }
  }, [selectedId]);

  return (
    <MainLayout title="Failed Request Debugger">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Failed Request Debugger
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Inspect recent failed requests and replay them for debugging.
          </p>
        </div>
        <button
          onClick={loadRequests}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      <div className="flex gap-6">
        {/* Left: request list */}
        <div className="w-96 shrink-0">
          {error && (
            <p className="mb-3 text-sm text-red-400" data-testid="list-error">{error}</p>
          )}
          {loading && requests.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="list-loading">Loading…</p>
          )}
          {!loading && requests.length === 0 && !error && (
            <p className="text-xs text-slate-500" data-testid="no-requests">
              No failed requests recorded.
            </p>
          )}
          {requests.length > 0 && (
            <div className="overflow-x-auto rounded border border-slate-700" data-testid="requests-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-800/50 text-left text-slate-500">
                    <th className="px-3 py-2 font-medium">Method</th>
                    <th className="px-3 py-2 font-medium">Path</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((req) => (
                    <tr
                      key={req.request_id}
                      onClick={() => selectRequest(req)}
                      className={`cursor-pointer border-b border-slate-700/40 hover:bg-slate-800/50 ${
                        selectedId === req.request_id ? 'bg-slate-800' : ''
                      }`}
                      data-testid="request-row"
                    >
                      <td className={`px-3 py-2 font-mono font-semibold ${methodColor(req.method)}`}>
                        {req.method}
                      </td>
                      <td className="max-w-[140px] truncate px-3 py-2 font-mono text-slate-300">
                        {req.path}
                      </td>
                      <td className={`px-3 py-2 font-mono ${statusColor(req.response_status)}`}>
                        {req.response_status}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right: debug detail panel */}
        <div className="flex-1">
          {!selectedId && (
            <p className="text-sm text-slate-500" data-testid="no-request-selected">
              Select a request to inspect.
            </p>
          )}

          {selectedId && debugLoading && (
            <p className="text-xs text-slate-500" data-testid="debug-loading">
              Loading debug info…
            </p>
          )}

          {selectedId && debugError && (
            <p className="text-sm text-red-400" data-testid="debug-error">{debugError}</p>
          )}

          {selectedId && debugDetail && (
            <div className="space-y-4" data-testid="debug-panel">
              {/* Summary row */}
              <div className="flex flex-wrap items-center gap-3 rounded border border-slate-700 bg-slate-800/30 px-4 py-3">
                <span className={`font-mono font-bold ${methodColor(debugDetail.method)}`}>
                  {debugDetail.method}
                </span>
                <span className="font-mono text-sm text-slate-300" data-testid="debug-path">
                  {debugDetail.path}
                </span>
                <span
                  className={`ml-auto font-mono font-semibold ${statusColor(debugDetail.response_status ?? 0)}`}
                  data-testid="debug-status"
                >
                  {debugDetail.response_status}
                </span>
                <span className="text-xs text-slate-500">
                  {debugDetail.duration_ms}ms
                </span>
              </div>

              {/* Request headers */}
              {debugDetail.request_headers && (
                <section data-testid="req-headers-section">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Request Headers
                  </h3>
                  <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300">
                    {JSON.stringify(debugDetail.request_headers, null, 2)}
                  </pre>
                </section>
              )}

              {/* Request body */}
              {debugDetail.request_body && (
                <section data-testid="req-body-section">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Request Body
                  </h3>
                  <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300">
                    {debugDetail.request_body}
                  </pre>
                </section>
              )}

              {/* Response body */}
              {debugDetail.response_body !== undefined && (
                <section data-testid="resp-body-section">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Response Body
                  </h3>
                  <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300">
                    {typeof debugDetail.response_body === 'string'
                      ? debugDetail.response_body
                      : JSON.stringify(debugDetail.response_body, null, 2)}
                  </pre>
                </section>
              )}

              {/* Replay section */}
              <section className="rounded border border-slate-700 p-4" data-testid="replay-section">
                <h3 className="mb-3 text-sm font-semibold text-slate-300">Replay Request</h3>
                <button
                  onClick={handleReplay}
                  disabled={replaying}
                  className="rounded bg-indigo-700 px-3 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
                  data-testid="replay-btn"
                >
                  {replaying ? 'Replaying…' : 'Replay'}
                </button>

                {replayError && (
                  <p className="mt-2 text-sm text-red-400" data-testid="replay-error">
                    {replayError}
                  </p>
                )}

                {replayResult && (
                  <div className="mt-3 space-y-2" data-testid="replay-result">
                    <p className="text-xs text-slate-400">
                      Replay status:{' '}
                      <span
                        className={`font-mono font-semibold ${statusColor(replayResult.replay_status)}`}
                        data-testid="replay-status"
                      >
                        {replayResult.replay_status}
                      </span>
                    </p>
                    <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300">
                      {typeof replayResult.replay_body === 'string'
                        ? replayResult.replay_body
                        : JSON.stringify(replayResult.replay_body, null, 2)}
                    </pre>
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      </div>
    </MainLayout>
  );
};

export default FailedRequestsPage;
