/**
 * DebugSessionPage — Interactive flow step-through debugger (N-107).
 *
 * Covers:
 *   POST   /workflows/{flow_id}/debug          → start debug session
 *   GET    /debug/{session_id}                 → get session state
 *   POST   /debug/{session_id}/continue        → resume from breakpoint
 *   POST   /debug/{session_id}/skip            → skip current node
 *   POST   /debug/{session_id}/breakpoints     → update breakpoints
 *   DELETE /debug/{session_id}                 → abort session
 *
 * Route: /debug-session (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DebugSession {
  session_id: string;
  run_id: string;
  flow_id: string;
  status: string;
  current_node_id?: string | null;
  breakpoints: string[];
  execution_history?: Array<{
    node_id: string;
    status: string;
    skipped?: boolean;
    output?: unknown;
  }>;
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const DebugSessionPage: React.FC = () => {
  // Start session form
  const [flowId, setFlowId] = useState('');
  const [inputJson, setInputJson] = useState('{}');
  const [breakpointsRaw, setBreakpointsRaw] = useState('');
  const [startLoading, setStartLoading] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // Active session
  const [session, setSession] = useState<DebugSession | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);

  // Breakpoint update
  const [newBreakpoints, setNewBreakpoints] = useState('');
  const [bpError, setBpError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    setStartLoading(true);
    setStartError(null);
    setSession(null);
    try {
      let inputData: unknown;
      try { inputData = JSON.parse(inputJson); } catch { setStartError('Invalid JSON in Input'); setStartLoading(false); return; }
      const bpList = breakpointsRaw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${flowId.trim()}/debug`,
        {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ input_data: inputData, breakpoints: bpList }),
        },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setStartError(data.detail ?? `Error ${resp.status}`); return; }
      setSession(data as DebugSession);
    } catch {
      setStartError('Network error');
    } finally {
      setStartLoading(false);
    }
  }

  async function refreshSession() {
    if (!session) return;
    setSessionError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/debug/${session.session_id}`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setSessionError(data.detail ?? `Error ${resp.status}`); return; }
      setSession(data as DebugSession);
    } catch {
      setSessionError('Network error');
    }
  }

  async function sendAction(action: 'continue' | 'skip') {
    if (!session) return;
    setSessionError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/debug/${session.session_id}/${action}`,
        { method: 'POST', headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setSessionError(data.detail ?? `Error ${resp.status}`); return; }
      setSession(data as DebugSession);
    } catch {
      setSessionError('Network error');
    }
  }

  async function updateBreakpoints() {
    if (!session) return;
    setBpError(null);
    const bpList = newBreakpoints.split(',').map((s) => s.trim()).filter(Boolean);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/debug/${session.session_id}/breakpoints`,
        {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ breakpoints: bpList }),
        },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setBpError(data.detail ?? `Error ${resp.status}`); return; }
      setSession(data as DebugSession);
    } catch {
      setBpError('Network error');
    }
  }

  async function handleAbort() {
    if (!session) return;
    setSessionError(null);
    try {
      await fetch(`${getBaseUrl()}/api/v1/debug/${session.session_id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      setSession(null);
    } catch {
      setSessionError('Network error');
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const statusColor = (s: string) =>
    s === 'completed' || s === 'pass'
      ? 'text-emerald-400'
      : s === 'paused'
      ? 'text-amber-400'
      : s === 'error' || s === 'aborted'
      ? 'text-red-400'
      : 'text-slate-300';

  return (
    <MainLayout title="Debug Session">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Debug Session
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Step-through debugger for flow execution with breakpoints.
        </p>
      </div>

      {/* ---- Start Session Form ---- */}
      {!session && (
        <section
          className="mb-6 rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="start-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Start Debug Session</h2>
          <form onSubmit={handleStart} className="space-y-3" data-testid="start-form">
            <input
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Flow ID"
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
              required
              data-testid="flow-id-input"
            />
            <textarea
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 font-mono text-xs text-slate-200"
              rows={4}
              placeholder='Input JSON (e.g. {"key":"value"})'
              value={inputJson}
              onChange={(e) => setInputJson(e.target.value)}
              data-testid="input-json"
            />
            <input
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Breakpoint node IDs (comma-separated, optional)"
              value={breakpointsRaw}
              onChange={(e) => setBreakpointsRaw(e.target.value)}
              data-testid="breakpoints-input"
            />
            <button
              type="submit"
              disabled={startLoading || !flowId.trim()}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="start-btn"
            >
              {startLoading ? 'Starting…' : 'Start Debug Session'}
            </button>
          </form>
          {startError && (
            <p className="mt-2 text-sm text-red-400" data-testid="start-error">{startError}</p>
          )}
        </section>
      )}

      {/* ---- Active Session ---- */}
      {session && (
        <div data-testid="session-panel">
          {/* Session Header */}
          <div className="mb-4 rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="session-header">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500">Session ID</p>
                <p className="font-mono text-xs text-slate-300" data-testid="session-id">{session.session_id}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Status</p>
                <p className={`font-semibold ${statusColor(session.status)}`} data-testid="session-status">
                  {session.status}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Run ID</p>
                <p className="font-mono text-xs text-slate-400" data-testid="session-run-id">{session.run_id}</p>
              </div>
              {session.current_node_id && (
                <div>
                  <p className="text-xs text-slate-500">Paused At</p>
                  <p className="font-mono text-xs text-amber-400" data-testid="current-node">{session.current_node_id}</p>
                </div>
              )}
            </div>
          </div>

          {sessionError && (
            <p className="mb-3 text-sm text-red-400" data-testid="session-error">{sessionError}</p>
          )}

          {/* Controls */}
          <div className="mb-4 flex flex-wrap gap-2" data-testid="session-controls">
            <button
              onClick={() => sendAction('continue')}
              disabled={session.status !== 'paused'}
              className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
              data-testid="continue-btn"
            >
              Continue
            </button>
            <button
              onClick={() => sendAction('skip')}
              disabled={session.status !== 'paused'}
              className="rounded bg-amber-700 px-3 py-1.5 text-sm text-white hover:bg-amber-600 disabled:opacity-50"
              data-testid="skip-btn"
            >
              Skip Node
            </button>
            <button
              onClick={refreshSession}
              className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600"
              data-testid="refresh-btn"
            >
              Refresh
            </button>
            <button
              onClick={handleAbort}
              className="rounded bg-red-900/40 px-3 py-1.5 text-sm text-red-400 hover:bg-red-900/60"
              data-testid="abort-btn"
            >
              Abort Session
            </button>
          </div>

          {/* Breakpoints */}
          <div className="mb-4 rounded border border-slate-700 bg-slate-800/30 p-3" data-testid="breakpoints-section">
            <p className="mb-2 text-xs font-semibold text-slate-400">
              Breakpoints: {session.breakpoints.join(', ') || 'none'}
            </p>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1 text-xs text-slate-200 placeholder-slate-500"
                placeholder="node-id1, node-id2"
                value={newBreakpoints}
                onChange={(e) => setNewBreakpoints(e.target.value)}
                data-testid="new-breakpoints-input"
              />
              <button
                onClick={updateBreakpoints}
                className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600"
                data-testid="update-bp-btn"
              >
                Update
              </button>
            </div>
            {bpError && <p className="mt-1 text-xs text-red-400" data-testid="bp-error">{bpError}</p>}
          </div>

          {/* Execution History */}
          {Array.isArray(session.execution_history) && session.execution_history.length > 0 && (
            <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="history-section">
              <h2 className="mb-2 text-sm font-semibold text-slate-300">Execution History</h2>
              <ul className="space-y-1">
                {session.execution_history.map((h, i) => (
                  <li key={i} className="flex items-center gap-3 text-xs" data-testid="history-item">
                    <span className="font-mono text-slate-400" data-testid="history-node-id">{h.node_id}</span>
                    <span className={statusColor(h.status)} data-testid="history-status">{h.status}</span>
                    {h.skipped && <span className="text-amber-500">skipped</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </MainLayout>
  );
};

export default DebugSessionPage;
