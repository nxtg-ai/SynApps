/**
 * SchedulesPage — Workflow Cron Schedule Manager (N-76).
 *
 * Wraps the scheduler management API:
 *   GET    /api/v1/schedules?flow_id=   — list schedules
 *   POST   /api/v1/schedules            — create schedule
 *   PATCH  /api/v1/schedules/{id}       — update (cron_expr / name / enabled)
 *   DELETE /api/v1/schedules/{id}       — delete
 *
 * Route: /schedules (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Schedule {
  id: string;
  flow_id: string;
  cron_expr: string;
  name: string;
  enabled: boolean;
  next_run: string | null;
  last_run: string | null;
  created_at: string;
  run_count: number;
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

function formatTs(ts: string | null): string {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const SchedulesPage: React.FC = () => {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [newFlowId, setNewFlowId] = useState('');
  const [newCron, setNewCron] = useState('');
  const [newName, setNewName] = useState('');
  const [newEnabled, setNewEnabled] = useState(true);
  const [creating, setCreating] = useState(false);

  // Edit state
  const [editId, setEditId] = useState<string | null>(null);
  const [editCron, setEditCron] = useState('');
  const [editName, setEditName] = useState('');
  const [saving, setSaving] = useState(false);

  // Delete confirm
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const loadSchedules = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/schedules`, { headers: authHeaders() });
      if (!resp.ok) {
        setError(`Failed to load schedules (${resp.status})`);
        return;
      }
      const data: Schedule[] = await resp.json();
      setSchedules(data);
    } catch {
      setError('Network error loading schedules');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSchedules();
  }, [loadSchedules]);

  const handleCreate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setCreating(true);
      setError(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/schedules`, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({
            flow_id: newFlowId.trim(),
            cron_expr: newCron.trim(),
            name: newName.trim() || undefined,
            enabled: newEnabled,
          }),
        });
        if (!resp.ok) {
          const detail = await resp.text().catch(() => '');
          setError(`Failed to create schedule (${resp.status})${detail ? ': ' + detail : ''}`);
          return;
        }
        const entry: Schedule = await resp.json();
        setSchedules((prev) => [entry, ...prev]);
        setShowCreate(false);
        setNewFlowId('');
        setNewCron('');
        setNewName('');
        setNewEnabled(true);
      } catch {
        setError('Network error creating schedule');
      } finally {
        setCreating(false);
      }
    },
    [newFlowId, newCron, newName, newEnabled],
  );

  const openEdit = useCallback((s: Schedule) => {
    setEditId(s.id);
    setEditCron(s.cron_expr);
    setEditName(s.name);
  }, []);

  const handleSaveEdit = useCallback(
    async (id: string) => {
      setSaving(true);
      setError(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/schedules/${id}`, {
          method: 'PATCH',
          headers: jsonHeaders(),
          body: JSON.stringify({ cron_expr: editCron.trim(), name: editName.trim() }),
        });
        if (!resp.ok) {
          setError(`Failed to update schedule (${resp.status})`);
          return;
        }
        const updated: Schedule = await resp.json();
        setSchedules((prev) => prev.map((s) => (s.id === id ? updated : s)));
        setEditId(null);
      } catch {
        setError('Network error updating schedule');
      } finally {
        setSaving(false);
      }
    },
    [editCron, editName],
  );

  const handleToggleEnabled = useCallback(async (s: Schedule) => {
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/schedules/${s.id}`, {
        method: 'PATCH',
        headers: jsonHeaders(),
        body: JSON.stringify({ enabled: !s.enabled }),
      });
      if (!resp.ok) {
        setError(`Failed to toggle schedule (${resp.status})`);
        return;
      }
      const updated: Schedule = await resp.json();
      setSchedules((prev) => prev.map((sc) => (sc.id === s.id ? updated : sc)));
    } catch {
      setError('Network error toggling schedule');
    }
  }, []);

  const handleDelete = useCallback(async (id: string) => {
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/schedules/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to delete schedule (${resp.status})`);
        return;
      }
      setSchedules((prev) => prev.filter((s) => s.id !== id));
      setDeleteId(null);
    } catch {
      setError('Network error deleting schedule');
    }
  }, []);

  return (
    <MainLayout title="Workflow Schedules">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Workflow Schedules
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Create and manage cron schedules that trigger workflow runs automatically.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          data-testid="new-schedule-btn"
        >
          + New Schedule
        </button>
      </div>

      {error && (
        <div
          className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
          data-testid="schedules-error"
        >
          {error}
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="mb-6 rounded border border-slate-700 bg-slate-800/40 p-5"
          data-testid="create-form"
        >
          <p className="mb-4 text-sm font-semibold text-slate-300">New Schedule</p>
          <div className="mb-3 grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-slate-400">Workflow ID *</label>
              <input
                type="text"
                value={newFlowId}
                onChange={(e) => setNewFlowId(e.target.value)}
                placeholder="flow-abc123"
                required
                className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                data-testid="new-flow-id-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">Cron Expression *</label>
              <input
                type="text"
                value={newCron}
                onChange={(e) => setNewCron(e.target.value)}
                placeholder="0 9 * * 1-5"
                required
                className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                data-testid="new-cron-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">Name (optional)</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Daily morning run"
                className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                data-testid="new-name-input"
              />
            </div>
            <div className="flex items-end gap-2">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={newEnabled}
                  onChange={(e) => setNewEnabled(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-800"
                  data-testid="new-enabled-checkbox"
                />
                Enable immediately
              </label>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={creating || !newFlowId.trim() || !newCron.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
              data-testid="create-submit-btn"
            >
              {creating ? 'Creating…' : 'Create Schedule'}
            </button>
            <button
              type="button"
              onClick={() => { setShowCreate(false); setError(null); }}
              className="rounded bg-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-600"
              data-testid="cancel-create-btn"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Schedule list */}
      {loading && (
        <p className="text-sm text-slate-500" data-testid="loading-state">
          Loading schedules…
        </p>
      )}

      {!loading && schedules.length === 0 && (
        <p className="text-sm text-slate-500" data-testid="empty-state">
          No schedules yet. Click <strong>+ New Schedule</strong> to create one.
        </p>
      )}

      {schedules.length > 0 && (
        <div className="space-y-3" data-testid="schedules-list">
          {schedules.map((s) => (
            <div
              key={s.id}
              className="rounded border border-slate-700 bg-slate-800/40 p-4"
              data-testid="schedule-row"
            >
              {editId === s.id ? (
                /* Edit mode */
                <div className="flex flex-wrap gap-3" data-testid="edit-form">
                  <input
                    type="text"
                    value={editCron}
                    onChange={(e) => setEditCron(e.target.value)}
                    className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                    data-testid="edit-cron-input"
                  />
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                    data-testid="edit-name-input"
                  />
                  <button
                    onClick={() => handleSaveEdit(s.id)}
                    disabled={saving}
                    className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
                    data-testid="save-edit-btn"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditId(null)}
                    className="rounded bg-slate-700 px-3 py-1.5 text-xs text-slate-300"
                    data-testid="cancel-edit-btn"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                /* View mode */
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-200">{s.name}</p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      Flow: <span className="font-mono text-slate-300">{s.flow_id}</span>
                      {' · '}
                      Cron: <span className="font-mono text-slate-300">{s.cron_expr}</span>
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Next run: {formatTs(s.next_run)} · Runs: {s.run_count}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${
                        s.enabled
                          ? 'border-emerald-700 bg-emerald-900/40 text-emerald-300'
                          : 'border-slate-600 bg-slate-800 text-slate-400'
                      }`}
                      data-testid="enabled-badge"
                    >
                      {s.enabled ? 'enabled' : 'disabled'}
                    </span>
                    <button
                      onClick={() => handleToggleEnabled(s)}
                      className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-600"
                      data-testid="toggle-btn"
                    >
                      {s.enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      onClick={() => openEdit(s)}
                      className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-600"
                      data-testid="edit-btn"
                    >
                      Edit
                    </button>
                    {deleteId === s.id ? (
                      <>
                        <button
                          onClick={() => handleDelete(s.id)}
                          className="rounded bg-red-700 px-2 py-0.5 text-xs text-red-100 hover:bg-red-600"
                          data-testid="confirm-delete-btn"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => setDeleteId(null)}
                          className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300"
                          data-testid="cancel-delete-btn"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setDeleteId(s.id)}
                        className="rounded bg-red-900/40 px-2 py-0.5 text-xs text-red-400 hover:bg-red-800/60"
                        data-testid="delete-btn"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </MainLayout>
  );
};

export default SchedulesPage;
