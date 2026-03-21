/**
 * ExecutionReplayPage — Execution Replay UI (N-90).
 *
 * Wraps:
 *   POST /api/v1/executions/{id}/replay         → replay execution
 *   GET  /api/v1/executions/{id}/replay-history → replay chain
 *
 * Route: /execution-replay (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ReplayResult {
  replay_run_id: string;
  original_run_id: string;
  flow_id: string;
  status: string;
}

interface ReplayHistory {
  execution_id: string;
  chain: string[];
  length: number;
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

const ExecutionReplayPage: React.FC = () => {
  // Replay form
  const [execId, setExecId] = useState('');
  const [replaying, setReplaying] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [replayResult, setReplayResult] = useState<ReplayResult | null>(null);

  // History form
  const [historyExecId, setHistoryExecId] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [history, setHistory] = useState<ReplayHistory | null>(null);

  const handleReplay = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!execId.trim()) return;
      setReplaying(true);
      setReplayError(null);
      setReplayResult(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/executions/${encodeURIComponent(execId.trim())}/replay`,
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
    },
    [execId],
  );

  const handleLoadHistory = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!historyExecId.trim()) return;
      setHistoryLoading(true);
      setHistoryError(null);
      setHistory(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/executions/${encodeURIComponent(historyExecId.trim())}/replay-history`,
          { headers: authHeaders() },
        );
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setHistoryError(data.detail ?? `Error ${resp.status}`);
          return;
        }
        setHistory(await resp.json());
      } catch {
        setHistoryError('Network error loading replay history');
      } finally {
        setHistoryLoading(false);
      }
    },
    [historyExecId],
  );

  return (
    <MainLayout title="Execution Replay">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Execution Replay
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Re-run a previous execution with its original input data, or inspect the replay chain.
        </p>
      </div>

      <div className="grid gap-8 md:grid-cols-2">
        {/* Replay section */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-5" data-testid="replay-section">
          <h2 className="mb-4 text-sm font-semibold text-slate-300">Replay Execution</h2>
          <form onSubmit={handleReplay} className="space-y-3" data-testid="replay-form">
            <input
              type="text"
              value={execId}
              onChange={(e) => setExecId(e.target.value)}
              placeholder="Execution ID"
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
              data-testid="exec-id-input"
            />
            <button
              type="submit"
              disabled={replaying || !execId.trim()}
              className="rounded bg-indigo-700 px-4 py-2 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="replay-btn"
            >
              {replaying ? 'Replaying…' : 'Replay'}
            </button>
          </form>

          {replayError && (
            <p className="mt-3 text-sm text-red-400" data-testid="replay-error">{replayError}</p>
          )}

          {replayResult && (
            <div
              className="mt-4 space-y-1.5 rounded bg-emerald-900/20 p-4 text-xs text-emerald-300"
              data-testid="replay-result"
            >
              <p>
                <span className="text-slate-500">New replay ID:</span>{' '}
                <span className="font-mono" data-testid="replay-run-id">
                  {replayResult.replay_run_id}
                </span>
              </p>
              <p>
                <span className="text-slate-500">Original ID:</span>{' '}
                <span className="font-mono">{replayResult.original_run_id}</span>
              </p>
              <p>
                <span className="text-slate-500">Flow:</span>{' '}
                <span className="font-mono">{replayResult.flow_id}</span>
              </p>
              <p>
                <span className="text-slate-500">Status:</span>{' '}
                <span className="font-mono capitalize">{replayResult.status}</span>
              </p>
            </div>
          )}
        </section>

        {/* History section */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-5" data-testid="history-section">
          <h2 className="mb-4 text-sm font-semibold text-slate-300">Replay Chain</h2>
          <form onSubmit={handleLoadHistory} className="space-y-3" data-testid="history-form">
            <input
              type="text"
              value={historyExecId}
              onChange={(e) => setHistoryExecId(e.target.value)}
              placeholder="Execution ID"
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
              data-testid="history-id-input"
            />
            <button
              type="submit"
              disabled={historyLoading || !historyExecId.trim()}
              className="rounded bg-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
              data-testid="history-btn"
            >
              {historyLoading ? 'Loading…' : 'Load History'}
            </button>
          </form>

          {historyError && (
            <p className="mt-3 text-sm text-red-400" data-testid="history-error">{historyError}</p>
          )}

          {history && (
            <div className="mt-4" data-testid="history-result">
              <p className="mb-2 text-xs text-slate-500">
                Chain length: <span className="text-slate-300">{history.length}</span>
              </p>
              {history.chain.length === 0 ? (
                <p className="text-xs text-slate-500" data-testid="no-chain">
                  No replay chain found.
                </p>
              ) : (
                <ol className="space-y-1" data-testid="chain-list">
                  {history.chain.map((runId, idx) => (
                    <li key={runId} className="flex items-center gap-2 text-xs" data-testid="chain-item">
                      <span className="w-5 shrink-0 text-right text-slate-600">{idx + 1}.</span>
                      <span className="font-mono text-slate-300">{runId}</span>
                      {idx === 0 && (
                        <span className="rounded bg-slate-700 px-1 py-0.5 text-slate-400">
                          original
                        </span>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default ExecutionReplayPage;
