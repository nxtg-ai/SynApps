/**
 * TaskMonitorPage — Async Task Monitor UI (N-92).
 *
 * Wraps:
 *   GET /api/v1/tasks              → list all tasks (with optional status filter)
 *   GET /api/v1/tasks/{task_id}    → get single task detail
 *
 * Route: /task-monitor (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Task {
  task_id: string;
  status: string;
  created_at?: string;
  completed_at?: string;
  result?: unknown;
  error?: string;
  [key: string]: unknown;
}

type StatusFilter = '' | 'pending' | 'running' | 'completed' | 'failed';

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
];

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

function statusBadgeColor(status: string): string {
  switch (status) {
    case 'completed': return 'bg-emerald-900/40 text-emerald-400';
    case 'running': return 'bg-indigo-900/40 text-indigo-400';
    case 'pending': return 'bg-slate-700 text-slate-400';
    case 'failed': return 'bg-red-900/40 text-red-400';
    default: return 'bg-slate-700 text-slate-400';
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const TaskMonitorPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('');

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detail, setDetail] = useState<Task | null>(null);

  const loadTasks = useCallback(
    async (filter: StatusFilter = statusFilter) => {
      setLoading(true);
      setError(null);
      try {
        const url = filter
          ? `${getBaseUrl()}/tasks?status=${encodeURIComponent(filter)}`
          : `${getBaseUrl()}/tasks`;
        const resp = await fetch(url, { headers: authHeaders() });
        if (!resp.ok) {
          setError(`Failed to load tasks (${resp.status})`);
          return;
        }
        const data = await resp.json();
        const list: Task[] = Array.isArray(data)
          ? data
          : Array.isArray(data.tasks)
            ? data.tasks
            : [];
        setTasks(list);
      } catch {
        setError('Network error loading tasks');
      } finally {
        setLoading(false);
      }
    },
    [statusFilter],
  );

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const applyFilter = useCallback(
    (filter: StatusFilter) => {
      setStatusFilter(filter);
      loadTasks(filter);
    },
    [loadTasks],
  );

  const selectTask = useCallback(async (task: Task) => {
    setSelectedId(task.task_id);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/tasks/${encodeURIComponent(task.task_id)}`,
        { headers: authHeaders() },
      );
      if (!resp.ok) {
        setDetailError(`Failed to load task (${resp.status})`);
        return;
      }
      setDetail(await resp.json());
    } catch {
      setDetailError('Network error loading task detail');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  return (
    <MainLayout title="Task Monitor">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Task Monitor
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Monitor async task queue status and results.
          </p>
        </div>
        <button
          onClick={() => loadTasks()}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* Status filter tabs */}
      <div className="mb-4 flex gap-1" data-testid="filter-bar">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => applyFilter(f.value)}
            className={`rounded px-3 py-1 text-xs ${
              statusFilter === f.value
                ? 'bg-indigo-700 text-white'
                : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
            data-testid={`filter-${f.value || 'all'}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="flex gap-6">
        {/* Left: task list */}
        <div className="w-96 shrink-0">
          {error && (
            <p className="mb-3 text-sm text-red-400" data-testid="tasks-error">{error}</p>
          )}
          {loading && tasks.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="tasks-loading">Loading…</p>
          )}
          {!loading && tasks.length === 0 && !error && (
            <p className="text-xs text-slate-500" data-testid="no-tasks">
              No tasks found.
            </p>
          )}
          {tasks.length > 0 && (
            <div className="overflow-x-auto rounded border border-slate-700" data-testid="tasks-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-800/50 text-left text-slate-500">
                    <th className="px-3 py-2 font-medium">Task ID</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((task) => (
                    <tr
                      key={task.task_id}
                      onClick={() => selectTask(task)}
                      className={`cursor-pointer border-b border-slate-700/40 hover:bg-slate-800/50 ${
                        selectedId === task.task_id ? 'bg-slate-800' : ''
                      }`}
                      data-testid="task-row"
                    >
                      <td className="max-w-[200px] truncate px-3 py-2 font-mono text-slate-300">
                        {task.task_id}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded px-1.5 py-0.5 ${statusBadgeColor(task.status)}`}
                          data-testid="status-badge"
                        >
                          {task.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right: task detail */}
        <div className="flex-1">
          {!selectedId && (
            <p className="text-sm text-slate-500" data-testid="no-task-selected">
              Select a task to view details.
            </p>
          )}

          {selectedId && detailLoading && (
            <p className="text-xs text-slate-500" data-testid="detail-loading">
              Loading task details…
            </p>
          )}

          {selectedId && detailError && (
            <p className="text-sm text-red-400" data-testid="detail-error">{detailError}</p>
          )}

          {selectedId && detail && (
            <div className="space-y-4" data-testid="task-detail">
              <div className="rounded border border-slate-700 bg-slate-800/30 px-4 py-3">
                <p className="text-xs text-slate-500">Task ID</p>
                <p className="font-mono text-sm text-slate-300" data-testid="detail-task-id">
                  {detail.task_id}
                </p>
              </div>

              <div className="flex gap-4">
                <div className="rounded border border-slate-700 bg-slate-800/30 px-4 py-3">
                  <p className="text-xs text-slate-500">Status</p>
                  <span
                    className={`mt-1 inline-block rounded px-2 py-0.5 text-xs font-semibold ${statusBadgeColor(detail.status)}`}
                    data-testid="detail-status"
                  >
                    {detail.status}
                  </span>
                </div>

                {detail.created_at && (
                  <div className="rounded border border-slate-700 bg-slate-800/30 px-4 py-3">
                    <p className="text-xs text-slate-500">Created</p>
                    <p className="mt-1 text-xs text-slate-300">
                      {new Date(detail.created_at).toLocaleString()}
                    </p>
                  </div>
                )}

                {detail.completed_at && (
                  <div className="rounded border border-slate-700 bg-slate-800/30 px-4 py-3">
                    <p className="text-xs text-slate-500">Completed</p>
                    <p className="mt-1 text-xs text-slate-300">
                      {new Date(detail.completed_at).toLocaleString()}
                    </p>
                  </div>
                )}
              </div>

              {detail.error && (
                <section data-testid="detail-error-section">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Error
                  </h3>
                  <pre className="rounded bg-red-900/20 p-3 text-xs text-red-300">
                    {detail.error}
                  </pre>
                </section>
              )}

              {detail.result !== undefined && detail.result !== null && (
                <section data-testid="detail-result-section">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Result
                  </h3>
                  <pre className="max-h-60 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300">
                    {typeof detail.result === 'string'
                      ? detail.result
                      : JSON.stringify(detail.result, null, 2)}
                  </pre>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </MainLayout>
  );
};

export default TaskMonitorPage;
