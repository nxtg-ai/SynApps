/**
 * WebhookTriggersPage — Webhook Trigger CRUD UI (N-89).
 *
 * Wraps:
 *   GET    /api/v1/webhook-triggers            → list all triggers
 *   POST   /api/v1/webhook-triggers            → register new trigger
 *   DELETE /api/v1/webhook-triggers/{id}       → delete trigger
 *
 * Route: /webhook-triggers (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WebhookTrigger {
  id: string;
  flow_id: string;
  created_at?: string;
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const WebhookTriggersPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [triggers, setTriggers] = useState<WebhookTrigger[]>([]);

  // Create form
  const [flowId, setFlowId] = useState('');
  const [secret, setSecret] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<WebhookTrigger | null>(null);

  // Delete state
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadTriggers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/webhook-triggers`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to load triggers (${resp.status})`);
        return;
      }
      const data = await resp.json();
      const list: WebhookTrigger[] = Array.isArray(data)
        ? data
        : Array.isArray(data.triggers)
          ? data.triggers
          : [];
      setTriggers(list);
    } catch {
      setError('Network error loading triggers');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTriggers();
  }, [loadTriggers]);

  const handleCreate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim()) {
        setCreateError('Flow ID is required.');
        return;
      }
      setCreating(true);
      setCreateError(null);
      setCreateSuccess(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/webhook-triggers`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ flow_id: flowId.trim(), secret: secret.trim() || undefined }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setCreateError(data.detail ?? `Error ${resp.status}`);
          return;
        }
        const newTrigger: WebhookTrigger = await resp.json();
        setCreateSuccess(newTrigger);
        setTriggers((prev) => [newTrigger, ...prev]);
        setFlowId('');
        setSecret('');
      } catch {
        setCreateError('Network error creating trigger');
      } finally {
        setCreating(false);
      }
    },
    [flowId, secret],
  );

  const handleDelete = useCallback(async (triggerId: string) => {
    setDeletingId(triggerId);
    setDeleteError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/webhook-triggers/${encodeURIComponent(triggerId)}`,
        { method: 'DELETE', headers: authHeaders() },
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setDeleteError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setTriggers((prev) => prev.filter((t) => t.id !== triggerId));
    } catch {
      setDeleteError('Network error deleting trigger');
    } finally {
      setDeletingId(null);
    }
  }, []);

  return (
    <MainLayout title="Webhook Triggers">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Webhook Triggers
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Register inbound webhook triggers that launch workflows on POST.
          </p>
        </div>
        <button
          onClick={loadTriggers}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* Create form */}
      <section className="mb-8 rounded border border-slate-700 bg-slate-800/30 p-5" data-testid="create-section">
        <h2 className="mb-4 text-sm font-semibold text-slate-300">Register New Trigger</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap gap-3" data-testid="create-form">
          <input
            type="text"
            value={flowId}
            onChange={(e) => setFlowId(e.target.value)}
            placeholder="Flow ID"
            className="w-48 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
            data-testid="flow-id-input"
          />
          <input
            type="text"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Signing secret (optional)"
            className="w-56 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
            data-testid="secret-input"
          />
          <button
            type="submit"
            disabled={creating || !flowId.trim()}
            className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
            data-testid="create-btn"
          >
            {creating ? 'Registering…' : 'Register'}
          </button>
        </form>
        {createError && (
          <p className="mt-2 text-sm text-red-400" data-testid="create-error">{createError}</p>
        )}
        {createSuccess && (
          <div className="mt-3 rounded bg-emerald-900/20 p-3 text-xs text-emerald-400" data-testid="create-success">
            <span className="font-semibold">Trigger registered!</span> ID:{' '}
            <span className="font-mono" data-testid="new-trigger-id">{createSuccess.id}</span>
            <br />
            Receive URL:{' '}
            <span className="font-mono text-slate-300">
              POST /api/v1/webhook-triggers/{createSuccess.id}/receive
            </span>
          </div>
        )}
      </section>

      {/* Trigger list */}
      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="triggers-error">{error}</p>
      )}
      {deleteError && (
        <p className="mb-4 text-sm text-red-400" data-testid="delete-error">{deleteError}</p>
      )}

      {loading && triggers.length === 0 && (
        <p className="text-xs text-slate-500" data-testid="triggers-loading">Loading…</p>
      )}

      {!loading && triggers.length === 0 && !error && (
        <p className="text-xs text-slate-500" data-testid="no-triggers">
          No webhook triggers registered.
        </p>
      )}

      {triggers.length > 0 && (
        <div className="overflow-x-auto" data-testid="triggers-table">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-500">
                <th className="pb-2 pr-4 font-medium">Trigger ID</th>
                <th className="pb-2 pr-4 font-medium">Flow ID</th>
                <th className="pb-2 pr-4 font-medium">Created</th>
                <th className="pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {triggers.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-slate-700/40"
                  data-testid="trigger-row"
                >
                  <td className="py-2 pr-4 font-mono text-slate-300">{t.id}</td>
                  <td className="py-2 pr-4 font-mono text-slate-400">{t.flow_id}</td>
                  <td className="py-2 pr-4 text-slate-500">
                    {t.created_at
                      ? new Date(t.created_at).toLocaleString()
                      : '—'}
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => handleDelete(t.id)}
                      disabled={deletingId === t.id}
                      className="rounded bg-red-900/60 px-2 py-0.5 text-xs text-red-300 hover:bg-red-900 disabled:opacity-50"
                      data-testid="delete-btn"
                    >
                      {deletingId === t.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </MainLayout>
  );
};

export default WebhookTriggersPage;
