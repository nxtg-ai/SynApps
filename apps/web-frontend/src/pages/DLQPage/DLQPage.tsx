/**
 * DLQPage — Dead Letter Queue Viewer (N-77).
 *
 * Wraps the DLQ management API:
 *   GET    /api/v1/dlq?flow_id=      — list failed runs
 *   GET    /api/v1/dlq/{id}          — get single entry
 *   DELETE /api/v1/dlq/{id}          — discard entry
 *   POST   /api/v1/dlq/{id}/replay   — replay entry (body: {input_override?})
 *
 * Route: /dlq (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DLQEntry {
  id: string;
  run_id: string;
  flow_id: string | null;
  error: string;
  error_details: Record<string, unknown> | null;
  failed_at: string;
  replay_count: number;
  input_data: Record<string, unknown>;
}

interface DLQListResult {
  items: DLQEntry[];
  total: number;
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

function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DLQPage: React.FC = () => {
  const [entries, setEntries] = useState<DLQEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter
  const [filterFlowId, setFilterFlowId] = useState('');

  // Expanded entry
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Replay state
  const [replayId, setReplayId] = useState<string | null>(null);
  const [replayOverride, setReplayOverride] = useState('');
  const [replaying, setReplaying] = useState(false);
  const [replayResult, setReplayResult] = useState<Record<string, unknown> | null>(null);

  // Delete confirm
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const loadEntries = useCallback(
    async (flowId?: string) => {
      setLoading(true);
      setError(null);
      setReplayResult(null);
      const qs = flowId?.trim() ? `?flow_id=${encodeURIComponent(flowId.trim())}` : '';
      try {
        const resp = await fetch(`${getBaseUrl()}/dlq${qs}`, { headers: authHeaders() });
        if (!resp.ok) {
          setError(`Failed to load DLQ (${resp.status})`);
          return;
        }
        const data: DLQListResult = await resp.json();
        setEntries(data.items);
        setTotal(data.total);
      } catch {
        setError('Network error loading DLQ');
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  const handleFilter = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      loadEntries(filterFlowId);
    },
    [filterFlowId, loadEntries],
  );

  const handleReplay = useCallback(
    async (id: string) => {
      setReplaying(true);
      setError(null);
      setReplayResult(null);
      let inputOverride: Record<string, unknown> | undefined;
      if (replayOverride.trim()) {
        try {
          inputOverride = JSON.parse(replayOverride);
        } catch {
          setError('Invalid JSON in input override');
          setReplaying(false);
          return;
        }
      }
      try {
        const resp = await fetch(`${getBaseUrl()}/dlq/${id}/replay`, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify(inputOverride ? { input_override: inputOverride } : {}),
        });
        if (!resp.ok) {
          setError(`Replay failed (${resp.status})`);
          return;
        }
        const result = await resp.json();
        setReplayResult(result);
        // Increment replay_count in local state
        setEntries((prev) =>
          prev.map((e) =>
            e.id === id ? { ...e, replay_count: e.replay_count + 1 } : e,
          ),
        );
        setReplayId(null);
        setReplayOverride('');
      } catch {
        setError('Network error during replay');
      } finally {
        setReplaying(false);
      }
    },
    [replayOverride],
  );

  const handleDiscard = useCallback(async (id: string) => {
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/dlq/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to discard entry (${resp.status})`);
        return;
      }
      setEntries((prev) => prev.filter((e) => e.id !== id));
      setTotal((prev) => Math.max(0, prev - 1));
      setDeleteId(null);
    } catch {
      setError('Network error discarding entry');
    }
  }, []);

  return (
    <MainLayout title="Dead Letter Queue">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Dead Letter Queue
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Failed workflow runs that could not be processed. Inspect errors, replay with optional
          input overrides, or discard entries.
        </p>
      </div>

      {/* Filter */}
      <form
        onSubmit={handleFilter}
        className="mb-6 flex gap-3"
        data-testid="filter-form"
      >
        <input
          type="text"
          value={filterFlowId}
          onChange={(e) => setFilterFlowId(e.target.value)}
          placeholder="Filter by workflow ID (optional)"
          className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          data-testid="filter-flow-input"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="filter-btn"
        >
          {loading ? 'Loading…' : 'Filter'}
        </button>
        <button
          type="button"
          onClick={() => { setFilterFlowId(''); loadEntries(); }}
          className="rounded bg-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-600"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </form>

      {error && (
        <div
          className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
          data-testid="dlq-error"
        >
          {error}
        </div>
      )}

      {replayResult && (
        <div
          className="mb-4 rounded border border-emerald-700 bg-emerald-900/30 px-4 py-2 text-sm text-emerald-300"
          data-testid="replay-result"
        >
          Replay dispatched. Run ID: <span className="font-mono">{String((replayResult as { replay_run_id?: unknown }).replay_run_id ?? '')}</span>
        </div>
      )}

      {!loading && (
        <p className="mb-3 text-xs text-slate-500" data-testid="total-count">
          {total} {total === 1 ? 'entry' : 'entries'} in queue
        </p>
      )}

      {!loading && entries.length === 0 && (
        <p className="text-sm text-slate-500" data-testid="empty-state">
          No failed runs in the dead letter queue.
        </p>
      )}

      {entries.length > 0 && (
        <div className="space-y-3" data-testid="dlq-list">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="rounded border border-slate-700 bg-slate-800/40 p-4"
              data-testid="dlq-row"
            >
              {/* Row header */}
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-red-400 line-clamp-2">
                    {entry.error}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    Run: <span className="font-mono text-slate-300">{entry.run_id.slice(0, 12)}…</span>
                    {entry.flow_id && (
                      <>
                        {' · '}Flow: <span className="font-mono text-slate-300">{entry.flow_id}</span>
                      </>
                    )}
                    {' · '}Failed: {formatTs(entry.failed_at)}
                    {entry.replay_count > 0 && (
                      <> · <span className="text-yellow-400">replayed {entry.replay_count}×</span></>
                    )}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                    className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-600"
                    data-testid="expand-btn"
                  >
                    {expandedId === entry.id ? 'Collapse' : 'Details'}
                  </button>
                  <button
                    onClick={() => { setReplayId(entry.id); setReplayOverride(''); }}
                    className="rounded bg-blue-800/60 px-2 py-0.5 text-xs text-blue-300 hover:bg-blue-700"
                    data-testid="replay-btn"
                  >
                    Replay
                  </button>
                  {deleteId === entry.id ? (
                    <>
                      <button
                        onClick={() => handleDiscard(entry.id)}
                        className="rounded bg-red-700 px-2 py-0.5 text-xs text-red-100 hover:bg-red-600"
                        data-testid="confirm-discard-btn"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => setDeleteId(null)}
                        className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300"
                        data-testid="cancel-discard-btn"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setDeleteId(entry.id)}
                      className="rounded bg-red-900/40 px-2 py-0.5 text-xs text-red-400 hover:bg-red-800/60"
                      data-testid="discard-btn"
                    >
                      Discard
                    </button>
                  )}
                </div>
              </div>

              {/* Expanded details */}
              {expandedId === entry.id && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2" data-testid="dlq-details">
                  <div className="rounded border border-slate-700 bg-slate-900 p-3">
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Input Data
                    </p>
                    <pre className="overflow-auto text-xs text-slate-300" data-testid="entry-input">
                      {JSON.stringify(entry.input_data, null, 2)}
                    </pre>
                  </div>
                  {entry.error_details && (
                    <div className="rounded border border-slate-700 bg-slate-900 p-3">
                      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Error Details
                      </p>
                      <pre className="overflow-auto text-xs text-red-300" data-testid="error-details">
                        {JSON.stringify(entry.error_details, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* Replay form */}
              {replayId === entry.id && (
                <div className="mt-3" data-testid="replay-form">
                  <p className="mb-2 text-xs text-slate-400">
                    Input override (JSON, optional — leave blank to replay with original input):
                  </p>
                  <textarea
                    value={replayOverride}
                    onChange={(e) => setReplayOverride(e.target.value)}
                    rows={4}
                    placeholder='{}'
                    className="mb-2 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-200 focus:border-blue-500 focus:outline-none"
                    data-testid="replay-override-input"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleReplay(entry.id)}
                      disabled={replaying}
                      className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
                      data-testid="submit-replay-btn"
                    >
                      {replaying ? 'Replaying…' : 'Dispatch Replay'}
                    </button>
                    <button
                      onClick={() => { setReplayId(null); setReplayOverride(''); }}
                      className="rounded bg-slate-700 px-3 py-1.5 text-xs text-slate-300"
                      data-testid="cancel-replay-btn"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </MainLayout>
  );
};

export default DLQPage;
