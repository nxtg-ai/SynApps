/**
 * AnalyticsDetailPage — Per-flow and per-node analytics (N-116).
 *
 * Covers:
 *   GET /api/v1/analytics/workflows  → per-flow execution stats
 *   GET /api/v1/analytics/nodes      → per-node execution stats
 *
 * Route: /analytics-detail (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WorkflowStat {
  flow_id: string;
  run_count: number;
  success_count: number;
  error_count: number;
  avg_duration_ms?: number;
}

interface NodeStat {
  node_id: string;
  node_type: string;
  flow_id?: string;
  execution_count: number;
  success_count: number;
  error_count: number;
  avg_duration_ms?: number;
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

const AnalyticsDetailPage: React.FC = () => {
  const [tab, setTab] = useState<'workflows' | 'nodes'>('workflows');
  const [flowIdFilter, setFlowIdFilter] = useState('');

  // Workflow analytics
  const [workflows, setWorkflows] = useState<WorkflowStat[]>([]);
  const [workflowsLoading, setWorkflowsLoading] = useState(false);
  const [workflowsError, setWorkflowsError] = useState<string | null>(null);

  // Node analytics
  const [nodes, setNodes] = useState<NodeStat[]>([]);
  const [nodesLoading, setNodesLoading] = useState(false);
  const [nodesError, setNodesError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function loadWorkflows() {
    setWorkflowsLoading(true);
    setWorkflowsError(null);
    try {
      const params = flowIdFilter.trim() ? `?flow_id=${encodeURIComponent(flowIdFilter.trim())}` : '';
      const resp = await fetch(`${getBaseUrl()}/api/v1/analytics/workflows${params}`, {
        headers: authHeaders(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setWorkflowsError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      const raw = data.workflows ?? data;
      setWorkflows(Array.isArray(raw) ? raw : []);
    } catch {
      setWorkflowsError('Network error');
    } finally {
      setWorkflowsLoading(false);
    }
  }

  async function loadNodes() {
    setNodesLoading(true);
    setNodesError(null);
    try {
      const params = flowIdFilter.trim() ? `?flow_id=${encodeURIComponent(flowIdFilter.trim())}` : '';
      const resp = await fetch(`${getBaseUrl()}/api/v1/analytics/nodes${params}`, {
        headers: authHeaders(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setNodesError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      const raw = data.nodes ?? data;
      setNodes(Array.isArray(raw) ? raw : []);
    } catch {
      setNodesError('Network error');
    } finally {
      setNodesLoading(false);
    }
  }

  function handleLoad() {
    if (tab === 'workflows') {
      loadWorkflows();
    } else {
      loadNodes();
    }
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  function pct(success: number, total: number): string {
    if (total === 0) return '—';
    return `${Math.round((success / total) * 100)}%`;
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Analytics Detail">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Analytics Detail
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Per-flow and per-node execution statistics.
        </p>
      </div>

      {/* Controls */}
      <div className="mb-6 flex flex-wrap items-center gap-3" data-testid="controls">
        <input
          className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
          placeholder="Flow ID filter (optional)"
          value={flowIdFilter}
          onChange={(e) => setFlowIdFilter(e.target.value)}
          data-testid="flow-id-filter"
        />
        <button
          onClick={handleLoad}
          className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500"
          data-testid="load-btn"
        >
          Load
        </button>
      </div>

      {/* Tabs */}
      <div className="mb-4 flex gap-2" data-testid="tabs">
        {(['workflows', 'nodes'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded px-4 py-1.5 text-sm font-medium ${
              tab === t
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:text-slate-200'
            }`}
            data-testid={`tab-${t}`}
          >
            {t === 'workflows' ? 'Workflow Stats' : 'Node Stats'}
          </button>
        ))}
      </div>

      {/* ---- Workflow Stats tab ---- */}
      {tab === 'workflows' && (
        <section data-testid="workflows-section">
          {workflowsError && (
            <p className="mb-3 text-sm text-red-400" data-testid="workflows-error">
              {workflowsError}
            </p>
          )}
          {workflowsLoading && (
            <p className="text-sm text-slate-500" data-testid="workflows-loading">Loading…</p>
          )}
          {!workflowsLoading && workflows.length === 0 && !workflowsError && (
            <p className="text-sm text-slate-500" data-testid="no-workflows">
              No workflow analytics yet. Click Load.
            </p>
          )}
          {workflows.length > 0 && (
            <div className="overflow-x-auto" data-testid="workflows-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Flow ID</th>
                    <th className="pb-2 pr-4 font-medium">Runs</th>
                    <th className="pb-2 pr-4 font-medium">Success</th>
                    <th className="pb-2 pr-4 font-medium">Errors</th>
                    <th className="pb-2 pr-4 font-medium">Success %</th>
                    <th className="pb-2 font-medium">Avg Duration (ms)</th>
                  </tr>
                </thead>
                <tbody>
                  {workflows.map((w) => (
                    <tr
                      key={w.flow_id}
                      className="border-b border-slate-700/40"
                      data-testid="workflow-row"
                    >
                      <td className="py-2 pr-4 font-mono text-slate-300" data-testid="workflow-flow-id">
                        {w.flow_id}
                      </td>
                      <td className="py-2 pr-4 text-slate-300">{w.run_count}</td>
                      <td className="py-2 pr-4 text-emerald-400">{w.success_count}</td>
                      <td className="py-2 pr-4 text-red-400">{w.error_count}</td>
                      <td className="py-2 pr-4 text-slate-300">{pct(w.success_count, w.run_count)}</td>
                      <td className="py-2 text-slate-400">
                        {w.avg_duration_ms != null ? Math.round(w.avg_duration_ms) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* ---- Node Stats tab ---- */}
      {tab === 'nodes' && (
        <section data-testid="nodes-section">
          {nodesError && (
            <p className="mb-3 text-sm text-red-400" data-testid="nodes-error">
              {nodesError}
            </p>
          )}
          {nodesLoading && (
            <p className="text-sm text-slate-500" data-testid="nodes-loading">Loading…</p>
          )}
          {!nodesLoading && nodes.length === 0 && !nodesError && (
            <p className="text-sm text-slate-500" data-testid="no-nodes">
              No node analytics yet. Click Load.
            </p>
          )}
          {nodes.length > 0 && (
            <div className="overflow-x-auto" data-testid="nodes-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Node ID</th>
                    <th className="pb-2 pr-4 font-medium">Type</th>
                    <th className="pb-2 pr-4 font-medium">Executions</th>
                    <th className="pb-2 pr-4 font-medium">Success</th>
                    <th className="pb-2 pr-4 font-medium">Errors</th>
                    <th className="pb-2 font-medium">Avg Duration (ms)</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((n) => (
                    <tr
                      key={n.node_id}
                      className="border-b border-slate-700/40"
                      data-testid="node-row"
                    >
                      <td className="py-2 pr-4 font-mono text-slate-300" data-testid="node-id">
                        {n.node_id}
                      </td>
                      <td className="py-2 pr-4 text-slate-400">{n.node_type}</td>
                      <td className="py-2 pr-4 text-slate-300">{n.execution_count}</td>
                      <td className="py-2 pr-4 text-emerald-400">{n.success_count}</td>
                      <td className="py-2 pr-4 text-red-400">{n.error_count}</td>
                      <td className="py-2 text-slate-400">
                        {n.avg_duration_ms != null ? Math.round(n.avg_duration_ms) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </MainLayout>
  );
};

export default AnalyticsDetailPage;
