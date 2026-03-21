/**
 * CostEstimatorPage — Pre-Run Cost Estimator UI (N-93).
 *
 * Wraps:
 *   POST /api/v1/workflows/{flow_id}/estimate-cost  → per-node breakdown + total
 *   POST /api/v1/flows/{flow_id}/estimate-cost       → alternate endpoint for saved flows
 *
 * Route: /cost-estimator (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NodeBreakdown {
  node_id: string;
  node_type: string;
  model?: string;
  estimated_usd: number;
  token_input?: number;
  token_output?: number;
  api_calls?: number;
  [key: string]: unknown;
}

interface EstimateResult {
  estimated_usd: number;
  total_token_input?: number;
  total_token_output?: number;
  breakdown?: NodeBreakdown[];
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

function formatUsd(n: number): string {
  return `$${n.toFixed(6)}`;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const CostEstimatorPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [inputText, setInputText] = useState('');
  const [estimating, setEstimating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EstimateResult | null>(null);

  const handleEstimate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim()) return;
      setEstimating(true);
      setError(null);
      setResult(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/workflows/${encodeURIComponent(flowId.trim())}/estimate-cost`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ input_text: inputText }),
          },
        );
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setError(data.detail ?? `Error ${resp.status}`);
          return;
        }
        setResult(await resp.json());
      } catch {
        setError('Network error during estimation');
      } finally {
        setEstimating(false);
      }
    },
    [flowId, inputText],
  );

  return (
    <MainLayout title="Cost Estimator">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Cost Estimator
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Estimate execution cost for a workflow before running it.
        </p>
      </div>

      {/* Estimate form */}
      <section className="mb-8 rounded border border-slate-700 bg-slate-800/30 p-5">
        <form onSubmit={handleEstimate} className="space-y-4" data-testid="estimate-form">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">
              Workflow / Flow ID
            </label>
            <input
              type="text"
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
              placeholder="e.g. flow-abc-123"
              className="w-full max-w-sm rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
              data-testid="flow-id-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">
              Sample Input Text (used to estimate token counts for LLM nodes)
            </label>
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Enter representative input text…"
              rows={4}
              className="w-full max-w-lg rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
              data-testid="input-text"
            />
          </div>
          <button
            type="submit"
            disabled={estimating || !flowId.trim()}
            className="rounded bg-indigo-700 px-5 py-2 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
            data-testid="estimate-btn"
          >
            {estimating ? 'Estimating…' : 'Estimate Cost'}
          </button>
        </form>

        {error && (
          <p className="mt-3 text-sm text-red-400" data-testid="estimate-error">{error}</p>
        )}
      </section>

      {/* Results */}
      {result && (
        <section data-testid="estimate-result">
          {/* Summary */}
          <div
            className="mb-6 flex flex-wrap gap-4 rounded border border-slate-700 bg-slate-800/30 p-5"
            data-testid="estimate-summary"
          >
            <div>
              <p className="text-xs text-slate-500">Total Estimated Cost</p>
              <p className="mt-1 text-2xl font-bold text-emerald-400" data-testid="total-usd">
                {formatUsd(result.estimated_usd)}
              </p>
            </div>
            {result.total_token_input != null && (
              <div>
                <p className="text-xs text-slate-500">Token Input</p>
                <p className="mt-1 text-lg font-semibold text-slate-300" data-testid="total-token-input">
                  {result.total_token_input.toLocaleString()}
                </p>
              </div>
            )}
            {result.total_token_output != null && (
              <div>
                <p className="text-xs text-slate-500">Token Output</p>
                <p className="mt-1 text-lg font-semibold text-slate-300" data-testid="total-token-output">
                  {result.total_token_output.toLocaleString()}
                </p>
              </div>
            )}
          </div>

          {/* Breakdown table */}
          {Array.isArray(result.breakdown) && result.breakdown.length > 0 && (
            <div className="overflow-x-auto" data-testid="breakdown-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Node ID</th>
                    <th className="pb-2 pr-4 font-medium">Type</th>
                    <th className="pb-2 pr-4 font-medium">Model</th>
                    <th className="pb-2 pr-4 font-medium">Tokens In</th>
                    <th className="pb-2 pr-4 font-medium">Tokens Out</th>
                    <th className="pb-2 font-medium">Est. Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {result.breakdown.map((node) => (
                    <tr
                      key={node.node_id}
                      className="border-b border-slate-700/40"
                      data-testid="breakdown-row"
                    >
                      <td className="py-2 pr-4 font-mono text-slate-400">{node.node_id}</td>
                      <td className="py-2 pr-4 text-slate-300">{node.node_type}</td>
                      <td className="py-2 pr-4 text-slate-400">{node.model ?? '—'}</td>
                      <td className="py-2 pr-4 text-slate-400">
                        {node.token_input != null ? node.token_input.toLocaleString() : '—'}
                      </td>
                      <td className="py-2 pr-4 text-slate-400">
                        {node.token_output != null ? node.token_output.toLocaleString() : '—'}
                      </td>
                      <td className="py-2 font-mono text-emerald-400">
                        {formatUsd(node.estimated_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {Array.isArray(result.breakdown) && result.breakdown.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="no-breakdown">
              No per-node breakdown available.
            </p>
          )}
        </section>
      )}
    </MainLayout>
  );
};

export default CostEstimatorPage;
