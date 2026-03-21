/**
 * WorkflowNotificationsPage — Workflow Notification Config UI (N-78).
 *
 * Wraps the N-27 backend API:
 *   GET /api/v1/workflows/{id}/notifications → { flow_id, config: { on_complete, on_failure } }
 *   PUT /api/v1/workflows/{id}/notifications ← same shape (body = config)
 *
 * Supported handler types: email, slack, webhook
 *
 * Route: /workflow-notifications (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type HandlerType = 'email' | 'slack' | 'webhook';

interface Handler {
  type: HandlerType;
  to?: string;           // email
  webhook_url?: string;  // slack / webhook
  subject?: string;      // email
  message?: string;      // email / slack
}

interface NotifConfig {
  on_complete: Handler[];
  on_failure: Handler[];
}

interface NotifResult {
  flow_id: string;
  config: NotifConfig;
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

function emptyHandler(): Handler {
  return { type: 'email', to: '', subject: '', message: '' };
}

// ---------------------------------------------------------------------------
// HandlerRow
// ---------------------------------------------------------------------------

interface HandlerRowProps {
  handler: Handler;
  onChange: (h: Handler) => void;
  onRemove: () => void;
  testId: string;
}

const HandlerRow: React.FC<HandlerRowProps> = ({ handler, onChange, onRemove, testId }) => (
  <div className="mb-2 rounded border border-slate-700 bg-slate-900 p-3" data-testid={testId}>
    <div className="mb-2 flex items-center gap-2">
      <select
        value={handler.type}
        onChange={(e) => onChange({ type: e.target.value as HandlerType })}
        className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:outline-none"
        data-testid="handler-type-select"
      >
        <option value="email">Email</option>
        <option value="slack">Slack</option>
        <option value="webhook">Webhook</option>
      </select>
      <button
        onClick={onRemove}
        className="ml-auto text-xs text-red-400 hover:text-red-300"
        data-testid="remove-handler-btn"
      >
        Remove
      </button>
    </div>

    {handler.type === 'email' && (
      <>
        <input
          type="text"
          value={handler.to ?? ''}
          onChange={(e) => onChange({ ...handler, to: e.target.value })}
          placeholder="Recipient email"
          className="mb-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
          data-testid="handler-to-input"
        />
        <input
          type="text"
          value={handler.subject ?? ''}
          onChange={(e) => onChange({ ...handler, subject: e.target.value })}
          placeholder="Subject"
          className="mb-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
          data-testid="handler-subject-input"
        />
      </>
    )}

    {(handler.type === 'slack' || handler.type === 'webhook') && (
      <input
        type="text"
        value={handler.webhook_url ?? ''}
        onChange={(e) => onChange({ ...handler, webhook_url: e.target.value })}
        placeholder={handler.type === 'slack' ? 'Slack webhook URL' : 'Webhook URL'}
        className="mb-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
        data-testid="handler-webhook-url-input"
      />
    )}

    {(handler.type === 'email' || handler.type === 'slack') && (
      <input
        type="text"
        value={handler.message ?? ''}
        onChange={(e) => onChange({ ...handler, message: e.target.value })}
        placeholder="Message (optional)"
        className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
        data-testid="handler-message-input"
      />
    )}
  </div>
);

// ---------------------------------------------------------------------------
// EventSection
// ---------------------------------------------------------------------------

interface EventSectionProps {
  label: string;
  handlers: Handler[];
  onAdd: () => void;
  onUpdate: (i: number, h: Handler) => void;
  onRemove: (i: number) => void;
  sectionTestId: string;
}

const EventSection: React.FC<EventSectionProps> = ({
  label, handlers, onAdd, onUpdate, onRemove, sectionTestId,
}) => (
  <section
    className="rounded border border-slate-700 bg-slate-800/40 p-4"
    data-testid={sectionTestId}
  >
    <div className="mb-3 flex items-center justify-between">
      <p className="text-sm font-semibold text-slate-300">{label}</p>
      <button
        onClick={onAdd}
        className="text-xs text-blue-400 hover:text-blue-300"
        data-testid="add-handler-btn"
      >
        + Add handler
      </button>
    </div>
    {handlers.length === 0 && (
      <p className="text-xs text-slate-500" data-testid="no-handlers">
        No handlers configured.
      </p>
    )}
    {handlers.map((h, i) => (
      <HandlerRow
        key={i}
        handler={h}
        onChange={(updated) => onUpdate(i, updated)}
        onRemove={() => onRemove(i)}
        testId="handler-row"
      />
    ))}
  </section>
);

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const WorkflowNotificationsPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);

  const [config, setConfig] = useState<NotifConfig>({ on_complete: [], on_failure: [] });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const loadConfig = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    setSuccess(false);
    try {
      const resp = await fetch(`${getBaseUrl()}/workflows/${id}/notifications`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to load notifications (${resp.status})`);
        return;
      }
      const data: NotifResult = await resp.json();
      setConfig(data.config ?? { on_complete: [], on_failure: [] });
    } catch {
      setError('Network error loading notifications');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleLoad = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const id = flowId.trim();
      if (!id) return;
      setActiveFlowId(id);
      loadConfig(id);
    },
    [flowId, loadConfig],
  );

  const handleSave = useCallback(async () => {
    if (!activeFlowId) return;
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const resp = await fetch(`${getBaseUrl()}/workflows/${activeFlowId}/notifications`, {
        method: 'PUT',
        headers: jsonHeaders(),
        body: JSON.stringify(config),
      });
      if (!resp.ok) {
        setError(`Failed to save notifications (${resp.status})`);
        return;
      }
      const data: NotifResult = await resp.json();
      setConfig(data.config ?? { on_complete: [], on_failure: [] });
      setSuccess(true);
    } catch {
      setError('Network error saving notifications');
    } finally {
      setSaving(false);
    }
  }, [activeFlowId, config]);

  const updateHandlers = (
    event: 'on_complete' | 'on_failure',
    updater: (prev: Handler[]) => Handler[],
  ) => setConfig((c) => ({ ...c, [event]: updater(c[event]) }));

  return (
    <MainLayout title="Workflow Notifications">
      <h1 className="mb-2 text-2xl font-bold text-slate-100" data-testid="page-title">
        Workflow Notifications
      </h1>
      <p className="mb-8 text-sm text-slate-400">
        Configure email, Slack, or webhook notifications that fire when a workflow completes or
        fails.
      </p>

      {/* Flow selector */}
      <form onSubmit={handleLoad} className="mb-6 flex gap-3" data-testid="flow-selector-form">
        <input
          type="text"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          placeholder="Workflow ID (e.g. flow-abc123)"
          className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          data-testid="flow-id-input"
        />
        <button
          type="submit"
          disabled={!flowId.trim() || loading}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          data-testid="load-btn"
        >
          Load
        </button>
      </form>

      {error && (
        <div
          className="mb-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
          data-testid="notif-error"
        >
          {error}
        </div>
      )}
      {success && (
        <p className="mb-4 text-sm text-emerald-400" data-testid="notif-success">
          Notification config saved.
        </p>
      )}

      {!activeFlowId && (
        <p className="text-sm text-slate-500" data-testid="no-flow-state">
          Enter a workflow ID to configure notifications.
        </p>
      )}

      {activeFlowId && !loading && (
        <div className="space-y-4" data-testid="config-panel">
          <EventSection
            label="On Complete"
            handlers={config.on_complete}
            onAdd={() => updateHandlers('on_complete', (h) => [...h, emptyHandler()])}
            onUpdate={(i, h) =>
              updateHandlers('on_complete', (prev) => prev.map((x, idx) => (idx === i ? h : x)))
            }
            onRemove={(i) =>
              updateHandlers('on_complete', (prev) => prev.filter((_, idx) => idx !== i))
            }
            sectionTestId="on-complete-section"
          />

          <EventSection
            label="On Failure"
            handlers={config.on_failure}
            onAdd={() => updateHandlers('on_failure', (h) => [...h, emptyHandler()])}
            onUpdate={(i, h) =>
              updateHandlers('on_failure', (prev) => prev.map((x, idx) => (idx === i ? h : x)))
            }
            onRemove={(i) =>
              updateHandlers('on_failure', (prev) => prev.filter((_, idx) => idx !== i))
            }
            sectionTestId="on-failure-section"
          />

          <div className="flex gap-3 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
              data-testid="save-btn"
            >
              {saving ? 'Saving…' : 'Save Notifications'}
            </button>
          </div>
        </div>
      )}
    </MainLayout>
  );
};

export default WorkflowNotificationsPage;
