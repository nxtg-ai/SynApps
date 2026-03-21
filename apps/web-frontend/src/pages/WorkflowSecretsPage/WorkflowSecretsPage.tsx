/**
 * WorkflowSecretsPage — Workflow secrets + diff + versions (N-110).
 *
 * Covers:
 *   GET  /workflows/{flow_id}/secrets         → masked secrets list
 *   PUT  /workflows/{flow_id}/secrets         → set/replace secrets
 *   POST /workflows/{flow_id}/diff            → compute structural diff
 *   POST /workflows/{flow_id}/versions        → save named snapshot
 *   GET  /workflows/{flow_id}/version-history → list version summaries
 *   GET  /workflows/{flow_id}/versions/{vid}  → get single version
 *
 * Route: /workflow-secrets (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MaskedSecret {
  name: string;
  value: string; // always "***"
}

interface VersionRecord {
  version_id: string;
  flow_id?: string;
  label?: string;
  saved_at?: number | string;
  snapshot?: unknown;
}

interface DiffResult {
  nodes_added?: string[];
  nodes_removed?: string[];
  edges_added?: number;
  edges_removed?: number;
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type TabId = 'secrets' | 'diff' | 'versions';

const WorkflowSecretsPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [activeTab, setActiveTab] = useState<TabId>('secrets');

  // Secrets
  const [secrets, setSecrets] = useState<MaskedSecret[]>([]);
  const [secretsLoading, setSecretsLoading] = useState(false);
  const [secretsError, setSecretsError] = useState<string | null>(null);
  const [putJson, setPutJson] = useState('{"MY_KEY":"my_value"}');
  const [putLoading, setPutLoading] = useState(false);
  const [putError, setPutError] = useState<string | null>(null);
  const [putResult, setPutResult] = useState<{ count: number } | null>(null);

  // Diff
  const [diffV1, setDiffV1] = useState('{}');
  const [diffV2, setDiffV2] = useState('{}');
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null);

  // Versions
  const [versions, setVersions] = useState<VersionRecord[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [saveLabel, setSaveLabel] = useState('');
  const [saveSnapshot, setSaveSnapshot] = useState('{}');
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveResult, setSaveResult] = useState<VersionRecord | null>(null);
  const [viewVersionId, setViewVersionId] = useState('');
  const [viewVersionResult, setViewVersionResult] = useState<VersionRecord | null>(null);
  const [viewVersionError, setViewVersionError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Handlers — Secrets
  // ---------------------------------------------------------------------------

  async function loadSecrets() {
    if (!flowId.trim()) return;
    setSecretsLoading(true);
    setSecretsError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${flowId.trim()}/secrets`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setSecretsError(data.detail ?? `Error ${resp.status}`); return; }
      const raw = data.secrets ?? data;
      setSecrets(Array.isArray(raw) ? raw : Object.entries(raw).map(([name, value]) => ({ name, value: String(value) })));
    } catch {
      setSecretsError('Network error');
    } finally {
      setSecretsLoading(false);
    }
  }

  async function handlePutSecrets(e: React.FormEvent) {
    e.preventDefault();
    if (!flowId.trim()) return;
    setPutLoading(true);
    setPutError(null);
    setPutResult(null);
    try {
      let body: unknown;
      try { body = JSON.parse(putJson); } catch { setPutError('Invalid JSON'); setPutLoading(false); return; }
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${flowId.trim()}/secrets`,
        { method: 'PUT', headers: jsonHeaders(), body: JSON.stringify(body) },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setPutError(data.detail ?? `Error ${resp.status}`); return; }
      setPutResult({ count: data.count ?? 0 });
      loadSecrets();
    } catch {
      setPutError('Network error');
    } finally {
      setPutLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Handlers — Diff
  // ---------------------------------------------------------------------------

  async function handleDiff(e: React.FormEvent) {
    e.preventDefault();
    if (!flowId.trim()) return;
    setDiffLoading(true);
    setDiffError(null);
    setDiffResult(null);
    try {
      let v1: unknown;
      let v2: unknown;
      try { v1 = JSON.parse(diffV1); } catch { setDiffError('Invalid JSON in V1'); setDiffLoading(false); return; }
      try { v2 = JSON.parse(diffV2); } catch { setDiffError('Invalid JSON in V2'); setDiffLoading(false); return; }
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${flowId.trim()}/diff`,
        { method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ v1, v2 }) },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setDiffError(data.detail ?? `Error ${resp.status}`); return; }
      setDiffResult(data as DiffResult);
    } catch {
      setDiffError('Network error');
    } finally {
      setDiffLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Handlers — Versions
  // ---------------------------------------------------------------------------

  async function loadVersionHistory() {
    if (!flowId.trim()) return;
    setVersionsLoading(true);
    setVersionsError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${flowId.trim()}/version-history`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setVersionsError(data.detail ?? `Error ${resp.status}`); return; }
      const raw = data.versions ?? data;
      setVersions(Array.isArray(raw) ? raw : []);
    } catch {
      setVersionsError('Network error');
    } finally {
      setVersionsLoading(false);
    }
  }

  async function handleSaveVersion(e: React.FormEvent) {
    e.preventDefault();
    if (!flowId.trim()) return;
    setSaveLoading(true);
    setSaveError(null);
    setSaveResult(null);
    try {
      let snapshot: unknown;
      try { snapshot = JSON.parse(saveSnapshot); } catch { setSaveError('Invalid JSON in snapshot'); setSaveLoading(false); return; }
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${flowId.trim()}/versions`,
        {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ snapshot, label: saveLabel || undefined }),
        },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setSaveError(data.detail ?? `Error ${resp.status}`); return; }
      setSaveResult(data as VersionRecord);
      loadVersionHistory();
    } catch {
      setSaveError('Network error');
    } finally {
      setSaveLoading(false);
    }
  }

  async function handleViewVersion() {
    if (!flowId.trim() || !viewVersionId.trim()) return;
    setViewVersionError(null);
    setViewVersionResult(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${flowId.trim()}/versions/${viewVersionId.trim()}`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setViewVersionError(data.detail ?? `Error ${resp.status}`); return; }
      setViewVersionResult(data as VersionRecord);
    } catch {
      setViewVersionError('Network error');
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Workflow Secrets">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Workflow Secrets &amp; Versions
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Manage encrypted secrets, compute diffs, and save workflow snapshots.
        </p>
      </div>

      {/* Flow ID */}
      <div className="mb-6 flex gap-3" data-testid="flow-id-section">
        <input
          className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
          placeholder="Flow ID"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          data-testid="flow-id-input"
        />
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-slate-700" data-testid="tabs">
        {(['secrets', 'diff', 'versions'] as TabId[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm capitalize ${activeTab === tab ? 'border-b-2 border-indigo-500 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
            data-testid={`tab-${tab}`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* ---- Secrets Tab ---- */}
      {activeTab === 'secrets' && (
        <div data-testid="tab-panel-secrets">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Get secrets */}
            <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="get-secrets-section">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-300">Secrets (masked)</h2>
                <button
                  onClick={loadSecrets}
                  disabled={!flowId.trim()}
                  className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                  data-testid="load-secrets-btn"
                >
                  Load
                </button>
              </div>
              {secretsError && (
                <p className="mb-2 text-xs text-red-400" data-testid="secrets-error">{secretsError}</p>
              )}
              {secretsLoading && (
                <p className="text-xs text-slate-500" data-testid="secrets-loading">Loading…</p>
              )}
              {!secretsLoading && secrets.length === 0 && (
                <p className="text-xs text-slate-500" data-testid="no-secrets">No secrets set.</p>
              )}
              {secrets.length > 0 && (
                <ul className="space-y-1" data-testid="secrets-list">
                  {secrets.map((s) => (
                    <li key={s.name} className="flex items-center gap-2 text-xs" data-testid="secret-item">
                      <span className="font-mono text-slate-300" data-testid="secret-name">{s.name}</span>
                      <span className="text-slate-500">{s.value}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Set secrets */}
            <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="put-secrets-section">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">Set Secrets</h2>
              <form onSubmit={handlePutSecrets} className="space-y-3" data-testid="put-form">
                <textarea
                  className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 font-mono text-xs text-slate-200"
                  rows={5}
                  value={putJson}
                  onChange={(e) => setPutJson(e.target.value)}
                  data-testid="put-secrets-json"
                />
                <button
                  type="submit"
                  disabled={putLoading || !flowId.trim()}
                  className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
                  data-testid="put-secrets-btn"
                >
                  {putLoading ? 'Saving…' : 'Set Secrets'}
                </button>
              </form>
              {putError && (
                <p className="mt-2 text-xs text-red-400" data-testid="put-error">{putError}</p>
              )}
              {putResult && (
                <div className="mt-3 rounded border border-emerald-700/40 bg-emerald-900/10 p-3 text-xs" data-testid="put-result">
                  <p className="text-emerald-300">Saved <span data-testid="secrets-count">{putResult.count}</span> secrets</p>
                </div>
              )}
            </section>
          </div>
        </div>
      )}

      {/* ---- Diff Tab ---- */}
      {activeTab === 'diff' && (
        <div data-testid="tab-panel-diff">
          <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="diff-section">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">Compute Diff</h2>
            <form onSubmit={handleDiff} className="space-y-3" data-testid="diff-form">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs text-slate-500">Workflow V1 (JSON)</label>
                  <textarea
                    className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 font-mono text-xs text-slate-200"
                    rows={6}
                    value={diffV1}
                    onChange={(e) => setDiffV1(e.target.value)}
                    data-testid="diff-v1-input"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">Workflow V2 (JSON)</label>
                  <textarea
                    className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 font-mono text-xs text-slate-200"
                    rows={6}
                    value={diffV2}
                    onChange={(e) => setDiffV2(e.target.value)}
                    data-testid="diff-v2-input"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={diffLoading || !flowId.trim()}
                className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
                data-testid="diff-btn"
              >
                {diffLoading ? 'Computing…' : 'Compute Diff'}
              </button>
            </form>
            {diffError && (
              <p className="mt-2 text-xs text-red-400" data-testid="diff-error">{diffError}</p>
            )}
            {diffResult && (
              <div className="mt-3" data-testid="diff-result">
                <pre className="overflow-x-auto rounded border border-slate-700 bg-slate-900 p-3 text-xs text-slate-300" data-testid="diff-json">
                  {JSON.stringify(diffResult, null, 2)}
                </pre>
              </div>
            )}
          </section>
        </div>
      )}

      {/* ---- Versions Tab ---- */}
      {activeTab === 'versions' && (
        <div data-testid="tab-panel-versions">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Save version */}
            <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="save-version-section">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">Save Snapshot</h2>
              <form onSubmit={handleSaveVersion} className="space-y-3" data-testid="save-form">
                <input
                  className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
                  placeholder="Label (optional)"
                  value={saveLabel}
                  onChange={(e) => setSaveLabel(e.target.value)}
                  data-testid="save-label-input"
                />
                <textarea
                  className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 font-mono text-xs text-slate-200"
                  rows={4}
                  placeholder="Snapshot JSON"
                  value={saveSnapshot}
                  onChange={(e) => setSaveSnapshot(e.target.value)}
                  data-testid="save-snapshot-input"
                />
                <button
                  type="submit"
                  disabled={saveLoading || !flowId.trim()}
                  className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
                  data-testid="save-version-btn"
                >
                  {saveLoading ? 'Saving…' : 'Save Version'}
                </button>
              </form>
              {saveError && (
                <p className="mt-2 text-xs text-red-400" data-testid="save-error">{saveError}</p>
              )}
              {saveResult && (
                <div className="mt-3 rounded border border-emerald-700/40 bg-emerald-900/10 p-3 text-xs" data-testid="save-result">
                  <p className="text-emerald-300">Version saved</p>
                  <p className="mt-1 text-slate-400">ID: <span className="font-mono" data-testid="saved-version-id">{saveResult.version_id}</span></p>
                </div>
              )}
            </section>

            {/* View single version */}
            <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="view-version-section">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">View Version</h2>
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
                  placeholder="Version ID"
                  value={viewVersionId}
                  onChange={(e) => setViewVersionId(e.target.value)}
                  data-testid="view-version-id-input"
                />
                <button
                  onClick={handleViewVersion}
                  disabled={!flowId.trim() || !viewVersionId.trim()}
                  className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                  data-testid="view-version-btn"
                >
                  Load
                </button>
              </div>
              {viewVersionError && (
                <p className="mt-2 text-xs text-red-400" data-testid="view-version-error">{viewVersionError}</p>
              )}
              {viewVersionResult && (
                <div className="mt-3" data-testid="view-version-result">
                  <p className="text-xs text-slate-400">Label: <span data-testid="view-version-label">{viewVersionResult.label ?? '—'}</span></p>
                  <pre className="mt-2 overflow-x-auto rounded border border-slate-700 bg-slate-900 p-2 text-xs text-slate-300">
                    {JSON.stringify(viewVersionResult, null, 2)}
                  </pre>
                </div>
              )}
            </section>

            {/* Version history */}
            <section className="rounded border border-slate-700 bg-slate-800/30 p-4 lg:col-span-2" data-testid="version-history-section">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-300">Version History</h2>
                <button
                  onClick={loadVersionHistory}
                  disabled={!flowId.trim()}
                  className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                  data-testid="load-history-btn"
                >
                  Load
                </button>
              </div>
              {versionsError && (
                <p className="mb-2 text-xs text-red-400" data-testid="versions-error">{versionsError}</p>
              )}
              {versionsLoading && (
                <p className="text-xs text-slate-500" data-testid="versions-loading">Loading…</p>
              )}
              {!versionsLoading && versions.length === 0 && (
                <p className="text-xs text-slate-500" data-testid="no-versions">No versions saved.</p>
              )}
              {versions.length > 0 && (
                <ul className="space-y-1" data-testid="versions-list">
                  {versions.map((v) => (
                    <li key={v.version_id} className="flex items-center gap-3 text-xs" data-testid="version-item">
                      <span className="font-mono text-slate-400" data-testid="version-id-cell">{v.version_id.slice(0, 8)}</span>
                      <span className="text-slate-300">{v.label ?? 'unlabeled'}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      )}
    </MainLayout>
  );
};

export default WorkflowSecretsPage;
