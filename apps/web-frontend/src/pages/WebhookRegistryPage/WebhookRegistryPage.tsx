/**
 * WebhookRegistryPage — Outgoing webhook registration & management (N-102).
 *
 * Covers:
 *   POST   /webhooks          → register a new outgoing webhook
 *   GET    /webhooks          → list all registered webhooks
 *   DELETE /webhooks/{id}     → delete / unregister a webhook
 *
 * Route: /webhook-registry (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WebhookHook {
  id: string;
  url: string;
  events: string[];
  created_at?: string | number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const WEBHOOK_EVENTS = [
  'template_started',
  'template_completed',
  'template_failed',
  'step_completed',
  'step_failed',
  'connector.status_changed',
  'request.failed',
  'key.rotated',
  'key.expiring_soon',
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const WebhookRegistryPage: React.FC = () => {
  // List state
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [hooks, setHooks] = useState<WebhookHook[]>([]);

  // Create form
  const [createUrl, setCreateUrl] = useState('');
  const [createEvents, setCreateEvents] = useState<string[]>([]);
  const [createSecret, setCreateSecret] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<WebhookHook | null>(null);

  // Delete
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Load
  // ---------------------------------------------------------------------------

  const loadHooks = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/webhooks`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setListError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      const data = await resp.json();
      setHooks(
        Array.isArray(data) ? data : Array.isArray(data.webhooks) ? data.webhooks : [],
      );
    } catch {
      setListError('Network error loading webhooks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHooks();
  }, [loadHooks]);

  // ---------------------------------------------------------------------------
  // Create
  // ---------------------------------------------------------------------------

  const toggleEvent = useCallback((event: string) => {
    setCreateEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event],
    );
  }, []);

  const handleCreate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!createUrl.trim() || createEvents.length === 0) return;
      setCreating(true);
      setCreateError(null);
      setCreateSuccess(null);
      try {
        const body: Record<string, unknown> = {
          url: createUrl.trim(),
          events: createEvents,
        };
        if (createSecret.trim()) body.secret = createSecret.trim();

        const resp = await fetch(`${getBaseUrl()}/webhooks`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setCreateError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const created: WebhookHook = await resp.json();
        setCreateSuccess(created);
        setHooks((prev) => [created, ...prev]);
        setCreateUrl('');
        setCreateEvents([]);
        setCreateSecret('');
      } catch {
        setCreateError('Network error creating webhook');
      } finally {
        setCreating(false);
      }
    },
    [createUrl, createEvents, createSecret],
  );

  // ---------------------------------------------------------------------------
  // Delete
  // ---------------------------------------------------------------------------

  const handleDelete = useCallback(
    async (hookId: string) => {
      setDeletingId(hookId);
      setDeleteError(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/webhooks/${encodeURIComponent(hookId)}`,
          { method: 'DELETE', headers: authHeaders() },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setDeleteError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setHooks((prev) => prev.filter((h) => h.id !== hookId));
      } catch {
        setDeleteError('Network error deleting webhook');
      } finally {
        setDeletingId(null);
      }
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Webhook Registry">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Outgoing Webhook Registry
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Register delivery URLs for workflow lifecycle and operational events.
          </p>
        </div>
        <button
          onClick={loadHooks}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {/* Create form */}
      <section
        className="mb-6 rounded border border-slate-700 bg-slate-800/30 p-4"
        data-testid="create-section"
      >
        <h2 className="mb-3 text-sm font-semibold text-slate-300">Register Webhook</h2>
        <form onSubmit={handleCreate} className="space-y-4" data-testid="create-form">
          <div className="flex flex-wrap gap-3">
            <input
              type="url"
              value={createUrl}
              onChange={(e) => setCreateUrl(e.target.value)}
              placeholder="https://example.com/webhook"
              className="flex-1 min-w-48 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="create-url-input"
            />
            <input
              type="password"
              value={createSecret}
              onChange={(e) => setCreateSecret(e.target.value)}
              placeholder="Signing secret (optional)"
              className="w-48 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="create-secret-input"
            />
          </div>

          <div data-testid="events-checkboxes">
            <p className="mb-2 text-xs text-slate-500">Events to subscribe to:</p>
            <div className="flex flex-wrap gap-2">
              {WEBHOOK_EVENTS.map((event) => (
                <label
                  key={event}
                  className="flex cursor-pointer items-center gap-1.5 rounded border border-slate-700 bg-slate-900/60 px-2 py-1 text-xs text-slate-300"
                >
                  <input
                    type="checkbox"
                    checked={createEvents.includes(event)}
                    onChange={() => toggleEvent(event)}
                    data-testid={`event-checkbox-${event}`}
                  />
                  {event}
                </label>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={creating || !createUrl.trim() || createEvents.length === 0}
            className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
            data-testid="create-btn"
          >
            {creating ? 'Registering…' : 'Register Webhook'}
          </button>
        </form>
        {createError && (
          <p className="mt-2 text-sm text-red-400" data-testid="create-error">
            {createError}
          </p>
        )}
        {createSuccess && (
          <div
            className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
            data-testid="create-success"
          >
            <p className="font-semibold text-emerald-400">Webhook registered!</p>
            <p className="mt-1 text-slate-300">
              ID:{' '}
              <span className="font-mono" data-testid="new-hook-id">
                {createSuccess.id}
              </span>
            </p>
          </div>
        )}
      </section>

      {/* Error states */}
      {listError && (
        <p className="mb-4 text-sm text-red-400" data-testid="list-error">
          {listError}
        </p>
      )}
      {deleteError && (
        <p className="mb-4 text-sm text-red-400" data-testid="delete-error">
          {deleteError}
        </p>
      )}

      {/* Hook list */}
      {loading && hooks.length === 0 && (
        <p className="text-xs text-slate-500" data-testid="list-loading">
          Loading…
        </p>
      )}
      {!loading && hooks.length === 0 && !listError && (
        <p className="text-xs text-slate-500" data-testid="no-hooks">
          No webhooks registered.
        </p>
      )}
      {hooks.length > 0 && (
        <div className="overflow-x-auto" data-testid="hooks-table">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-500">
                <th className="pb-2 pr-4 font-medium">ID</th>
                <th className="pb-2 pr-4 font-medium">URL</th>
                <th className="pb-2 pr-4 font-medium">Events</th>
                <th className="pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {hooks.map((h) => (
                <tr
                  key={h.id}
                  className="border-b border-slate-700/40"
                  data-testid="hook-row"
                >
                  <td className="py-2 pr-4 font-mono text-slate-500">{h.id}</td>
                  <td className="py-2 pr-4 text-slate-300 break-all">{h.url}</td>
                  <td className="py-2 pr-4 text-slate-400">
                    {Array.isArray(h.events) ? h.events.join(', ') : '—'}
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => handleDelete(h.id)}
                      disabled={deletingId === h.id}
                      className="rounded bg-red-900/60 px-2 py-0.5 text-xs text-red-300 hover:bg-red-900 disabled:opacity-50"
                      data-testid="delete-btn"
                    >
                      {deletingId === h.id ? 'Deleting…' : 'Delete'}
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

export default WebhookRegistryPage;
