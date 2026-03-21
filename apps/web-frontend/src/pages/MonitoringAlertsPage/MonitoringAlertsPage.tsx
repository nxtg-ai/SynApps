/**
 * MonitoringAlertsPage — Alert rule CRUD + workflow health (N-109).
 *
 * Covers:
 *   POST   /monitoring/alerts              → create alert rule
 *   GET    /monitoring/alerts              → list alert rules
 *   PUT    /monitoring/alerts/{rule_id}    → update alert rule
 *   DELETE /monitoring/alerts/{rule_id}    → delete alert rule
 *   GET    /monitoring/workflows           → list workflow health summaries
 *
 * Route: /monitoring-alerts (ProtectedRoute)
 */
import React, { useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AlertRule {
  rule_id: string;
  metric: string;
  operator: string;
  threshold: number;
  action_type: string;
  workflow_id?: string;
  window_minutes?: number;
  enabled?: boolean;
}

interface WorkflowHealth {
  flow_id: string;
  success_rate?: number;
  total_runs?: number;
  avg_duration_ms?: number;
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

function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

const METRICS = ['error_rate', 'avg_duration_ms', 'total_runs', 'failure_count', 'success_rate'];
const OPERATORS = ['>', '<', '>=', '<=', '=='];
const ACTION_TYPES = ['log', 'webhook', 'email'];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const MonitoringAlertsPage: React.FC = () => {
  // Create form
  const [createMetric, setCreateMetric] = useState(METRICS[0]);
  const [createOperator, setCreateOperator] = useState(OPERATORS[0]);
  const [createThreshold, setCreateThreshold] = useState('0.1');
  const [createActionType, setCreateActionType] = useState(ACTION_TYPES[0]);
  const [createWorkflowId, setCreateWorkflowId] = useState('');
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createResult, setCreateResult] = useState<AlertRule | null>(null);

  // List
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  // Update
  const [editId, setEditId] = useState('');
  const [editThreshold, setEditThreshold] = useState('');
  const [editEnabled, setEditEnabled] = useState(true);
  const [updateLoading, setUpdateLoading] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [updateResult, setUpdateResult] = useState<AlertRule | null>(null);

  // Delete
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Workflow health
  const [health, setHealth] = useState<WorkflowHealth[]>([]);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);

  // Load on mount
  useEffect(() => {
    loadRules();
    loadHealth();
  }, []);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function loadRules() {
    setListLoading(true);
    setListError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/monitoring/alerts`, {
        headers: authHeaders(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setListError(data.detail ?? `Error ${resp.status}`); return; }
      const raw = data.rules ?? data;
      setRules(Array.isArray(raw) ? raw : []);
    } catch {
      setListError('Network error');
    } finally {
      setListLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    setCreateResult(null);
    try {
      const body: Record<string, unknown> = {
        metric: createMetric,
        operator: createOperator,
        threshold: parseFloat(createThreshold),
        action_type: createActionType,
      };
      if (createWorkflowId.trim()) body.workflow_id = createWorkflowId.trim();
      const resp = await fetch(`${getBaseUrl()}/api/v1/monitoring/alerts`, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setCreateError(data.detail ?? `Error ${resp.status}`); return; }
      setCreateResult((data.rule ?? data) as AlertRule);
      loadRules();
    } catch {
      setCreateError('Network error');
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleUpdate(e: React.FormEvent) {
    e.preventDefault();
    if (!editId.trim()) return;
    setUpdateLoading(true);
    setUpdateError(null);
    setUpdateResult(null);
    try {
      const body: Record<string, unknown> = { enabled: editEnabled };
      if (editThreshold.trim()) body.threshold = parseFloat(editThreshold);
      const resp = await fetch(`${getBaseUrl()}/api/v1/monitoring/alerts/${editId.trim()}`, {
        method: 'PUT',
        headers: jsonHeaders(),
        body: JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setUpdateError(data.detail ?? `Error ${resp.status}`); return; }
      setUpdateResult((data.rule ?? data) as AlertRule);
      loadRules();
    } catch {
      setUpdateError('Network error');
    } finally {
      setUpdateLoading(false);
    }
  }

  async function handleDelete(ruleId: string) {
    setDeleteError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/monitoring/alerts/${ruleId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!resp.ok && resp.status !== 204) {
        const data = await resp.json().catch(() => ({}));
        setDeleteError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setRules((prev) => prev.filter((r) => r.rule_id !== ruleId));
    } catch {
      setDeleteError('Network error');
    }
  }

  async function loadHealth() {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/monitoring/workflows`, {
        headers: authHeaders(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setHealthError(data.detail ?? `Error ${resp.status}`); return; }
      const raw = data.workflows ?? data;
      setHealth(Array.isArray(raw) ? raw : []);
    } catch {
      setHealthError('Network error');
    } finally {
      setHealthLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Monitoring Alerts">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Monitoring &amp; Alerts
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Configure alert rules and view workflow health summaries.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">

        {/* ---- Create Rule ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="create-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Create Alert Rule</h2>
          <form onSubmit={handleCreate} className="space-y-3" data-testid="create-form">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-xs text-slate-500">Metric</label>
                <select
                  className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1.5 text-xs text-slate-200"
                  value={createMetric}
                  onChange={(e) => setCreateMetric(e.target.value)}
                  data-testid="create-metric"
                >
                  {METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">Operator</label>
                <select
                  className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1.5 text-xs text-slate-200"
                  value={createOperator}
                  onChange={(e) => setCreateOperator(e.target.value)}
                  data-testid="create-operator"
                >
                  {OPERATORS.map((op) => <option key={op} value={op}>{op}</option>)}
                </select>
              </div>
            </div>
            <input
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Threshold (e.g. 0.1)"
              value={createThreshold}
              onChange={(e) => setCreateThreshold(e.target.value)}
              required
              data-testid="create-threshold"
            />
            <div>
              <label className="mb-1 block text-xs text-slate-500">Action Type</label>
              <select
                className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1.5 text-xs text-slate-200"
                value={createActionType}
                onChange={(e) => setCreateActionType(e.target.value)}
                data-testid="create-action-type"
              >
                {ACTION_TYPES.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <input
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Workflow ID (optional, default: *)"
              value={createWorkflowId}
              onChange={(e) => setCreateWorkflowId(e.target.value)}
              data-testid="create-workflow-id"
            />
            <button
              type="submit"
              disabled={createLoading}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="create-btn"
            >
              {createLoading ? 'Creating…' : 'Create Rule'}
            </button>
          </form>
          {createError && (
            <p className="mt-2 text-xs text-red-400" data-testid="create-error">{createError}</p>
          )}
          {createResult && (
            <div className="mt-3 rounded border border-emerald-700/40 bg-emerald-900/10 p-3 text-xs" data-testid="create-result">
              <p className="text-emerald-300">Rule created</p>
              <p className="mt-1 text-slate-400">ID: <span className="font-mono" data-testid="new-rule-id">{createResult.rule_id}</span></p>
            </div>
          )}
        </section>

        {/* ---- Update Rule ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="update-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Update Alert Rule</h2>
          <form onSubmit={handleUpdate} className="space-y-3" data-testid="update-form">
            <input
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Rule ID"
              value={editId}
              onChange={(e) => setEditId(e.target.value)}
              required
              data-testid="update-rule-id"
            />
            <input
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="New threshold (optional)"
              value={editThreshold}
              onChange={(e) => setEditThreshold(e.target.value)}
              data-testid="update-threshold"
            />
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={editEnabled}
                onChange={(e) => setEditEnabled(e.target.checked)}
                data-testid="update-enabled"
              />
              Enabled
            </label>
            <button
              type="submit"
              disabled={updateLoading}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="update-btn"
            >
              {updateLoading ? 'Updating…' : 'Update Rule'}
            </button>
          </form>
          {updateError && (
            <p className="mt-2 text-xs text-red-400" data-testid="update-error">{updateError}</p>
          )}
          {updateResult && (
            <div className="mt-3 rounded border border-emerald-700/40 bg-emerald-900/10 p-3 text-xs" data-testid="update-result">
              <p className="text-emerald-300">Rule updated</p>
              <p className="mt-1 text-slate-400">
                Threshold: <span className="font-semibold text-slate-200" data-testid="updated-threshold">{updateResult.threshold}</span>
              </p>
            </div>
          )}
        </section>

        {/* ---- Alert Rules List ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4 lg:col-span-2" data-testid="rules-section">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">Alert Rules</h2>
            <button
              onClick={loadRules}
              className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600"
              data-testid="refresh-rules-btn"
            >
              Refresh
            </button>
          </div>
          {listError && (
            <p className="mb-2 text-xs text-red-400" data-testid="list-error">{listError}</p>
          )}
          {deleteError && (
            <p className="mb-2 text-xs text-red-400" data-testid="delete-error">{deleteError}</p>
          )}
          {listLoading && (
            <p className="text-xs text-slate-500" data-testid="list-loading">Loading…</p>
          )}
          {!listLoading && rules.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="no-rules">No alert rules configured.</p>
          )}
          {rules.length > 0 && (
            <div className="overflow-x-auto" data-testid="rules-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Metric</th>
                    <th className="pb-2 pr-4 font-medium">Op</th>
                    <th className="pb-2 pr-4 font-medium">Threshold</th>
                    <th className="pb-2 pr-4 font-medium">Action</th>
                    <th className="pb-2 pr-4 font-medium">Enabled</th>
                    <th className="pb-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r) => (
                    <tr key={r.rule_id} className="border-b border-slate-700/40" data-testid="rule-row">
                      <td className="py-2 pr-4 text-slate-300" data-testid="rule-metric">{r.metric}</td>
                      <td className="py-2 pr-4 text-slate-400">{r.operator}</td>
                      <td className="py-2 pr-4 text-slate-300">{r.threshold}</td>
                      <td className="py-2 pr-4 text-slate-400">{r.action_type}</td>
                      <td className="py-2 pr-4">
                        <span className={r.enabled !== false ? 'text-emerald-400' : 'text-red-400'}>
                          {r.enabled !== false ? 'yes' : 'no'}
                        </span>
                      </td>
                      <td className="py-2">
                        <button
                          onClick={() => handleDelete(r.rule_id)}
                          className="rounded bg-red-900/30 px-2 py-0.5 text-xs text-red-400 hover:bg-red-900/50"
                          data-testid="delete-rule-btn"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ---- Workflow Health ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4 lg:col-span-2" data-testid="health-section">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">Workflow Health</h2>
            <button
              onClick={loadHealth}
              className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600"
              data-testid="refresh-health-btn"
            >
              Refresh
            </button>
          </div>
          {healthError && (
            <p className="mb-2 text-xs text-red-400" data-testid="health-error">{healthError}</p>
          )}
          {healthLoading && (
            <p className="text-xs text-slate-500" data-testid="health-loading">Loading…</p>
          )}
          {!healthLoading && health.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="no-health">No workflow health data.</p>
          )}
          {health.length > 0 && (
            <div className="overflow-x-auto" data-testid="health-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Flow ID</th>
                    <th className="pb-2 pr-4 font-medium">Success Rate</th>
                    <th className="pb-2 pr-4 font-medium">Total Runs</th>
                    <th className="pb-2 font-medium">Avg Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {health.map((h) => (
                    <tr key={h.flow_id} className="border-b border-slate-700/40" data-testid="health-row">
                      <td className="py-2 pr-4 font-mono text-slate-400" data-testid="health-flow-id">
                        {h.flow_id}
                      </td>
                      <td className="py-2 pr-4 text-slate-300">
                        {h.success_rate !== undefined
                          ? `${(h.success_rate * 100).toFixed(1)}%`
                          : '—'}
                      </td>
                      <td className="py-2 pr-4 text-slate-300">{h.total_runs ?? '—'}</td>
                      <td className="py-2 text-slate-300">
                        {h.avg_duration_ms !== undefined
                          ? `${h.avg_duration_ms.toFixed(0)}ms`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default MonitoringAlertsPage;
