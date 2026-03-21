/**
 * WorkflowDebugPage — Step-Through Workflow Debugger UI (N-73).
 *
 * Wraps the N-40 backend debug API:
 *   POST /api/v1/workflows/{id}/debug      — start session
 *   GET  /api/v1/debug/{session_id}        — poll status (1s intervals)
 *   POST /api/v1/debug/{session_id}/continue    — resume from pause
 *   POST /api/v1/debug/{session_id}/skip        — skip current node
 *   POST /api/v1/debug/{session_id}/breakpoints — update breakpoints
 *   DELETE /api/v1/debug/{session_id}           — abort
 *
 * Route: /workflow-debug (ProtectedRoute)
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HistoryEntry {
  node_id: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  skipped: boolean;
  timestamp: number;
}

interface DebugSession {
  session_id: string;
  run_id: string;
  flow_id: string;
  status: 'running' | 'paused' | 'completed' | 'aborted';
  breakpoints: string[];
  current_node_id: string | null;
  current_node_input: Record<string, unknown>;
  current_node_output: Record<string, unknown>;
  execution_history: HistoryEntry[];
  created_at: number;
  paused_at: number | null;
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

function getAuthToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

const STATUS_STYLES: Record<string, string> = {
  running:   'bg-blue-900/40 text-blue-300 border-blue-700',
  paused:    'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  completed: 'bg-emerald-900/40 text-emerald-300 border-emerald-700',
  aborted:   'bg-red-900/40 text-red-300 border-red-700',
};

const TERMINAL_STATUSES = new Set(['completed', 'aborted']);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const WorkflowDebugPage: React.FC = () => {
  // Start-session form
  const [flowId, setFlowId] = useState('');
  const [breakpointInput, setBreakpointInput] = useState('');
  const [starting, setStarting] = useState(false);

  // Active session
  const [session, setSession] = useState<DebugSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Breakpoints editing mid-session
  const [editBp, setEditBp] = useState('');
  const [editBpOpen, setEditBpOpen] = useState(false);

  // ---------------------------------------------------------------------------
  // Polling
  // ---------------------------------------------------------------------------

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollSession = useCallback(
    async (sessionId: string) => {
      try {
        const resp = await fetch(`${getBaseUrl()}/debug/${sessionId}`, {
          headers: authHeaders(),
        });
        if (!resp.ok) return;
        const data: { session: DebugSession } = await resp.json();
        setSession(data.session);
        if (TERMINAL_STATUSES.has(data.session.status)) {
          stopPolling();
        }
      } catch {
        // transient network blip — keep polling
      }
    },
    [stopPolling],
  );

  const startPolling = useCallback(
    (sessionId: string) => {
      stopPolling();
      pollRef.current = setInterval(() => pollSession(sessionId), 1000);
    },
    [pollSession, stopPolling],
  );

  useEffect(() => {
    return stopPolling; // cleanup on unmount
  }, [stopPolling]);

  // ---------------------------------------------------------------------------
  // Start session
  // ---------------------------------------------------------------------------

  const handleStart = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const id = flowId.trim();
      if (!id) return;
      setStarting(true);
      setError(null);
      setSession(null);
      stopPolling();

      const bps = breakpointInput
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      try {
        const resp = await fetch(`${getBaseUrl()}/workflows/${id}/debug`, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ breakpoints: bps }),
        });
        if (!resp.ok) {
          const detail = await resp.text().catch(() => '');
          setError(`Failed to start debug session (${resp.status})${detail ? ': ' + detail : ''}`);
          return;
        }
        const data: { session: DebugSession } = await resp.json();
        setSession(data.session);
        if (!TERMINAL_STATUSES.has(data.session.status)) {
          startPolling(data.session.session_id);
        }
      } catch {
        setError('Network error starting debug session');
      } finally {
        setStarting(false);
      }
    },
    [flowId, breakpointInput, startPolling, stopPolling],
  );

  // ---------------------------------------------------------------------------
  // Session controls
  // ---------------------------------------------------------------------------

  const sendControl = useCallback(
    async (path: string, body: Record<string, unknown> = {}, method = 'POST') => {
      if (!session) return;
      setError(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/debug/${session.session_id}/${path}`, {
          method,
          headers: method === 'DELETE' ? authHeaders() : jsonHeaders(),
          body: method === 'DELETE' ? undefined : JSON.stringify(body),
        });
        if (!resp.ok) {
          setError(`Request failed (${resp.status})`);
          return;
        }
        if (method !== 'DELETE') {
          const data: { session: DebugSession } = await resp.json();
          setSession(data.session);
          if (TERMINAL_STATUSES.has(data.session.status)) stopPolling();
          else if (!pollRef.current) startPolling(data.session.session_id);
        } else {
          stopPolling();
          setSession((prev) => prev ? { ...prev, status: 'aborted' } : null);
        }
      } catch {
        setError('Network error sending debug control');
      }
    },
    [session, startPolling, stopPolling],
  );

  const handleContinue = useCallback(() => sendControl('continue'), [sendControl]);
  const handleSkip = useCallback(() => sendControl('skip'), [sendControl]);
  const handleAbort = useCallback(
    () => sendControl('', {}, 'DELETE'),
    [sendControl],
  );

  const handleUpdateBreakpoints = useCallback(async () => {
    if (!session) return;
    const bps = editBp.split(',').map((s) => s.trim()).filter(Boolean);
    await sendControl('breakpoints', { breakpoints: bps });
    setEditBpOpen(false);
  }, [session, editBp, sendControl]);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const isTerminal = session ? TERMINAL_STATUSES.has(session.status) : false;
  const isPaused = session?.status === 'paused';

  return (
    <MainLayout title="Workflow Debugger">
      <h1 className="mb-2 text-2xl font-bold text-slate-100" data-testid="page-title">
        Step-Through Workflow Debugger
      </h1>
      <p className="mb-8 text-sm text-slate-400">
        Pause execution at breakpoints, inspect node inputs and outputs, and step through a
        workflow run node by node.
      </p>

      {/* Start form */}
      {!session && (
        <form
          onSubmit={handleStart}
          className="mb-6 rounded border border-slate-700 bg-slate-800/40 p-5"
          data-testid="start-form"
        >
          <p className="mb-4 text-sm font-semibold text-slate-300">Start Debug Session</p>
          <div className="mb-3">
            <label className="mb-1 block text-xs text-slate-400">Workflow ID</label>
            <input
              type="text"
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
              placeholder="flow-abc123"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="flow-id-input"
              required
            />
          </div>
          <div className="mb-4">
            <label className="mb-1 block text-xs text-slate-400">
              Breakpoints <span className="text-slate-500">(node IDs, comma-separated — optional)</span>
            </label>
            <input
              type="text"
              value={breakpointInput}
              onChange={(e) => setBreakpointInput(e.target.value)}
              placeholder="node-1, node-3"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="breakpoint-input"
            />
          </div>
          <button
            type="submit"
            disabled={starting || !flowId.trim()}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            data-testid="start-debug-btn"
          >
            {starting ? 'Starting…' : 'Start Debug Session'}
          </button>
        </form>
      )}

      {error && (
        <div className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300" data-testid="debug-error">
          {error}
        </div>
      )}

      {/* Session panel */}
      {session && (
        <div data-testid="session-panel">
          {/* Header */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border border-slate-700 bg-slate-800/40 px-4 py-3">
            <div className="space-y-0.5">
              <p className="text-xs text-slate-400">
                Session <span className="font-mono text-slate-300">{session.session_id.slice(0, 8)}…</span>
                {' · '}
                Flow <span className="font-mono text-slate-300">{session.flow_id}</span>
              </p>
              {session.current_node_id && (
                <p className="text-xs text-slate-400">
                  Current node: <span className="font-mono text-slate-200">{session.current_node_id}</span>
                </p>
              )}
            </div>
            <span
              className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold ${STATUS_STYLES[session.status] ?? STATUS_STYLES.running}`}
              data-testid="session-status"
            >
              {session.status}
            </span>
          </div>

          {/* Controls */}
          {!isTerminal && (
            <div className="mb-4 flex flex-wrap gap-2" data-testid="session-controls">
              <button
                onClick={handleContinue}
                disabled={!isPaused}
                className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-40"
                data-testid="continue-btn"
              >
                Continue
              </button>
              <button
                onClick={handleSkip}
                disabled={!isPaused}
                className="rounded bg-yellow-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-yellow-600 disabled:opacity-40"
                data-testid="skip-btn"
              >
                Skip Node
              </button>
              <button
                onClick={() => { setEditBp(session.breakpoints.join(', ')); setEditBpOpen(true); }}
                className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600"
                data-testid="edit-breakpoints-btn"
              >
                Breakpoints ({session.breakpoints.length})
              </button>
              <button
                onClick={handleAbort}
                className="rounded bg-red-800/60 px-3 py-1.5 text-sm text-red-300 hover:bg-red-700"
                data-testid="abort-btn"
              >
                Abort
              </button>
            </div>
          )}

          {/* Breakpoints editor */}
          {editBpOpen && (
            <div className="mb-4 flex gap-2" data-testid="breakpoints-editor">
              <input
                type="text"
                value={editBp}
                onChange={(e) => setEditBp(e.target.value)}
                placeholder="node-1, node-3"
                className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                data-testid="breakpoints-edit-input"
              />
              <button
                onClick={handleUpdateBreakpoints}
                className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-500"
                data-testid="save-breakpoints-btn"
              >
                Save
              </button>
              <button
                onClick={() => setEditBpOpen(false)}
                className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300"
                data-testid="cancel-breakpoints-btn"
              >
                Cancel
              </button>
            </div>
          )}

          {/* Current node I/O */}
          {isPaused && session.current_node_id && (
            <div className="mb-4 grid gap-3 sm:grid-cols-2" data-testid="node-io">
              <div className="rounded border border-slate-700 bg-slate-900 p-3">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Input</p>
                <pre className="overflow-auto text-xs text-slate-300" data-testid="node-input">
                  {JSON.stringify(session.current_node_input, null, 2)}
                </pre>
              </div>
              <div className="rounded border border-slate-700 bg-slate-900 p-3">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Output</p>
                <pre className="overflow-auto text-xs text-slate-300" data-testid="node-output">
                  {JSON.stringify(session.current_node_output, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* Execution history */}
          <div data-testid="execution-history">
            <p className="mb-2 text-sm font-semibold text-slate-300">
              Execution History ({session.execution_history.length} nodes)
            </p>
            {session.execution_history.length === 0 ? (
              <p className="text-xs text-slate-500" data-testid="history-empty">
                No nodes executed yet.
              </p>
            ) : (
              <div className="space-y-1">
                {session.execution_history.map((entry, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-3 rounded border px-3 py-1.5 text-xs ${
                      entry.skipped
                        ? 'border-slate-700 bg-slate-800/30 text-slate-500'
                        : 'border-slate-700 bg-slate-800/60 text-slate-200'
                    }`}
                    data-testid="history-entry"
                  >
                    <span className="font-mono">{entry.node_id}</span>
                    {entry.skipped && (
                      <span className="text-yellow-500" data-testid="skipped-badge">skipped</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* New session button for terminal states */}
          {isTerminal && (
            <button
              onClick={() => { setSession(null); setError(null); }}
              className="mt-6 rounded bg-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-600"
              data-testid="new-session-btn"
            >
              Start New Session
            </button>
          )}
        </div>
      )}
    </MainLayout>
  );
};

export default WorkflowDebugPage;
