/**
 * RunTracePage — Run Trace, Diff & Re-run UI (N-86).
 *
 * Wraps:
 *   GET  /api/v1/runs                      → paginated run list
 *   GET  /api/v1/runs/{id}/trace           → full node-by-node execution trace
 *   GET  /api/v1/runs/{id}/diff?other_run_id=Y → structural diff between two runs
 *   POST /api/v1/runs/{id}/rerun           → re-run with optional input override
 *
 * Route: /run-trace (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RunSummary {
  run_id: string;
  flow_id?: string;
  status?: string;
  created_at?: string;
  [key: string]: unknown;
}

interface RunsResponse {
  items: RunSummary[];
  total: number;
  page: number;
  page_size: number;
}

interface TraceNode {
  node_id: string;
  node_type?: string;
  status?: string;
  duration_ms?: number;
  output?: unknown;
  error?: string;
  [key: string]: unknown;
}

interface TraceResponse {
  run_id?: string;
  flow_id?: string;
  input?: unknown;
  nodes?: TraceNode[];
  [key: string]: unknown;
}

interface DiffResponse {
  same_flow?: boolean;
  nodes_added?: string[];
  nodes_removed?: string[];
  nodes_changed?: string[];
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

function statusColor(s: string): string {
  switch (s?.toLowerCase()) {
    case 'success': case 'completed': return 'text-emerald-400';
    case 'failed': case 'error': return 'text-red-400';
    case 'running': return 'text-yellow-400';
    default: return 'text-slate-400';
  }
}

function statusBadge(s: string): string {
  switch (s?.toLowerCase()) {
    case 'success': case 'completed': return 'bg-emerald-900/40 text-emerald-300';
    case 'failed': case 'error': return 'bg-red-900/40 text-red-300';
    case 'running': return 'bg-yellow-900/40 text-yellow-300';
    default: return 'bg-slate-700/40 text-slate-400';
  }
}

// ---------------------------------------------------------------------------
// RunList sub-component
// ---------------------------------------------------------------------------

interface RunListProps {
  runs: RunSummary[];
  onSelect: (runId: string) => void;
  selectedId: string | null;
}

const RunList: React.FC<RunListProps> = ({ runs, onSelect, selectedId }) => (
  <div className="overflow-x-auto" data-testid="runs-table">
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-slate-700 text-left text-slate-500">
          <th className="pb-2 pr-4 font-medium">Run ID</th>
          <th className="pb-2 pr-4 font-medium">Flow</th>
          <th className="pb-2 pr-4 font-medium">Status</th>
          <th className="pb-2 font-medium">Created</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr
            key={r.run_id}
            onClick={() => onSelect(r.run_id)}
            className={`cursor-pointer border-b border-slate-700/40 hover:bg-slate-700/30 ${
              selectedId === r.run_id ? 'bg-slate-700/50' : ''
            }`}
            data-testid="run-row"
          >
            <td className="py-1.5 pr-4 font-mono text-slate-300">{r.run_id}</td>
            <td className="py-1.5 pr-4 font-mono text-slate-400">{r.flow_id ?? '—'}</td>
            <td className="py-1.5 pr-4">
              <span className={`rounded px-1.5 py-0.5 text-xs ${statusBadge(r.status ?? '')}`} data-testid="run-status-badge">
                {r.status ?? '—'}
              </span>
            </td>
            <td className="py-1.5 text-slate-400">{r.created_at ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const RunTracePage: React.FC = () => {
  // Runs list
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [totalRuns, setTotalRuns] = useState(0);

  // Selected run + trace
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);

  // Diff
  const [diffRunId, setDiffRunId] = useState('');
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [diff, setDiff] = useState<DiffResponse | null>(null);

  // Re-run
  const [rerunInput, setRerunInput] = useState('');
  const [rerunning, setRerunning] = useState(false);
  const [rerunResult, setRerunResult] = useState<string | null>(null);
  const [rerunError, setRerunError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/runs?page_size=20`, { headers: authHeaders() });
      if (!resp.ok) {
        setListError(`Failed to load runs (${resp.status})`);
        return;
      }
      const data: RunsResponse = await resp.json();
      setRuns(data.items ?? []);
      setTotalRuns(data.total ?? 0);
    } catch {
      setListError('Network error loading runs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const handleSelectRun = useCallback(async (runId: string) => {
    setSelectedRunId(runId);
    setTrace(null);
    setTraceError(null);
    setDiff(null);
    setDiffError(null);
    setRerunResult(null);
    setRerunError(null);
    setTraceLoading(true);
    try {
      const resp = await fetch(`${getBaseUrl()}/runs/${runId}/trace`, { headers: authHeaders() });
      if (!resp.ok) {
        setTraceError(`Failed to load trace (${resp.status})`);
        return;
      }
      setTrace(await resp.json());
    } catch {
      setTraceError('Network error loading trace');
    } finally {
      setTraceLoading(false);
    }
  }, []);

  const handleDiff = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!selectedRunId || !diffRunId.trim()) return;
      setDiffLoading(true);
      setDiffError(null);
      setDiff(null);
      try {
        const url = `${getBaseUrl()}/runs/${selectedRunId}/diff?other_run_id=${encodeURIComponent(diffRunId.trim())}`;
        const resp = await fetch(url, { headers: authHeaders() });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setDiffError(data.detail ?? `Error ${resp.status}`);
          return;
        }
        setDiff(await resp.json());
      } catch {
        setDiffError('Network error');
      } finally {
        setDiffLoading(false);
      }
    },
    [selectedRunId, diffRunId],
  );

  const handleRerun = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!selectedRunId) return;
      setRerunning(true);
      setRerunResult(null);
      setRerunError(null);
      let inputData: Record<string, unknown> = {};
      if (rerunInput.trim()) {
        try {
          inputData = JSON.parse(rerunInput.trim());
        } catch {
          setRerunError('Input override must be valid JSON');
          setRerunning(false);
          return;
        }
      }
      try {
        const resp = await fetch(`${getBaseUrl()}/runs/${selectedRunId}/rerun`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ input: inputData, merge_with_original_input: false }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setRerunError(data.detail ?? `Error ${resp.status}`);
          return;
        }
        const data = await resp.json();
        setRerunResult(data.run_id ?? 'Queued');
      } catch {
        setRerunError('Network error');
      } finally {
        setRerunning(false);
      }
    },
    [selectedRunId, rerunInput],
  );

  const traceNodes: TraceNode[] = trace?.nodes ?? [];

  return (
    <MainLayout title="Run Trace">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Run Trace
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Inspect execution traces, compare runs, and re-run workflows.
          </p>
        </div>
        <button
          onClick={loadRuns}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left: run list */}
        <section
          className="rounded border border-slate-700 bg-slate-800/40 p-5"
          data-testid="runs-section"
        >
          <p className="mb-3 text-sm font-semibold text-slate-300">
            Recent Runs
            {totalRuns > 0 && (
              <span className="ml-2 text-xs text-slate-500">({totalRuns} total)</span>
            )}
          </p>

          {listError && (
            <p className="text-sm text-red-400" data-testid="list-error">{listError}</p>
          )}

          {loading && runs.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="runs-loading">Loading…</p>
          )}

          {!loading && runs.length === 0 && !listError && (
            <p className="text-xs text-slate-500" data-testid="no-runs">No runs found.</p>
          )}

          {runs.length > 0 && (
            <RunList runs={runs} onSelect={handleSelectRun} selectedId={selectedRunId} />
          )}
        </section>

        {/* Right: trace + diff + rerun */}
        <section
          className="rounded border border-slate-700 bg-slate-800/40 p-5"
          data-testid="trace-section"
        >
          {!selectedRunId && (
            <p className="text-xs text-slate-500" data-testid="no-run-selected">
              Select a run from the list to view its trace.
            </p>
          )}

          {selectedRunId && (
            <>
              <p className="mb-3 text-sm font-semibold text-slate-300">
                Trace: <span className="font-mono text-slate-400">{selectedRunId}</span>
              </p>

              {traceError && (
                <p className="mb-3 text-sm text-red-400" data-testid="trace-error">{traceError}</p>
              )}
              {traceLoading && (
                <p className="mb-3 text-xs text-slate-500" data-testid="trace-loading">Loading trace…</p>
              )}

              {trace && (
                <div data-testid="trace-panel">
                  {traceNodes.length > 0 ? (
                    <div className="mb-4 space-y-1" data-testid="trace-nodes">
                      {traceNodes.map((n, i) => (
                        <div
                          key={n.node_id ?? i}
                          className="flex items-center gap-2 rounded border border-slate-700/60 bg-slate-900/40 px-3 py-2"
                          data-testid="trace-node"
                        >
                          <span
                            className={`shrink-0 font-mono text-xs ${statusColor(n.status ?? '')}`}
                            data-testid="trace-node-status"
                          >
                            {n.status ?? '?'}
                          </span>
                          <span className="font-mono text-xs text-slate-300">{n.node_id}</span>
                          {n.node_type && (
                            <span className="text-xs text-slate-500">{n.node_type}</span>
                          )}
                          {n.duration_ms != null && (
                            <span className="ml-auto text-xs text-slate-500">{n.duration_ms}ms</span>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mb-4 text-xs text-slate-500" data-testid="no-trace-nodes">
                      No node trace available.
                    </p>
                  )}

                  {/* Diff form */}
                  <div className="mb-4 border-t border-slate-700 pt-4" data-testid="diff-section">
                    <p className="mb-2 text-xs font-semibold text-slate-400">Compare with run</p>
                    <form onSubmit={handleDiff} className="flex gap-2" data-testid="diff-form">
                      <input
                        type="text"
                        value={diffRunId}
                        onChange={(e) => setDiffRunId(e.target.value)}
                        placeholder="Other run ID"
                        className="flex-1 rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
                        data-testid="diff-run-input"
                      />
                      <button
                        type="submit"
                        disabled={diffLoading || !diffRunId.trim()}
                        className="rounded bg-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                        data-testid="diff-btn"
                      >
                        {diffLoading ? 'Diffing…' : 'Diff'}
                      </button>
                    </form>
                    {diffError && (
                      <p className="mt-2 text-xs text-red-400" data-testid="diff-error">{diffError}</p>
                    )}
                    {diff && (
                      <div className="mt-2 text-xs" data-testid="diff-result">
                        <p className="text-slate-400">
                          Same flow: <span className="text-slate-300">{diff.same_flow ? 'Yes' : 'No'}</span>
                        </p>
                        {(diff.nodes_added?.length ?? 0) > 0 && (
                          <p className="text-emerald-400">+{diff.nodes_added!.length} nodes added</p>
                        )}
                        {(diff.nodes_removed?.length ?? 0) > 0 && (
                          <p className="text-red-400">-{diff.nodes_removed!.length} nodes removed</p>
                        )}
                        {(diff.nodes_changed?.length ?? 0) > 0 && (
                          <p className="text-yellow-400">~{diff.nodes_changed!.length} nodes changed</p>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Re-run form */}
                  <div className="border-t border-slate-700 pt-4" data-testid="rerun-section">
                    <p className="mb-2 text-xs font-semibold text-slate-400">Re-run</p>
                    <form onSubmit={handleRerun} className="space-y-2" data-testid="rerun-form">
                      <textarea
                        value={rerunInput}
                        onChange={(e) => setRerunInput(e.target.value)}
                        placeholder='{"key": "value"} (optional input override)'
                        rows={2}
                        className="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1.5 font-mono text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
                        data-testid="rerun-input"
                      />
                      <button
                        type="submit"
                        disabled={rerunning}
                        className="rounded bg-indigo-700 px-3 py-1.5 text-xs text-white hover:bg-indigo-600 disabled:opacity-50"
                        data-testid="rerun-btn"
                      >
                        {rerunning ? 'Queuing…' : 'Re-run'}
                      </button>
                    </form>
                    {rerunError && (
                      <p className="mt-2 text-xs text-red-400" data-testid="rerun-error">{rerunError}</p>
                    )}
                    {rerunResult && (
                      <p className="mt-2 text-xs text-emerald-400" data-testid="rerun-result">
                        New run queued: <span className="font-mono">{rerunResult}</span>
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default RunTracePage;
