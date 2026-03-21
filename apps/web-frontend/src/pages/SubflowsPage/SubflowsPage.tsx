/**
 * SubflowsPage — Subflow Browser & Cycle Validator (N-84).
 *
 * Wraps:
 *   GET  /api/v1/subflows                  → all workflows usable as subflows
 *   POST /api/v1/subflows/validate         → validate parent+subflow for cycles
 *
 * Route: /subflows (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SubflowEntry {
  id: string;
  name: string;
  description?: string;
  is_subflow_compatible: boolean;
  node_count?: number;
  created_at?: string;
  [key: string]: unknown;
}

interface SubflowsResponse {
  flows: SubflowEntry[];
  total: number;
}

interface ValidateResult {
  valid: boolean;
  error: string | null;
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

const SubflowsPage: React.FC = () => {
  // Subflows list
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subflows, setSubflows] = useState<SubflowEntry[]>([]);
  const [total, setTotal] = useState(0);

  // Validate form
  const [parentId, setParentId] = useState('');
  const [subflowId, setSubflowId] = useState('');
  const [validating, setValidating] = useState(false);
  const [validateResult, setValidateResult] = useState<ValidateResult | null>(null);

  const loadSubflows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/subflows`, { headers: authHeaders() });
      if (!resp.ok) {
        setError(`Failed to load subflows (${resp.status})`);
        return;
      }
      const data: SubflowsResponse = await resp.json();
      setSubflows(data.flows ?? []);
      setTotal(data.total ?? 0);
    } catch {
      setError('Network error loading subflows');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSubflows();
  }, [loadSubflows]);

  const handleValidate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!parentId.trim() || !subflowId.trim()) return;
      setValidating(true);
      setValidateResult(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/subflows/validate`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            parent_flow_id: parentId.trim(),
            subflow_id: subflowId.trim(),
          }),
        });
        if (!resp.ok) {
          setValidateResult({ valid: false, error: `Server error (${resp.status})` });
          return;
        }
        setValidateResult(await resp.json());
      } catch {
        setValidateResult({ valid: false, error: 'Network error' });
      } finally {
        setValidating(false);
      }
    },
    [parentId, subflowId],
  );

  return (
    <MainLayout title="Subflows">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Subflows
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Browse workflows available as subflows and validate for circular dependencies.
          </p>
        </div>
        <button
          onClick={loadSubflows}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* Cycle Validator */}
      <section
        className="mb-6 rounded border border-slate-700 bg-slate-800/40 p-5"
        data-testid="validate-section"
      >
        <p className="mb-4 text-sm font-semibold text-slate-300">Cycle Validator</p>
        <form onSubmit={handleValidate} className="flex flex-col gap-2 sm:flex-row" data-testid="validate-form">
          <input
            type="text"
            value={parentId}
            onChange={(e) => setParentId(e.target.value)}
            placeholder="Parent workflow ID"
            className="flex-1 rounded border border-slate-600 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
            data-testid="parent-id-input"
          />
          <input
            type="text"
            value={subflowId}
            onChange={(e) => setSubflowId(e.target.value)}
            placeholder="Subflow workflow ID"
            className="flex-1 rounded border border-slate-600 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
            data-testid="subflow-id-input"
          />
          <button
            type="submit"
            disabled={validating || !parentId.trim() || !subflowId.trim()}
            className="rounded bg-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
            data-testid="validate-btn"
          >
            {validating ? 'Checking…' : 'Validate'}
          </button>
        </form>

        {validateResult && (
          <div className="mt-3" data-testid="validate-result">
            {validateResult.valid ? (
              <p className="text-sm text-emerald-400" data-testid="validate-ok">
                ✓ No circular dependency detected — safe to use as subflow.
              </p>
            ) : (
              <p className="text-sm text-red-400" data-testid="validate-error">
                ✗ {validateResult.error}
              </p>
            )}
          </div>
        )}
      </section>

      {/* Subflows list */}
      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="subflows-error">{error}</p>
      )}

      {loading && subflows.length === 0 && (
        <p className="text-xs text-slate-500" data-testid="subflows-loading">Loading…</p>
      )}

      {!loading && subflows.length === 0 && !error && (
        <p className="text-xs text-slate-500" data-testid="no-subflows">
          No workflows available. Create a workflow first.
        </p>
      )}

      {subflows.length > 0 && (
        <div data-testid="subflows-panel">
          <p className="mb-3 text-xs text-slate-500">
            {total.toLocaleString()} workflow{total !== 1 ? 's' : ''} available as subflows
          </p>
          <div className="overflow-x-auto" data-testid="subflows-table">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700 text-left text-slate-500">
                  <th className="pb-2 pr-4 font-medium">ID</th>
                  <th className="pb-2 pr-4 font-medium">Name</th>
                  <th className="pb-2 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {subflows.map((sf) => (
                  <tr
                    key={sf.id}
                    className="border-b border-slate-700/40"
                    data-testid="subflow-row"
                  >
                    <td className="py-1.5 pr-4 font-mono text-slate-400">{sf.id}</td>
                    <td className="py-1.5 pr-4 text-slate-300">{sf.name}</td>
                    <td className="py-1.5 text-slate-400">{sf.created_at ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </MainLayout>
  );
};

export default SubflowsPage;
