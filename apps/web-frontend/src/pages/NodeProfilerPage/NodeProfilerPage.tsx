/**
 * NodeProfilerPage -- Node Performance Profiler UI (N-70).
 *
 * Provides two views:
 *   Workflow Profile  — aggregated per-node timing across all runs
 *                       (GET /api/v1/workflows/{id}/profile)
 *   Execution Profile — single-run per-node timing with bottleneck highlight
 *                       (GET /api/v1/executions/{id}/profile)
 *
 * Route: /node-profiler (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WorkflowNodeStat {
  node_id: string;
  run_count: number;
  avg_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  min_ms: number;
  max_ms: number;
}

interface WorkflowProfile {
  flow_id: string;
  profiled_at: number;
  nodes: WorkflowNodeStat[];
  total_node_types_profiled: number;
}

interface ExecutionNodeEntry {
  node_id: string;
  duration_ms: number;
  is_bottleneck: boolean;
}

interface ExecutionProfile {
  execution_id: string;
  nodes: ExecutionNodeEntry[];
  total_duration_ms: number;
  bottleneck_node_id: string | null;
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

function fmt(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms.toFixed(1)}ms`;
}

/** Map a duration to a heatmap colour class: green → yellow → orange → red */
function heatClass(ms: number, maxMs: number): string {
  if (maxMs === 0) return 'bg-slate-700';
  const ratio = ms / maxMs;
  if (ratio < 0.25) return 'bg-emerald-700';
  if (ratio < 0.5) return 'bg-yellow-600';
  if (ratio < 0.75) return 'bg-orange-600';
  return 'bg-red-600';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface HeatBarProps {
  ms: number;
  maxMs: number;
}

const HeatBar: React.FC<HeatBarProps> = ({ ms, maxMs }) => {
  const pct = maxMs > 0 ? Math.max(2, (ms / maxMs) * 100) : 2;
  return (
    <div className="h-3 w-full rounded bg-slate-800" aria-hidden="true">
      <div
        className={`h-3 rounded ${heatClass(ms, maxMs)} transition-all`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Workflow Profile Panel
// ---------------------------------------------------------------------------

const WorkflowProfilePanel: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [profile, setProfile] = useState<WorkflowProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFetch = useCallback(async () => {
    const id = flowId.trim();
    if (!id) return;
    setLoading(true);
    setError(null);
    setProfile(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/workflows/${id}/profile`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`API returned ${resp.status}`);
        return;
      }
      setProfile(await resp.json());
    } catch {
      setError('Network error fetching workflow profile');
    } finally {
      setLoading(false);
    }
  }, [flowId]);

  const maxMs = profile ? Math.max(...profile.nodes.map((n) => n.avg_ms), 0) : 0;

  return (
    <section data-testid="workflow-profile-panel">
      <h2 className="mb-3 text-lg font-semibold text-slate-200">Workflow Profile</h2>
      <p className="mb-4 text-sm text-slate-400">
        Aggregated per-node timing across all execution runs for a workflow.
      </p>

      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleFetch()}
          placeholder="Workflow ID"
          className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          data-testid="workflow-id-input"
        />
        <button
          onClick={handleFetch}
          disabled={loading || !flowId.trim()}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          data-testid="fetch-workflow-btn"
        >
          {loading ? 'Loading…' : 'Profile'}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300" data-testid="workflow-error">
          {error}
        </div>
      )}

      {profile && (
        <div data-testid="workflow-profile-result">
          <p className="mb-3 text-xs text-slate-500">
            Flow: <span className="text-slate-300">{profile.flow_id}</span>
            {' · '}
            {profile.total_node_types_profiled} node{profile.total_node_types_profiled !== 1 ? 's' : ''} profiled
          </p>
          {profile.nodes.length === 0 ? (
            <p className="text-sm text-slate-500" data-testid="workflow-empty">No execution data yet.</p>
          ) : (
            <div className="overflow-auto rounded border border-slate-700">
              <table className="w-full text-left text-sm text-slate-200" data-testid="workflow-table">
                <thead className="border-b border-slate-700 bg-slate-800/60 text-xs uppercase text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Node ID</th>
                    <th className="px-3 py-2">Runs</th>
                    <th className="px-3 py-2">Avg</th>
                    <th className="px-3 py-2">P50</th>
                    <th className="px-3 py-2">P95</th>
                    <th className="px-3 py-2">P99</th>
                    <th className="px-3 py-2 w-40">Heat</th>
                  </tr>
                </thead>
                <tbody>
                  {profile.nodes
                    .slice()
                    .sort((a, b) => b.avg_ms - a.avg_ms)
                    .map((node) => (
                      <tr key={node.node_id} className="border-b border-slate-800" data-testid="workflow-row">
                        <td className="px-3 py-2 font-mono text-xs text-slate-300">{node.node_id}</td>
                        <td className="px-3 py-2 text-slate-400">{node.run_count}</td>
                        <td className="px-3 py-2 font-medium">{fmt(node.avg_ms)}</td>
                        <td className="px-3 py-2 text-slate-400">{fmt(node.p50_ms)}</td>
                        <td className="px-3 py-2 text-slate-400">{fmt(node.p95_ms)}</td>
                        <td className="px-3 py-2 text-slate-400">{fmt(node.p99_ms)}</td>
                        <td className="px-3 py-2">
                          <HeatBar ms={node.avg_ms} maxMs={maxMs} />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Execution Profile Panel
// ---------------------------------------------------------------------------

const ExecutionProfilePanel: React.FC = () => {
  const [execId, setExecId] = useState('');
  const [profile, setProfile] = useState<ExecutionProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFetch = useCallback(async () => {
    const id = execId.trim();
    if (!id) return;
    setLoading(true);
    setError(null);
    setProfile(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/executions/${id}/profile`, {
        headers: authHeaders(),
      });
      if (resp.status === 404) {
        setError('Execution not found or no logs available');
        return;
      }
      if (!resp.ok) {
        setError(`API returned ${resp.status}`);
        return;
      }
      setProfile(await resp.json());
    } catch {
      setError('Network error fetching execution profile');
    } finally {
      setLoading(false);
    }
  }, [execId]);

  const maxMs = profile ? Math.max(...profile.nodes.map((n) => n.duration_ms), 0) : 0;

  return (
    <section data-testid="execution-profile-panel">
      <h2 className="mb-3 text-lg font-semibold text-slate-200">Execution Profile</h2>
      <p className="mb-4 text-sm text-slate-400">
        Per-node timing for a single execution run. The bottleneck node is highlighted.
      </p>

      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={execId}
          onChange={(e) => setExecId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleFetch()}
          placeholder="Execution / Run ID"
          className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          data-testid="execution-id-input"
        />
        <button
          onClick={handleFetch}
          disabled={loading || !execId.trim()}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          data-testid="fetch-execution-btn"
        >
          {loading ? 'Loading…' : 'Profile'}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300" data-testid="execution-error">
          {error}
        </div>
      )}

      {profile && (
        <div data-testid="execution-profile-result">
          <p className="mb-3 text-xs text-slate-500">
            Run: <span className="text-slate-300">{profile.execution_id}</span>
            {' · '}
            Total: <span className="text-slate-300">{fmt(profile.total_duration_ms)}</span>
            {profile.bottleneck_node_id && (
              <>
                {' · '}
                Bottleneck: <span className="font-mono text-red-400">{profile.bottleneck_node_id}</span>
              </>
            )}
          </p>
          {profile.nodes.length === 0 ? (
            <p className="text-sm text-slate-500" data-testid="execution-empty">No node timing data.</p>
          ) : (
            <div className="space-y-2" data-testid="execution-timeline">
              {profile.nodes.map((node) => (
                <div
                  key={node.node_id}
                  className={`rounded border px-3 py-2 ${
                    node.is_bottleneck
                      ? 'border-red-700 bg-red-900/20'
                      : 'border-slate-700 bg-slate-800/40'
                  }`}
                  data-testid={node.is_bottleneck ? 'bottleneck-node' : 'execution-node'}
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-mono text-xs text-slate-300">{node.node_id}</span>
                    <span className={`text-xs font-medium ${node.is_bottleneck ? 'text-red-400' : 'text-slate-300'}`}>
                      {fmt(node.duration_ms)}
                      {node.is_bottleneck && ' ⚡ bottleneck'}
                    </span>
                  </div>
                  <HeatBar ms={node.duration_ms} maxMs={maxMs} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const NodeProfilerPage: React.FC = () => {
  return (
    <MainLayout title="Node Profiler">
      <h1 className="mb-6 text-2xl font-bold text-slate-100" data-testid="page-title">
        Node Performance Profiler
      </h1>
      <p className="mb-8 text-sm text-slate-400">
        Inspect per-node execution timing to identify bottlenecks and optimise workflow performance.
      </p>

      <div className="grid gap-10 lg:grid-cols-2">
        <WorkflowProfilePanel />
        <ExecutionProfilePanel />
      </div>
    </MainLayout>
  );
};

export default NodeProfilerPage;
