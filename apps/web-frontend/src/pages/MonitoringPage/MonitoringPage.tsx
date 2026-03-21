/**
 * MonitoringPage — Workflow Health + Alert Rules Dashboard (N-71).
 *
 * Two panels:
 *   Workflow Health  — aggregated per-workflow health (healthy/degraded/critical)
 *                      GET /api/v1/monitoring/workflows?window_hours={n}
 *   Alert Rules      — CRUD for threshold-based alert rules
 *                      GET/POST/PUT/DELETE /api/v1/monitoring/alerts
 *
 * Route: /monitoring (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WorkflowHealth {
  flow_id: string;
  run_count: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  error_rate: number;
  avg_duration_seconds: number;
  p95_duration_seconds: number;
  last_run_at: number | null;
  health_status: 'healthy' | 'degraded' | 'critical';
}

interface AlertRule {
  id: string;
  workflow_id: string;
  metric: string;
  operator: string;
  threshold: number;
  window_minutes: number;
  action_type: string;
  action_config: Record<string, unknown>;
  enabled: boolean;
  created_at: number;
  last_triggered_at: number | null;
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

function formatDuration(seconds: number): string {
  if (seconds >= 60) return `${(seconds / 60).toFixed(1)}m`;
  return `${seconds.toFixed(1)}s`;
}

function formatDate(epoch: number): string {
  return new Date(epoch * 1000).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const STATUS_STYLES: Record<string, string> = {
  healthy:  'bg-emerald-900/40 text-emerald-300 border-emerald-700',
  degraded: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  critical: 'bg-red-900/40 text-red-300 border-red-700',
};

const STATUS_DOT: Record<string, string> = {
  healthy:  'bg-emerald-400',
  degraded: 'bg-yellow-400',
  critical: 'bg-red-400',
};

// ---------------------------------------------------------------------------
// Workflow Health Panel
// ---------------------------------------------------------------------------

const HealthPanel: React.FC = () => {
  const [workflows, setWorkflows] = useState<WorkflowHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [windowHours, setWindowHours] = useState(24);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/monitoring/workflows?window_hours=${windowHours}`,
        { headers: authHeaders() },
      );
      if (!resp.ok) {
        setError(`API returned ${resp.status}`);
        return;
      }
      const data: { workflows: WorkflowHealth[] } = await resp.json();
      setWorkflows(data.workflows ?? []);
    } catch {
      setError('Network error loading workflow health');
    } finally {
      setLoading(false);
    }
  }, [windowHours]);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  return (
    <section data-testid="health-panel">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-200">Workflow Health</h2>
        <div className="flex items-center gap-2">
          <label htmlFor="window-select" className="text-xs text-slate-400">Window:</label>
          <select
            id="window-select"
            value={windowHours}
            onChange={(e) => setWindowHours(Number(e.target.value))}
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:outline-none"
            data-testid="window-select"
          >
            {[1, 6, 12, 24, 48, 168].map((h) => (
              <option key={h} value={h}>{h}h</option>
            ))}
          </select>
          <button
            onClick={fetchHealth}
            className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600"
            data-testid="refresh-health-btn"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300" data-testid="health-error">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-10 text-center text-slate-400" data-testid="health-loading">Loading…</div>
      ) : workflows.length === 0 ? (
        <div className="py-10 text-center text-slate-500" data-testid="health-empty">
          No workflow runs in the last {windowHours}h.
        </div>
      ) : (
        <div className="overflow-auto rounded border border-slate-700" data-testid="health-table">
          <table className="w-full text-left text-sm text-slate-200">
            <thead className="border-b border-slate-700 bg-slate-800/60 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-3 py-2">Workflow</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Runs</th>
                <th className="px-3 py-2">Success</th>
                <th className="px-3 py-2">Error</th>
                <th className="px-3 py-2">Avg Dur</th>
                <th className="px-3 py-2">Last Run</th>
              </tr>
            </thead>
            <tbody>
              {workflows.map((wf) => (
                <tr key={wf.flow_id} className="border-b border-slate-800" data-testid="health-row">
                  <td className="px-3 py-2 font-mono text-xs text-slate-300">{wf.flow_id}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[wf.health_status] ?? STATUS_STYLES.healthy}`}
                      data-testid="health-status-badge"
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[wf.health_status] ?? 'bg-slate-400'}`} />
                      {wf.health_status}
                    </span>
                  </td>
                  <td className="px-3 py-2">{wf.run_count}</td>
                  <td className="px-3 py-2 text-emerald-400">{(wf.success_rate * 100).toFixed(0)}%</td>
                  <td className={`px-3 py-2 ${wf.error_rate > 0.1 ? 'text-red-400' : 'text-slate-400'}`}>
                    {(wf.error_rate * 100).toFixed(0)}%
                  </td>
                  <td className="px-3 py-2 text-slate-400">{formatDuration(wf.avg_duration_seconds)}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {wf.last_run_at ? formatDate(wf.last_run_at) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Alert Rules Panel
// ---------------------------------------------------------------------------

const METRICS = ['error_rate', 'avg_duration_seconds', 'run_count'] as const;
const OPERATORS = ['>', '<', '>=', '<='] as const;
const ACTION_TYPES = ['log', 'webhook'] as const;

const AlertRulesPanel: React.FC = () => {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create form
  const [metric, setMetric] = useState<string>('error_rate');
  const [operator, setOperator] = useState<string>('>');
  const [threshold, setThreshold] = useState('0.3');
  const [actionType, setActionType] = useState<string>('log');
  const [creating, setCreating] = useState(false);

  // Confirm-delete
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const fetchRules = useCallback(async () => {
    try {
      const resp = await fetch(`${getBaseUrl()}/monitoring/alerts`, { headers: authHeaders() });
      if (!resp.ok) {
        setError(`API returned ${resp.status}`);
        return;
      }
      const data: { rules: AlertRule[] } = await resp.json();
      setRules(data.rules ?? []);
    } catch {
      setError('Network error loading alert rules');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRules();
  }, [fetchRules]);

  const handleCreate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const parsed = parseFloat(threshold);
      if (isNaN(parsed)) return;
      setCreating(true);
      setError(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/monitoring/alerts`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ metric, operator, threshold: parsed, action_type: actionType }),
        });
        if (!resp.ok) {
          setError('Failed to create alert rule');
          return;
        }
        await fetchRules();
        setThreshold('0.3');
      } catch {
        setError('Network error creating alert rule');
      } finally {
        setCreating(false);
      }
    },
    [metric, operator, threshold, actionType, fetchRules],
  );

  const handleToggle = useCallback(async (rule: AlertRule) => {
    try {
      await fetch(`${getBaseUrl()}/monitoring/alerts/${rule.id}`, {
        method: 'PUT',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !rule.enabled }),
      });
      setRules((prev) => prev.map((r) => r.id === rule.id ? { ...r, enabled: !r.enabled } : r));
    } catch {
      setError('Network error updating alert rule');
    }
  }, []);

  const handleDelete = useCallback(async (ruleId: string) => {
    try {
      await fetch(`${getBaseUrl()}/monitoring/alerts/${ruleId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
      setConfirmDeleteId(null);
    } catch {
      setError('Network error deleting alert rule');
    }
  }, []);

  return (
    <section data-testid="alerts-panel">
      <h2 className="mb-4 text-lg font-semibold text-slate-200">Alert Rules</h2>

      {error && (
        <div className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300" data-testid="alerts-error">
          {error}
        </div>
      )}

      {/* Create form */}
      <form onSubmit={handleCreate} className="mb-6 rounded border border-slate-700 bg-slate-800/40 p-4" data-testid="create-rule-form">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">New Alert Rule</p>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="mb-1 block text-xs text-slate-400">Metric</label>
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:outline-none"
              data-testid="rule-metric-select"
            >
              {METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Operator</label>
            <select
              value={operator}
              onChange={(e) => setOperator(e.target.value)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:outline-none"
              data-testid="rule-operator-select"
            >
              {OPERATORS.map((op) => <option key={op} value={op}>{op}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Threshold</label>
            <input
              type="number"
              step="any"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              className="w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-blue-500 focus:outline-none"
              data-testid="rule-threshold-input"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Action</label>
            <select
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:outline-none"
              data-testid="rule-action-select"
            >
              {ACTION_TYPES.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <button
            type="submit"
            disabled={creating}
            className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            data-testid="create-rule-btn"
          >
            {creating ? 'Creating…' : 'Add Rule'}
          </button>
        </div>
      </form>

      {/* Rules list */}
      {loading ? (
        <div className="py-6 text-center text-slate-400" data-testid="alerts-loading">Loading…</div>
      ) : rules.length === 0 ? (
        <div className="py-6 text-center text-slate-500" data-testid="alerts-empty">
          No alert rules yet. Create one above.
        </div>
      ) : (
        <div className="overflow-auto rounded border border-slate-700" data-testid="alerts-table">
          <table className="w-full text-left text-sm text-slate-200">
            <thead className="border-b border-slate-700 bg-slate-800/60 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-3 py-2">Metric</th>
                <th className="px-3 py-2">Condition</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">Last Triggered</th>
                <th className="px-3 py-2">Enabled</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id} className="border-b border-slate-800" data-testid="alert-row">
                  <td className="px-3 py-2 font-mono text-xs">{rule.metric}</td>
                  <td className="px-3 py-2 text-xs">
                    {rule.operator} {rule.threshold}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-400">{rule.action_type}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {rule.last_triggered_at ? formatDate(rule.last_triggered_at) : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      onClick={() => handleToggle(rule)}
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        rule.enabled
                          ? 'bg-emerald-900/40 text-emerald-300'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                      data-testid="toggle-rule-btn"
                    >
                      {rule.enabled ? 'On' : 'Off'}
                    </button>
                  </td>
                  <td className="px-3 py-2">
                    {confirmDeleteId === rule.id ? (
                      <span className="flex items-center gap-1">
                        <button
                          onClick={() => handleDelete(rule.id)}
                          className="rounded bg-red-700 px-2 py-0.5 text-xs text-white hover:bg-red-600"
                          data-testid="confirm-delete-rule-btn"
                        >
                          Yes
                        </button>
                        <button
                          onClick={() => setConfirmDeleteId(null)}
                          className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300"
                          data-testid="cancel-delete-rule-btn"
                        >
                          No
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setConfirmDeleteId(rule.id)}
                        className="rounded bg-red-800/40 px-2 py-0.5 text-xs text-red-400 hover:bg-red-700/60"
                        data-testid="delete-rule-btn"
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const MonitoringPage: React.FC = () => {
  return (
    <MainLayout title="Monitoring">
      <h1 className="mb-2 text-2xl font-bold text-slate-100" data-testid="page-title">
        Workflow Monitoring
      </h1>
      <p className="mb-8 text-sm text-slate-400">
        Real-time health status for all workflows and threshold-based alert rule management.
      </p>

      <div className="space-y-10">
        <HealthPanel />
        <AlertRulesPanel />
      </div>
    </MainLayout>
  );
};

export default MonitoringPage;
