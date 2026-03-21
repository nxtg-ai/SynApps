/**
 * WorkflowVarsPage — Workflow Variables & Secrets Manager (N-74).
 *
 * Wraps the N-26 backend API:
 *   GET  /api/v1/workflows/{id}/variables  — fetch variables
 *   PUT  /api/v1/workflows/{id}/variables  — replace all variables
 *   GET  /api/v1/workflows/{id}/secrets    — fetch masked secrets
 *   PUT  /api/v1/workflows/{id}/secrets    — replace all secrets (plaintext write, masked read)
 *
 * Route: /workflow-vars (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type KVMap = Record<string, string>;

interface VarsResult {
  flow_id: string;
  variables: KVMap;
  count: number;
}

interface SecretsResult {
  flow_id: string;
  secrets: KVMap;
  count: number;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface VariablesPanelProps {
  flowId: string;
}

const VariablesPanel: React.FC<VariablesPanelProps> = ({ flowId }) => {
  const [data, setData] = useState<VarsResult | null>(null);
  const [editJson, setEditJson] = useState('');
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSuccess(false);
    try {
      const resp = await fetch(`${getBaseUrl()}/workflows/${flowId}/variables`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to load variables (${resp.status})`);
        return;
      }
      const result: VarsResult = await resp.json();
      setData(result);
      setEditJson(JSON.stringify(result.variables, null, 2));
    } catch {
      setError('Network error loading variables');
    } finally {
      setLoading(false);
    }
  }, [flowId]);

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      let parsed: KVMap;
      try {
        parsed = JSON.parse(editJson);
      } catch {
        setError('Invalid JSON — fix syntax before saving');
        setSaving(false);
        return;
      }
      const resp = await fetch(`${getBaseUrl()}/workflows/${flowId}/variables`, {
        method: 'PUT',
        headers: jsonHeaders(),
        body: JSON.stringify(parsed),
      });
      if (!resp.ok) {
        setError(`Failed to save variables (${resp.status})`);
        return;
      }
      const result: VarsResult = await resp.json();
      setData(result);
      setEditJson(JSON.stringify(result.variables, null, 2));
      setEditing(false);
      setSuccess(true);
    } catch {
      setError('Network error saving variables');
    } finally {
      setSaving(false);
    }
  }, [flowId, editJson]);

  return (
    <section
      className="rounded border border-slate-700 bg-slate-800/40 p-5"
      data-testid="variables-panel"
    >
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-300">
          Variables
          {data !== null && (
            <span className="ml-2 text-xs text-slate-500">({data.count} defined)</span>
          )}
        </p>
        {!data && (
          <button
            onClick={load}
            disabled={loading}
            className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
            data-testid="load-vars-btn"
          >
            {loading ? 'Loading…' : 'Load'}
          </button>
        )}
        {data && !editing && (
          <button
            onClick={() => { setEditing(true); setSuccess(false); }}
            className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600"
            data-testid="edit-vars-btn"
          >
            Edit
          </button>
        )}
      </div>

      {error && (
        <p className="mb-3 rounded border border-red-700 bg-red-900/30 px-3 py-1.5 text-xs text-red-300" data-testid="vars-error">
          {error}
        </p>
      )}
      {success && (
        <p className="mb-3 text-xs text-emerald-400" data-testid="vars-success">
          Variables saved.
        </p>
      )}

      {!data && !loading && (
        <p className="text-xs text-slate-500" data-testid="vars-empty-state">
          Enter a workflow ID above and click Load.
        </p>
      )}

      {data && !editing && (
        <div data-testid="vars-table">
          {Object.keys(data.variables).length === 0 ? (
            <p className="text-xs text-slate-500" data-testid="vars-no-entries">
              No variables defined.
            </p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="pb-1 pr-4 font-medium">Key</th>
                  <th className="pb-1 font-medium">Value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.variables).map(([k, v]) => (
                  <tr key={k} className="border-t border-slate-700/50" data-testid="var-row">
                    <td className="py-1 pr-4 font-mono text-slate-300">{k}</td>
                    <td className="py-1 font-mono text-slate-400">{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {editing && (
        <div data-testid="vars-editor">
          <textarea
            value={editJson}
            onChange={(e) => setEditJson(e.target.value)}
            rows={8}
            className="mb-3 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-200 focus:border-blue-500 focus:outline-none"
            data-testid="vars-json-input"
          />
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={saving}
              className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
              data-testid="save-vars-btn"
            >
              {saving ? 'Saving…' : 'Save Variables'}
            </button>
            <button
              onClick={() => { setEditing(false); setError(null); }}
              className="rounded bg-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-600"
              data-testid="cancel-vars-btn"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------

interface SecretsPanelProps {
  flowId: string;
}

const SecretsPanel: React.FC<SecretsPanelProps> = ({ flowId }) => {
  const [data, setData] = useState<SecretsResult | null>(null);
  const [editJson, setEditJson] = useState('');
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSuccess(false);
    try {
      const resp = await fetch(`${getBaseUrl()}/workflows/${flowId}/secrets`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to load secrets (${resp.status})`);
        return;
      }
      const result: SecretsResult = await resp.json();
      setData(result);
      // Editing template — show keys with empty values so user fills in plaintext
      const template = Object.fromEntries(Object.keys(result.secrets).map((k) => [k, '']));
      setEditJson(JSON.stringify(template, null, 2));
    } catch {
      setError('Network error loading secrets');
    } finally {
      setLoading(false);
    }
  }, [flowId]);

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      let parsed: KVMap;
      try {
        parsed = JSON.parse(editJson);
      } catch {
        setError('Invalid JSON — fix syntax before saving');
        setSaving(false);
        return;
      }
      const resp = await fetch(`${getBaseUrl()}/workflows/${flowId}/secrets`, {
        method: 'PUT',
        headers: jsonHeaders(),
        body: JSON.stringify(parsed),
      });
      if (!resp.ok) {
        setError(`Failed to save secrets (${resp.status})`);
        return;
      }
      const result: SecretsResult = await resp.json();
      setData(result);
      const template = Object.fromEntries(Object.keys(result.secrets).map((k) => [k, '']));
      setEditJson(JSON.stringify(template, null, 2));
      setEditing(false);
      setSuccess(true);
    } catch {
      setError('Network error saving secrets');
    } finally {
      setSaving(false);
    }
  }, [flowId, editJson]);

  return (
    <section
      className="rounded border border-slate-700 bg-slate-800/40 p-5"
      data-testid="secrets-panel"
    >
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-300">
          Secrets
          {data !== null && (
            <span className="ml-2 text-xs text-slate-500">({data.count} defined)</span>
          )}
        </p>
        {!data && (
          <button
            onClick={load}
            disabled={loading}
            className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
            data-testid="load-secrets-btn"
          >
            {loading ? 'Loading…' : 'Load'}
          </button>
        )}
        {data && !editing && (
          <button
            onClick={() => { setEditing(true); setSuccess(false); }}
            className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600"
            data-testid="edit-secrets-btn"
          >
            Set Secrets
          </button>
        )}
      </div>

      <p className="mb-3 text-xs text-slate-500" data-testid="secrets-note">
        Secret values are never displayed. Names are shown masked. To update, enter plaintext values
        in the editor — they are encrypted at rest.
      </p>

      {error && (
        <p className="mb-3 rounded border border-red-700 bg-red-900/30 px-3 py-1.5 text-xs text-red-300" data-testid="secrets-error">
          {error}
        </p>
      )}
      {success && (
        <p className="mb-3 text-xs text-emerald-400" data-testid="secrets-success">
          Secrets saved.
        </p>
      )}

      {!data && !loading && (
        <p className="text-xs text-slate-500" data-testid="secrets-empty-state">
          Enter a workflow ID above and click Load.
        </p>
      )}

      {data && !editing && (
        <div data-testid="secrets-table">
          {Object.keys(data.secrets).length === 0 ? (
            <p className="text-xs text-slate-500" data-testid="secrets-no-entries">
              No secrets defined.
            </p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="pb-1 pr-4 font-medium">Name</th>
                  <th className="pb-1 font-medium">Value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.secrets).map(([k, v]) => (
                  <tr key={k} className="border-t border-slate-700/50" data-testid="secret-row">
                    <td className="py-1 pr-4 font-mono text-slate-300">{k}</td>
                    <td className="py-1 font-mono text-slate-500">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {editing && (
        <div data-testid="secrets-editor">
          <p className="mb-2 text-xs text-yellow-400">
            Enter new plaintext values. Keys without values will be ignored.
          </p>
          <textarea
            value={editJson}
            onChange={(e) => setEditJson(e.target.value)}
            rows={6}
            className="mb-3 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-200 focus:border-blue-500 focus:outline-none"
            data-testid="secrets-json-input"
          />
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={saving}
              className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 disabled:opacity-50"
              data-testid="save-secrets-btn"
            >
              {saving ? 'Saving…' : 'Save Secrets'}
            </button>
            <button
              onClick={() => { setEditing(false); setError(null); }}
              className="rounded bg-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-600"
              data-testid="cancel-secrets-btn"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const WorkflowVarsPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const id = flowId.trim();
      if (id) setActiveFlowId(id);
    },
    [flowId],
  );

  return (
    <MainLayout title="Workflow Variables & Secrets">
      <h1 className="mb-2 text-2xl font-bold text-slate-100" data-testid="page-title">
        Workflow Variables &amp; Secrets
      </h1>
      <p className="mb-8 text-sm text-slate-400">
        Manage per-workflow variables (plain key/value pairs) and secrets (encrypted at rest, values
        never returned in plaintext).
      </p>

      {/* Flow selector */}
      <form
        onSubmit={handleSubmit}
        className="mb-6 flex gap-3"
        data-testid="flow-selector-form"
      >
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
          disabled={!flowId.trim()}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          data-testid="load-flow-btn"
        >
          Load
        </button>
      </form>

      {activeFlowId && (
        <div className="space-y-6" data-testid="panels-container">
          <VariablesPanel flowId={activeFlowId} />
          <SecretsPanel flowId={activeFlowId} />
        </div>
      )}

      {!activeFlowId && (
        <p className="text-sm text-slate-500" data-testid="no-flow-state">
          Enter a workflow ID to manage its variables and secrets.
        </p>
      )}
    </MainLayout>
  );
};

export default WorkflowVarsPage;
