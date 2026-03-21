/**
 * RunsPage — Paginated run list + single-run detail (N-121).
 *
 * Covers:
 *   GET /api/v1/runs               → paginated list of all workflow runs
 *   GET /api/v1/runs/{run_id}      → single run detail
 *
 * Route: /runs (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Run {
  run_id: string;
  flow_id?: string;
  status: string;
  start_time?: number;
  progress?: number;
  total_steps?: number;
}

interface RunDetail extends Run {
  input_data?: unknown;
  results?: Record<string, unknown>;
  completed_applets?: string[];
  current_applet?: string | null;
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
  if (s === 'completed') return 'text-emerald-400';
  if (s === 'failed' || s === 'error') return 'text-red-400';
  if (s === 'running') return 'text-blue-400';
  return 'text-slate-400';
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const RunsPage: React.FC = () => {
  // List
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [runs, setRuns] = useState<Run[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [totalItems, setTotalItems] = useState<number | null>(null);

  // Detail
  const [detailRunId, setDetailRunId] = useState('');
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function loadRuns(p = page) {
    setListLoading(true);
    setListError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/runs?page=${p}&page_size=${pageSize}`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setListError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      const items = data.items ?? data.runs ?? data;
      setRuns(Array.isArray(items) ? items : []);
      if (data.total != null) setTotalItems(data.total as number);
    } catch {
      setListError('Network error');
    } finally {
      setListLoading(false);
    }
  }

  async function loadDetail(runId: string) {
    if (!runId.trim()) return;
    setDetailLoading(true);
    setDetailError(null);
    setDetail(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/runs/${encodeURIComponent(runId.trim())}`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setDetailError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setDetail(data as RunDetail);
    } catch {
      setDetailError('Network error');
    } finally {
      setDetailLoading(false);
    }
  }

  function handleDetailFetch(e: React.FormEvent) {
    e.preventDefault();
    loadDetail(detailRunId);
  }

  function handleRowClick(runId: string) {
    setDetailRunId(runId);
    loadDetail(runId);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Runs">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Workflow Runs
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Browse all runs and inspect individual run details.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* ---- Run List ---- */}
        <section data-testid="list-section">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">All Runs</h2>
            <button
              onClick={() => loadRuns(1)}
              className="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-500"
              data-testid="load-runs-btn"
            >
              Load
            </button>
          </div>

          {listError && (
            <p className="mb-2 text-xs text-red-400" data-testid="list-error">{listError}</p>
          )}
          {listLoading && (
            <p className="text-xs text-slate-500" data-testid="list-loading">Loading…</p>
          )}
          {!listLoading && runs.length === 0 && !listError && (
            <p className="text-xs text-slate-500" data-testid="no-runs">
              Click Load to fetch runs.
            </p>
          )}

          {runs.length > 0 && (
            <>
              {totalItems != null && (
                <p className="mb-2 text-xs text-slate-500" data-testid="total-count">
                  {totalItems} total
                </p>
              )}
              <div className="overflow-x-auto" data-testid="runs-table">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-700 text-left text-slate-500">
                      <th className="pb-2 pr-4 font-medium">Run ID</th>
                      <th className="pb-2 pr-4 font-medium">Flow</th>
                      <th className="pb-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr
                        key={r.run_id}
                        className="cursor-pointer border-b border-slate-700/40 hover:bg-slate-800/30"
                        onClick={() => handleRowClick(r.run_id)}
                        data-testid="run-row"
                      >
                        <td className="py-2 pr-4 font-mono text-slate-300" data-testid="run-row-id">
                          {r.run_id.slice(0, 12)}…
                        </td>
                        <td className="py-2 pr-4 text-slate-400">{r.flow_id ?? '—'}</td>
                        <td className={`py-2 font-medium ${statusColor(r.status)}`} data-testid="run-row-status">
                          {r.status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="mt-3 flex items-center gap-3" data-testid="pagination">
                <button
                  disabled={page <= 1}
                  onClick={() => { setPage(page - 1); loadRuns(page - 1); }}
                  className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                  data-testid="prev-btn"
                >
                  Prev
                </button>
                <span className="text-xs text-slate-500" data-testid="page-indicator">
                  Page {page}
                </span>
                <button
                  onClick={() => { setPage(page + 1); loadRuns(page + 1); }}
                  className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600"
                  data-testid="next-btn"
                >
                  Next
                </button>
              </div>
            </>
          )}
        </section>

        {/* ---- Run Detail ---- */}
        <section data-testid="detail-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Run Detail</h2>
          <form onSubmit={handleDetailFetch} className="mb-4 flex gap-2" data-testid="detail-form">
            <input
              className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Run ID"
              value={detailRunId}
              onChange={(e) => setDetailRunId(e.target.value)}
              data-testid="detail-run-id-input"
            />
            <button
              type="submit"
              disabled={detailLoading || !detailRunId.trim()}
              className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="detail-fetch-btn"
            >
              {detailLoading ? '…' : 'Fetch'}
            </button>
          </form>

          {detailError && (
            <p className="mb-2 text-xs text-red-400" data-testid="detail-error">{detailError}</p>
          )}

          {detail && (
            <div
              className="rounded border border-slate-700 bg-slate-800/30 p-4 space-y-3"
              data-testid="run-detail"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-slate-400" data-testid="detail-run-id">
                  {detail.run_id}
                </span>
                <span className={`text-sm font-medium ${statusColor(detail.status)}`} data-testid="detail-status">
                  {detail.status}
                </span>
              </div>
              {detail.flow_id && (
                <p className="text-xs text-slate-500">
                  Flow: <span className="font-mono text-slate-400" data-testid="detail-flow-id">{detail.flow_id}</span>
                </p>
              )}
              {detail.progress != null && detail.total_steps != null && (
                <p className="text-xs text-slate-500" data-testid="detail-progress">
                  Progress: {detail.progress} / {detail.total_steps}
                </p>
              )}
              {detail.current_applet && (
                <p className="text-xs text-slate-500">
                  Current: <span className="text-slate-400">{detail.current_applet}</span>
                </p>
              )}
              {detail.completed_applets && detail.completed_applets.length > 0 && (
                <div data-testid="completed-applets">
                  <p className="text-xs text-slate-500">Completed nodes:</p>
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {detail.completed_applets.map((a) => (
                      <li key={a} className="rounded bg-slate-700 px-2 py-0.5 font-mono text-xs text-slate-400">
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default RunsPage;
