/**
 * ExecutionDashboardPage - Real-time admin execution monitoring dashboard.
 *
 * Shows all running workflows with kill/pause/resume controls,
 * resource usage per workflow, and aggregate stats.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ExecutionEntry {
  run_id: string;
  flow_id: string;
  flow_name: string;
  user_id: string;
  status: string;
  started_at: number;
  updated_at: number;
  node_count: number;
  completed_nodes: number;
  progress_pct: number;
  input_size_bytes: number;
  output_size_bytes: number;
  paused: boolean;
  killed: boolean;
  duration_ms: number;
}

interface DashboardStats {
  active_count: number;
  total_today: number;
  avg_duration_ms: number;
  kill_count: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string; REACT_APP_API_URL?: string } }).env
      ?.VITE_API_URL ||
    (import.meta as unknown as { env?: { REACT_APP_API_URL?: string } }).env?.REACT_APP_API_URL ||
    'http://localhost:8000'
  );
}

function getAuthToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const resp = await fetch(`${getBaseUrl()}${path}`, { ...options, headers });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}

function truncateId(id: string, len = 8): string {
  return id.length > len ? id.slice(0, len) + '...' : id;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const secs = ms / 1000;
  if (secs < 60) return `${secs.toFixed(1)}s`;
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`;
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, string> = {
  running: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  completed: 'bg-green-500/20 text-green-400 border-green-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  error: 'bg-red-500/20 text-red-400 border-red-500/30',
  paused: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  killed: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || STATUS_COLORS.killed;
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ExecutionDashboardPage: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [activeExecutions, setActiveExecutions] = useState<ExecutionEntry[]>([]);
  const [recentExecutions, setRecentExecutions] = useState<ExecutionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [statsData, activeData, recentData] = await Promise.all([
        apiFetch<DashboardStats>('/api/v1/admin/executions/stats'),
        apiFetch<{ items: ExecutionEntry[] }>('/api/v1/admin/executions/active'),
        apiFetch<{ items: ExecutionEntry[] }>('/api/v1/admin/executions'),
      ]);
      setStats(statsData);
      setActiveExecutions(activeData.items);
      setRecentExecutions(recentData.items.slice(0, 20));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(fetchData, 3000);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [autoRefresh, fetchData]);

  const handleKill = async (runId: string) => {
    if (!window.confirm(`Kill execution ${runId}?`)) return;
    try {
      await apiFetch(`/api/v1/admin/executions/${runId}/kill`, { method: 'POST' });
      fetchData();
    } catch {
      // Error is surfaced on next refresh
    }
  };

  const handlePause = async (runId: string) => {
    try {
      await apiFetch(`/api/v1/admin/executions/${runId}/pause`, { method: 'POST' });
      fetchData();
    } catch {
      // Error is surfaced on next refresh
    }
  };

  const handleResume = async (runId: string) => {
    try {
      await apiFetch(`/api/v1/admin/executions/${runId}/resume`, { method: 'POST' });
      fetchData();
    } catch {
      // Error is surfaced on next refresh
    }
  };

  if (loading) {
    return (
      <MainLayout title="Execution Monitor">
        <div data-testid="execution-dashboard" className="p-6 text-slate-400">
          Loading execution data...
        </div>
      </MainLayout>
    );
  }

  if (error) {
    return (
      <MainLayout title="Execution Monitor">
        <div data-testid="execution-dashboard" className="p-6">
          <div data-testid="error-state" className="rounded border border-red-500/30 bg-red-500/10 p-4 text-red-400">
            {error}
          </div>
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout title="Execution Monitor">
      <div data-testid="execution-dashboard" className="space-y-6 p-6">
        {/* Controls */}
        <div className="flex items-center justify-end gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-slate-600"
            />
            Auto-refresh
          </label>
          <button
            onClick={fetchData}
            className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-600"
          >
            Refresh
          </button>
        </div>

        {/* Stats bar */}
        {stats && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-4">
              <div className="text-sm text-blue-400">Active Now</div>
              <div data-testid="stats-active-count" className="mt-1 text-2xl font-bold text-blue-300">
                {stats.active_count}
              </div>
            </div>
            <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-4">
              <div className="text-sm text-green-400">Total Today</div>
              <div data-testid="stats-total-today" className="mt-1 text-2xl font-bold text-green-300">
                {stats.total_today}
              </div>
            </div>
            <div className="rounded-lg border border-purple-500/30 bg-purple-500/10 p-4">
              <div className="text-sm text-purple-400">Avg Duration</div>
              <div className="mt-1 text-2xl font-bold text-purple-300">
                {formatDuration(stats.avg_duration_ms)}
              </div>
            </div>
            <div className="rounded-lg border border-gray-500/30 bg-gray-500/10 p-4">
              <div className="text-sm text-gray-400">Kill Count</div>
              <div className="mt-1 text-2xl font-bold text-gray-300">{stats.kill_count}</div>
            </div>
          </div>
        )}

        {/* Active Executions */}
        <div>
          <h2 className="mb-3 text-lg font-semibold text-slate-200">Active Executions</h2>
          <div className="overflow-x-auto rounded-lg border border-slate-700">
            <table data-testid="active-executions-table" className="w-full text-sm text-slate-300">
              <thead className="border-b border-slate-700 bg-slate-800/50">
                <tr>
                  <th className="px-4 py-2 text-left">Run ID</th>
                  <th className="px-4 py-2 text-left">Flow</th>
                  <th className="px-4 py-2 text-left">User</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Progress</th>
                  <th className="px-4 py-2 text-left">Duration</th>
                  <th className="px-4 py-2 text-left">Nodes</th>
                  <th className="px-4 py-2 text-left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {activeExecutions.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-6 text-center text-slate-500">
                      No active executions
                    </td>
                  </tr>
                ) : (
                  activeExecutions.map((exec) => (
                    <tr key={exec.run_id} className="border-b border-slate-800 hover:bg-slate-800/30">
                      <td className="px-4 py-2 font-mono text-xs">{truncateId(exec.run_id)}</td>
                      <td className="px-4 py-2">{exec.flow_name || truncateId(exec.flow_id)}</td>
                      <td className="px-4 py-2">{exec.user_id || '-'}</td>
                      <td className="px-4 py-2">
                        <StatusBadge status={exec.status} />
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-700">
                            <div
                              data-testid={`progress-bar-${exec.run_id}`}
                              className="h-full rounded-full bg-blue-500 transition-all"
                              style={{ width: `${Math.min(exec.progress_pct, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-500">
                            {Math.round(exec.progress_pct)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-xs">{formatDuration(exec.duration_ms)}</td>
                      <td className="px-4 py-2 text-xs">
                        {exec.completed_nodes}/{exec.node_count}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex gap-1">
                          {exec.status === 'paused' ? (
                            <button
                              data-testid={`resume-button-${exec.run_id}`}
                              onClick={() => handleResume(exec.run_id)}
                              className="rounded bg-green-600/20 px-2 py-1 text-xs text-green-400 hover:bg-green-600/30"
                            >
                              Resume
                            </button>
                          ) : (
                            <button
                              data-testid={`pause-button-${exec.run_id}`}
                              onClick={() => handlePause(exec.run_id)}
                              className="rounded bg-yellow-600/20 px-2 py-1 text-xs text-yellow-400 hover:bg-yellow-600/30"
                            >
                              Pause
                            </button>
                          )}
                          <button
                            data-testid={`kill-button-${exec.run_id}`}
                            onClick={() => handleKill(exec.run_id)}
                            className="rounded bg-red-600/20 px-2 py-1 text-xs text-red-400 hover:bg-red-600/30"
                          >
                            Kill
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Executions */}
        <div>
          <h2 className="mb-3 text-lg font-semibold text-slate-200">Recent Executions</h2>
          <div className="overflow-x-auto rounded-lg border border-slate-700">
            <table data-testid="recent-executions-table" className="w-full text-sm text-slate-300">
              <thead className="border-b border-slate-700 bg-slate-800/50">
                <tr>
                  <th className="px-4 py-2 text-left">Run ID</th>
                  <th className="px-4 py-2 text-left">Flow</th>
                  <th className="px-4 py-2 text-left">User</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Progress</th>
                  <th className="px-4 py-2 text-left">Duration</th>
                  <th className="px-4 py-2 text-left">Nodes</th>
                </tr>
              </thead>
              <tbody>
                {recentExecutions.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-6 text-center text-slate-500">
                      No recent executions
                    </td>
                  </tr>
                ) : (
                  recentExecutions.map((exec) => (
                    <tr key={exec.run_id} className="border-b border-slate-800 hover:bg-slate-800/30">
                      <td className="px-4 py-2 font-mono text-xs">{truncateId(exec.run_id)}</td>
                      <td className="px-4 py-2">{exec.flow_name || truncateId(exec.flow_id)}</td>
                      <td className="px-4 py-2">{exec.user_id || '-'}</td>
                      <td className="px-4 py-2">
                        <StatusBadge status={exec.status} />
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-700">
                            <div
                              className="h-full rounded-full bg-blue-500 transition-all"
                              style={{ width: `${Math.min(exec.progress_pct, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-500">
                            {Math.round(exec.progress_pct)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-xs">{formatDuration(exec.duration_ms)}</td>
                      <td className="px-4 py-2 text-xs">
                        {exec.completed_nodes}/{exec.node_count}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </MainLayout>
  );
};

export default ExecutionDashboardPage;
