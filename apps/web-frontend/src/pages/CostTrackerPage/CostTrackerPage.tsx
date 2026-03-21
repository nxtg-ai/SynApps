/**
 * CostTrackerPage — Execution Cost & Workflow Cost Summary (N-81).
 *
 * Wraps:
 *   GET /api/v1/executions/{execution_id}/cost  → per-node cost breakdown
 *   GET /api/v1/workflows/{flow_id}/cost-summary → aggregate stats + run history
 *
 * Route: /cost-tracker (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NodeCost {
  node_id: string;
  node_type?: string;
  tokens?: number;
  cost_usd?: number;
  [key: string]: unknown;
}

interface ExecutionCost {
  execution_id: string;
  flow_id: string;
  node_costs: NodeCost[];
  total_usd: number;
  total_tokens: number;
  created_at: string;
}

interface CostRecord {
  execution_id: string;
  flow_id: string;
  node_costs: NodeCost[];
  total_usd: number;
  total_tokens: number;
  created_at: string;
}

interface WorkflowCostSummary {
  flow_id: string;
  run_count: number;
  total_usd: number;
  avg_usd_per_run: number;
  total_tokens: number;
  avg_tokens_per_run: number;
  records: CostRecord[];
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

function formatUsd(n: number): string {
  return `$${n.toFixed(6)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

// ---------------------------------------------------------------------------
// ExecutionCostPanel
// ---------------------------------------------------------------------------

const ExecutionCostPanel: React.FC = () => {
  const [execId, setExecId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExecutionCost | null>(null);

  const handleLookup = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!execId.trim()) return;
      setLoading(true);
      setError(null);
      setResult(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/executions/${execId.trim()}/cost`, {
          headers: authHeaders(),
        });
        if (!resp.ok) {
          setError(resp.status === 404 ? 'No cost record found for this execution ID.' : `Error ${resp.status}`);
          return;
        }
        setResult(await resp.json());
      } catch {
        setError('Network error');
      } finally {
        setLoading(false);
      }
    },
    [execId],
  );

  return (
    <section
      className="mb-6 rounded border border-slate-700 bg-slate-800/40 p-5"
      data-testid="exec-cost-section"
    >
      <p className="mb-4 text-sm font-semibold text-slate-300">Execution Cost Lookup</p>

      <form onSubmit={handleLookup} className="mb-4 flex gap-2" data-testid="exec-cost-form">
        <input
          type="text"
          value={execId}
          onChange={(e) => setExecId(e.target.value)}
          placeholder="Execution ID"
          className="flex-1 rounded border border-slate-600 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          data-testid="exec-id-input"
        />
        <button
          type="submit"
          disabled={loading || !execId.trim()}
          className="rounded bg-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="exec-cost-btn"
        >
          {loading ? 'Loading…' : 'Look Up'}
        </button>
      </form>

      {error && (
        <p className="mb-3 text-sm text-red-400" data-testid="exec-cost-error">{error}</p>
      )}

      {result && (
        <div data-testid="exec-cost-result">
          <div className="mb-3 flex gap-6 text-xs text-slate-400">
            <span>
              Execution: <span className="font-mono text-slate-300">{result.execution_id}</span>
            </span>
            <span>
              Flow: <span className="font-mono text-slate-300">{result.flow_id}</span>
            </span>
            <span data-testid="exec-total-usd">
              Total: <span className="text-emerald-400">{formatUsd(result.total_usd)}</span>
            </span>
            <span data-testid="exec-total-tokens">
              Tokens: <span className="text-slate-300">{formatTokens(result.total_tokens)}</span>
            </span>
          </div>

          {result.node_costs.length > 0 ? (
            <div className="overflow-x-auto" data-testid="node-cost-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Node ID</th>
                    <th className="pb-2 pr-4 font-medium">Type</th>
                    <th className="pb-2 pr-4 font-medium">Tokens</th>
                    <th className="pb-2 font-medium">Cost (USD)</th>
                  </tr>
                </thead>
                <tbody>
                  {result.node_costs.map((nc, i) => (
                    <tr
                      key={nc.node_id ?? i}
                      className="border-b border-slate-700/40"
                      data-testid="node-cost-row"
                    >
                      <td className="py-1.5 pr-4 font-mono text-slate-300">{nc.node_id}</td>
                      <td className="py-1.5 pr-4 text-slate-400">{nc.node_type ?? '—'}</td>
                      <td className="py-1.5 pr-4 text-slate-300">
                        {nc.tokens != null ? formatTokens(nc.tokens) : '—'}
                      </td>
                      <td className="py-1.5 text-emerald-400">
                        {nc.cost_usd != null ? formatUsd(nc.cost_usd) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-slate-500" data-testid="no-node-costs">No per-node cost breakdown available.</p>
          )}
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// WorkflowCostPanel
// ---------------------------------------------------------------------------

const WorkflowCostPanel: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<WorkflowCostSummary | null>(null);

  const handleLookup = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim()) return;
      setLoading(true);
      setError(null);
      setSummary(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/workflows/${flowId.trim()}/cost-summary`, {
          headers: authHeaders(),
        });
        if (!resp.ok) {
          setError(`Error ${resp.status}`);
          return;
        }
        setSummary(await resp.json());
      } catch {
        setError('Network error');
      } finally {
        setLoading(false);
      }
    },
    [flowId],
  );

  return (
    <section
      className="rounded border border-slate-700 bg-slate-800/40 p-5"
      data-testid="workflow-cost-section"
    >
      <p className="mb-4 text-sm font-semibold text-slate-300">Workflow Cost Summary</p>

      <form onSubmit={handleLookup} className="mb-4 flex gap-2" data-testid="workflow-cost-form">
        <input
          type="text"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          placeholder="Workflow / Flow ID"
          className="flex-1 rounded border border-slate-600 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          data-testid="flow-id-input"
        />
        <button
          type="submit"
          disabled={loading || !flowId.trim()}
          className="rounded bg-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="workflow-cost-btn"
        >
          {loading ? 'Loading…' : 'Look Up'}
        </button>
      </form>

      {error && (
        <p className="mb-3 text-sm text-red-400" data-testid="workflow-cost-error">{error}</p>
      )}

      {summary && (
        <div data-testid="workflow-cost-result">
          {summary.run_count === 0 ? (
            <p className="text-xs text-slate-500" data-testid="no-runs">No cost records for this workflow.</p>
          ) : (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                {[
                  { label: 'Runs', value: summary.run_count.toLocaleString(), testId: 'stat-runs' },
                  { label: 'Total Cost', value: formatUsd(summary.total_usd), testId: 'stat-total-usd' },
                  { label: 'Avg / Run', value: formatUsd(summary.avg_usd_per_run), testId: 'stat-avg-usd' },
                  { label: 'Total Tokens', value: formatTokens(summary.total_tokens), testId: 'stat-total-tokens' },
                  { label: 'Avg Tokens', value: formatTokens(summary.avg_tokens_per_run), testId: 'stat-avg-tokens' },
                ].map((s) => (
                  <div
                    key={s.label}
                    className="rounded border border-slate-700 bg-slate-900/40 p-3 text-center"
                    data-testid={s.testId}
                  >
                    <p className="text-xs text-slate-500">{s.label}</p>
                    <p className="mt-1 text-sm font-semibold text-emerald-400">{s.value}</p>
                  </div>
                ))}
              </div>

              <div className="overflow-x-auto" data-testid="run-history-table">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-700 text-left text-slate-500">
                      <th className="pb-2 pr-4 font-medium">Execution ID</th>
                      <th className="pb-2 pr-4 font-medium">Cost (USD)</th>
                      <th className="pb-2 pr-4 font-medium">Tokens</th>
                      <th className="pb-2 font-medium">Recorded At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.records.map((rec) => (
                      <tr
                        key={rec.execution_id}
                        className="border-b border-slate-700/40"
                        data-testid="run-history-row"
                      >
                        <td className="py-1.5 pr-4 font-mono text-slate-300">{rec.execution_id}</td>
                        <td className="py-1.5 pr-4 text-emerald-400">{formatUsd(rec.total_usd)}</td>
                        <td className="py-1.5 pr-4 text-slate-300">{formatTokens(rec.total_tokens)}</td>
                        <td className="py-1.5 text-slate-400">{rec.created_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const CostTrackerPage: React.FC = () => {
  return (
    <MainLayout title="Cost Tracker">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Cost Tracker
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Execution cost breakdowns and per-workflow spend summaries.
        </p>
      </div>

      <ExecutionCostPanel />
      <WorkflowCostPanel />
    </MainLayout>
  );
};

export default CostTrackerPage;
