/**
 * WorkflowSnapshotsPage — Workflow snapshot management (N-122).
 *
 * Covers:
 *   POST /api/v1/workflows/{flow_id}/versions        → save a named snapshot
 *   GET  /api/v1/workflows/{flow_id}/version-history → list all version summaries
 *   GET  /api/v1/workflows/{flow_id}/versions/{id}   → full snapshot record
 *   POST /api/v1/workflows/{flow_id}/diff            → diff two raw snapshots
 *
 * Route: /workflow-snapshots (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface VersionSummary {
  version_id: string;
  label?: string;
  created_at?: number;
  node_count?: number;
}

interface VersionRecord extends VersionSummary {
  snapshot: unknown;
}

interface DiffResult {
  nodes_added?: string[];
  nodes_removed?: string[];
  nodes_changed?: string[];
  edges_added?: number;
  edges_removed?: number;
  summary?: string;
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

type TabId = 'save' | 'history' | 'inspect' | 'diff';

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const WorkflowSnapshotsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('history');

  // Save snapshot
  const [saveFlowId, setSaveFlowId] = useState('');
  const [saveSnapshot, setSaveSnapshot] = useState('');
  const [saveLabel, setSaveLabel] = useState('');
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveResult, setSaveResult] = useState<VersionSummary | null>(null);

  // Version history
  const [histFlowId, setHistFlowId] = useState('');
  const [histLoading, setHistLoading] = useState(false);
  const [histError, setHistError] = useState<string | null>(null);
  const [versions, setVersions] = useState<VersionSummary[] | null>(null);

  // Inspect version
  const [inspFlowId, setInspFlowId] = useState('');
  const [inspVersionId, setInspVersionId] = useState('');
  const [inspLoading, setInspLoading] = useState(false);
  const [inspError, setInspError] = useState<string | null>(null);
  const [inspRecord, setInspRecord] = useState<VersionRecord | null>(null);

  // Diff
  const [diffFlowId, setDiffFlowId] = useState('');
  const [diffV1, setDiffV1] = useState('');
  const [diffV2, setDiffV2] = useState('');
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!saveFlowId.trim()) return;
    let snapshotObj: unknown;
    try {
      snapshotObj = saveSnapshot.trim() ? JSON.parse(saveSnapshot) : {};
    } catch {
      setSaveError('Snapshot must be valid JSON');
      return;
    }
    setSaveLoading(true);
    setSaveError(null);
    setSaveResult(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${encodeURIComponent(saveFlowId.trim())}/versions`,
        {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ snapshot: snapshotObj, label: saveLabel.trim() || undefined }),
        },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setSaveError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setSaveResult(data as VersionSummary);
    } catch {
      setSaveError('Network error');
    } finally {
      setSaveLoading(false);
    }
  }

  async function handleLoadHistory(e: React.FormEvent) {
    e.preventDefault();
    if (!histFlowId.trim()) return;
    setHistLoading(true);
    setHistError(null);
    setVersions(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${encodeURIComponent(histFlowId.trim())}/version-history`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setHistError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setVersions(Array.isArray(data.versions) ? data.versions : []);
    } catch {
      setHistError('Network error');
    } finally {
      setHistLoading(false);
    }
  }

  async function handleInspect(e: React.FormEvent) {
    e.preventDefault();
    if (!inspFlowId.trim() || !inspVersionId.trim()) return;
    setInspLoading(true);
    setInspError(null);
    setInspRecord(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${encodeURIComponent(inspFlowId.trim())}/versions/${encodeURIComponent(inspVersionId.trim())}`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setInspError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setInspRecord(data as VersionRecord);
    } catch {
      setInspError('Network error');
    } finally {
      setInspLoading(false);
    }
  }

  async function handleDiff(e: React.FormEvent) {
    e.preventDefault();
    if (!diffFlowId.trim()) return;
    let v1Obj: unknown, v2Obj: unknown;
    try {
      v1Obj = JSON.parse(diffV1);
      v2Obj = JSON.parse(diffV2);
    } catch {
      setDiffError('Both snapshots must be valid JSON');
      return;
    }
    setDiffLoading(true);
    setDiffError(null);
    setDiffResult(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/workflows/${encodeURIComponent(diffFlowId.trim())}/diff`,
        {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ v1: v1Obj, v2: v2Obj }),
        },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setDiffError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setDiffResult(data as DiffResult);
    } catch {
      setDiffError('Network error');
    } finally {
      setDiffLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const tabs: { id: TabId; label: string }[] = [
    { id: 'history', label: 'Version History' },
    { id: 'inspect', label: 'Inspect Version' },
    { id: 'save', label: 'Save Snapshot' },
    { id: 'diff', label: 'Diff Snapshots' },
  ];

  return (
    <MainLayout title="Workflow Snapshots">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Workflow Snapshots
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Save, browse, inspect, and diff workflow version snapshots.
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-slate-700" data-testid="tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === t.id
                ? 'border-b-2 border-indigo-400 text-indigo-300'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            data-testid={`tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ---- Version History ---- */}
      {activeTab === 'history' && (
        <section data-testid="history-section">
          <form onSubmit={handleLoadHistory} className="mb-4 flex gap-2" data-testid="history-form">
            <input
              className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Flow ID"
              value={histFlowId}
              onChange={(e) => setHistFlowId(e.target.value)}
              data-testid="history-flow-id-input"
            />
            <button
              type="submit"
              disabled={histLoading || !histFlowId.trim()}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="history-load-btn"
            >
              {histLoading ? '…' : 'Load'}
            </button>
          </form>

          {histError && (
            <p className="mb-3 text-sm text-red-400" data-testid="history-error">{histError}</p>
          )}

          {versions !== null && versions.length === 0 && (
            <p className="text-sm text-slate-500" data-testid="no-versions">No versions saved.</p>
          )}

          {versions && versions.length > 0 && (
            <div data-testid="versions-list">
              <p className="mb-2 text-xs text-slate-500" data-testid="versions-count">
                {versions.length} version{versions.length !== 1 ? 's' : ''}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-700 text-left text-slate-500">
                      <th className="pb-2 pr-4 font-medium">Version ID</th>
                      <th className="pb-2 pr-4 font-medium">Label</th>
                      <th className="pb-2 font-medium">Nodes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.map((v) => (
                      <tr
                        key={v.version_id}
                        className="border-b border-slate-700/40 hover:bg-slate-800/30"
                        data-testid="version-row"
                        onClick={() => {
                          setInspFlowId(histFlowId);
                          setInspVersionId(v.version_id);
                          setActiveTab('inspect');
                        }}
                      >
                        <td className="py-2 pr-4 font-mono text-slate-300" data-testid="version-row-id">
                          {v.version_id.slice(0, 12)}…
                        </td>
                        <td className="py-2 pr-4 text-slate-400">{v.label ?? '—'}</td>
                        <td className="py-2 text-slate-400">{v.node_count ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}

      {/* ---- Inspect Version ---- */}
      {activeTab === 'inspect' && (
        <section data-testid="inspect-section">
          <form onSubmit={handleInspect} className="mb-4 flex flex-col gap-2 sm:flex-row" data-testid="inspect-form">
            <input
              className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Flow ID"
              value={inspFlowId}
              onChange={(e) => setInspFlowId(e.target.value)}
              data-testid="inspect-flow-id-input"
            />
            <input
              className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Version ID"
              value={inspVersionId}
              onChange={(e) => setInspVersionId(e.target.value)}
              data-testid="inspect-version-id-input"
            />
            <button
              type="submit"
              disabled={inspLoading || !inspFlowId.trim() || !inspVersionId.trim()}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="inspect-btn"
            >
              {inspLoading ? '…' : 'Fetch'}
            </button>
          </form>

          {inspError && (
            <p className="mb-3 text-sm text-red-400" data-testid="inspect-error">{inspError}</p>
          )}

          {inspRecord && (
            <div
              className="rounded border border-slate-700 bg-slate-800/30 p-4 space-y-3"
              data-testid="inspect-result"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-slate-400" data-testid="inspect-version-id">
                  {inspRecord.version_id}
                </span>
                {inspRecord.label && (
                  <span className="rounded bg-indigo-900/60 px-2 py-0.5 text-xs text-indigo-300" data-testid="inspect-label">
                    {inspRecord.label}
                  </span>
                )}
              </div>
              {inspRecord.node_count != null && (
                <p className="text-xs text-slate-500" data-testid="inspect-node-count">
                  Nodes: {inspRecord.node_count}
                </p>
              )}
              <div data-testid="inspect-snapshot">
                <p className="mb-1 text-xs text-slate-500">Snapshot:</p>
                <pre className="max-h-60 overflow-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-300">
                  {JSON.stringify(inspRecord.snapshot, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </section>
      )}

      {/* ---- Save Snapshot ---- */}
      {activeTab === 'save' && (
        <section data-testid="save-section">
          <form onSubmit={handleSave} className="space-y-3" data-testid="save-form">
            <div>
              <label className="mb-1 block text-xs text-slate-400" htmlFor="save-flow-id">
                Flow ID
              </label>
              <input
                id="save-flow-id"
                className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
                placeholder="e.g. flow-abc-123"
                value={saveFlowId}
                onChange={(e) => setSaveFlowId(e.target.value)}
                data-testid="save-flow-id-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400" htmlFor="save-label">
                Label (optional)
              </label>
              <input
                id="save-label"
                className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
                placeholder="e.g. before-refactor"
                value={saveLabel}
                onChange={(e) => setSaveLabel(e.target.value)}
                data-testid="save-label-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400" htmlFor="save-snapshot">
                Snapshot JSON
              </label>
              <textarea
                id="save-snapshot"
                className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 font-mono text-xs text-slate-200 placeholder-slate-500"
                rows={6}
                placeholder='{"nodes": [], "edges": []}'
                value={saveSnapshot}
                onChange={(e) => setSaveSnapshot(e.target.value)}
                data-testid="save-snapshot-input"
              />
            </div>
            <button
              type="submit"
              disabled={saveLoading || !saveFlowId.trim()}
              className="rounded bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="save-btn"
            >
              {saveLoading ? 'Saving…' : 'Save Snapshot'}
            </button>
          </form>

          {saveError && (
            <p className="mt-3 text-sm text-red-400" data-testid="save-error">{saveError}</p>
          )}

          {saveResult && (
            <div
              className="mt-4 rounded border border-emerald-700/40 bg-emerald-900/20 p-4"
              data-testid="save-result"
            >
              <p className="text-sm font-medium text-emerald-300">Snapshot saved</p>
              <p className="mt-1 font-mono text-xs text-slate-400" data-testid="save-result-version-id">
                {saveResult.version_id}
              </p>
              {saveResult.label && (
                <p className="mt-1 text-xs text-slate-500" data-testid="save-result-label">
                  Label: {saveResult.label}
                </p>
              )}
            </div>
          )}
        </section>
      )}

      {/* ---- Diff Snapshots ---- */}
      {activeTab === 'diff' && (
        <section data-testid="diff-section">
          <form onSubmit={handleDiff} className="space-y-3" data-testid="diff-form">
            <div>
              <label className="mb-1 block text-xs text-slate-400" htmlFor="diff-flow-id">
                Flow ID
              </label>
              <input
                id="diff-flow-id"
                className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
                placeholder="e.g. flow-abc-123"
                value={diffFlowId}
                onChange={(e) => setDiffFlowId(e.target.value)}
                data-testid="diff-flow-id-input"
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-slate-400" htmlFor="diff-v1">
                  Snapshot A (JSON)
                </label>
                <textarea
                  id="diff-v1"
                  className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 font-mono text-xs text-slate-200 placeholder-slate-500"
                  rows={5}
                  placeholder='{"nodes": [], "edges": []}'
                  value={diffV1}
                  onChange={(e) => setDiffV1(e.target.value)}
                  data-testid="diff-v1-input"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400" htmlFor="diff-v2">
                  Snapshot B (JSON)
                </label>
                <textarea
                  id="diff-v2"
                  className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 font-mono text-xs text-slate-200 placeholder-slate-500"
                  rows={5}
                  placeholder='{"nodes": [], "edges": []}'
                  value={diffV2}
                  onChange={(e) => setDiffV2(e.target.value)}
                  data-testid="diff-v2-input"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={diffLoading || !diffFlowId.trim() || !diffV1.trim() || !diffV2.trim()}
              className="rounded bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="diff-btn"
            >
              {diffLoading ? 'Diffing…' : 'Compute Diff'}
            </button>
          </form>

          {diffError && (
            <p className="mt-3 text-sm text-red-400" data-testid="diff-error">{diffError}</p>
          )}

          {diffResult && (
            <div
              className="mt-4 rounded border border-slate-700 bg-slate-800/30 p-4 space-y-3"
              data-testid="diff-result"
            >
              <p className="text-sm font-semibold text-slate-200">Diff Result</p>
              {diffResult.summary && (
                <p className="text-xs text-slate-400" data-testid="diff-summary">{diffResult.summary}</p>
              )}
              {diffResult.nodes_added && diffResult.nodes_added.length > 0 && (
                <div data-testid="diff-nodes-added">
                  <p className="text-xs font-medium text-emerald-400">
                    Added ({diffResult.nodes_added.length})
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {diffResult.nodes_added.map((n) => (
                      <li key={n} className="rounded bg-emerald-900/40 px-2 py-0.5 font-mono text-xs text-emerald-300">
                        {n}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {diffResult.nodes_removed && diffResult.nodes_removed.length > 0 && (
                <div data-testid="diff-nodes-removed">
                  <p className="text-xs font-medium text-red-400">
                    Removed ({diffResult.nodes_removed.length})
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {diffResult.nodes_removed.map((n) => (
                      <li key={n} className="rounded bg-red-900/40 px-2 py-0.5 font-mono text-xs text-red-300">
                        {n}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {diffResult.nodes_changed && diffResult.nodes_changed.length > 0 && (
                <div data-testid="diff-nodes-changed">
                  <p className="text-xs font-medium text-amber-400">
                    Changed ({diffResult.nodes_changed.length})
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {diffResult.nodes_changed.map((n) => (
                      <li key={n} className="rounded bg-amber-900/40 px-2 py-0.5 font-mono text-xs text-amber-300">
                        {n}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-slate-500" data-testid="diff-edges-summary">
                Edges: +{diffResult.edges_added ?? 0} / −{diffResult.edges_removed ?? 0}
              </p>
            </div>
          )}
        </section>
      )}
    </MainLayout>
  );
};

export default WorkflowSnapshotsPage;
