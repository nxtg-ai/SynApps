/**
 * TemplateManagerPage — Template Registry Manager (N-96).
 *
 * Covers:
 *   GET    /api/v1/templates                         → list with optional category filter
 *   GET    /api/v1/templates/search                  → full-text + tag search
 *   POST   /api/v1/templates/import                  → import from JSON blob
 *   GET    /api/v1/templates/{id}/export             → download JSON
 *   GET    /api/v1/templates/{id}/versions           → version history
 *   PUT    /api/v1/templates/{id}/rollback?version=  → rollback to semver
 *   POST   /api/v1/templates/{id}/instantiate        → create flow from template
 *
 * Route: /templates-manager (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Template {
  id: string;
  name: string;
  description?: string;
  version?: number;
  semver?: string;
  tags?: string[];
  nodes?: unknown[];
  edges?: unknown[];
  metadata?: Record<string, unknown>;
}

interface TemplateVersion {
  version: number;
  semver: string;
  created_at?: string | number;
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

const TemplateManagerPage: React.FC = () => {
  // ── List / search state ───────────────────────────────────────────────────
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [category, setCategory] = useState('');
  const [searchQ, setSearchQ] = useState('');
  const [searchTags, setSearchTags] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // ── Selected template + detail tabs ───────────────────────────────────────
  const [selected, setSelected] = useState<Template | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'versions' | 'instantiate'>('overview');

  // ── Versions sub-state ────────────────────────────────────────────────────
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versions, setVersions] = useState<TemplateVersion[]>([]);
  const [rollbackTarget, setRollbackTarget] = useState('');
  const [rolling, setRolling] = useState(false);
  const [rollbackError, setRollbackError] = useState<string | null>(null);
  const [rollbackSuccess, setRollbackSuccess] = useState<string | null>(null);

  // ── Instantiate sub-state ─────────────────────────────────────────────────
  const [flowName, setFlowName] = useState('');
  const [instantiating, setInstantiating] = useState(false);
  const [instantiateError, setInstantiateError] = useState<string | null>(null);
  const [instantiateResult, setInstantiateResult] = useState<Record<string, unknown> | null>(null);

  // ── Import state ──────────────────────────────────────────────────────────
  const [importJson, setImportJson] = useState('');
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Load template list
  // ---------------------------------------------------------------------------

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const params = category ? `?category=${encodeURIComponent(category)}` : '';
      const resp = await fetch(`${getBaseUrl()}/templates${params}`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setListError(`Failed to load templates (${resp.status})`);
        return;
      }
      const data = await resp.json();
      setTemplates(Array.isArray(data) ? data : Array.isArray(data.templates) ? data.templates : []);
    } catch {
      setListError('Network error loading templates');
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  // ---------------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------------

  const handleSearch = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setSearching(true);
      setSearchError(null);
      try {
        const params = new URLSearchParams();
        if (searchQ.trim()) params.set('q', searchQ.trim());
        searchTags
          .split(/\s+/)
          .filter(Boolean)
          .forEach((t) => params.append('tags', t));
        const resp = await fetch(`${getBaseUrl()}/templates/search?${params}`, {
          headers: authHeaders(),
        });
        if (!resp.ok) {
          setSearchError(`Search failed (${resp.status})`);
          return;
        }
        const data = await resp.json();
        setTemplates(Array.isArray(data) ? data : Array.isArray(data.items) ? data.items : []);
      } catch {
        setSearchError('Network error during search');
      } finally {
        setSearching(false);
      }
    },
    [searchQ, searchTags],
  );

  // ---------------------------------------------------------------------------
  // Import
  // ---------------------------------------------------------------------------

  const handleImport = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setImporting(true);
      setImportError(null);
      setImportSuccess(null);
      let parsed: unknown;
      try {
        parsed = JSON.parse(importJson);
      } catch {
        setImportError('Invalid JSON');
        setImporting(false);
        return;
      }
      try {
        const resp = await fetch(`${getBaseUrl()}/templates/import`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(parsed),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setImportError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const entry: Template = await resp.json();
        setImportSuccess(`Imported: ${entry.name ?? entry.id} (v${entry.version ?? 1})`);
        setImportJson('');
        setTemplates((prev) => [entry, ...prev]);
      } catch {
        setImportError('Network error importing template');
      } finally {
        setImporting(false);
      }
    },
    [importJson],
  );

  // ---------------------------------------------------------------------------
  // Load versions for selected template
  // ---------------------------------------------------------------------------

  const loadVersions = useCallback(async (templateId: string) => {
    setVersionsLoading(true);
    setVersionsError(null);
    setVersions([]);
    setRollbackError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/templates/${encodeURIComponent(templateId)}/versions`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setVersionsError(`Failed to load versions (${resp.status})`);
        return;
      }
      const data = await resp.json();
      setVersions(Array.isArray(data.versions) ? data.versions : []);
    } catch {
      setVersionsError('Network error loading versions');
    } finally {
      setVersionsLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Rollback
  // ---------------------------------------------------------------------------

  const handleRollback = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!selected || !rollbackTarget.trim()) return;
      setRolling(true);
      setRollbackError(null);
      setRollbackSuccess(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/templates/${encodeURIComponent(selected.id)}/rollback?version=${encodeURIComponent(rollbackTarget.trim())}`,
          { method: 'PUT', headers: authHeaders() },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setRollbackError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const entry: Template = await resp.json();
        setRollbackSuccess(`Rolled back to ${rollbackTarget} → new version ${entry.version ?? '?'} (${entry.semver ?? ''})`);
        setRollbackTarget('');
        loadVersions(selected.id);
      } catch {
        setRollbackError('Network error during rollback');
      } finally {
        setRolling(false);
      }
    },
    [selected, rollbackTarget, loadVersions],
  );

  // ---------------------------------------------------------------------------
  // Instantiate
  // ---------------------------------------------------------------------------

  const handleInstantiate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!selected) return;
      setInstantiating(true);
      setInstantiateError(null);
      setInstantiateResult(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/templates/${encodeURIComponent(selected.id)}/instantiate`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
              flow_name: flowName.trim() || `${selected.name} (from template)`,
              connector_overrides: {},
            }),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setInstantiateError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const result = await resp.json();
        setInstantiateResult(result as Record<string, unknown>);
        setFlowName('');
      } catch {
        setInstantiateError('Network error instantiating template');
      } finally {
        setInstantiating(false);
      }
    },
    [selected, flowName],
  );

  // ---------------------------------------------------------------------------
  // Select template
  // ---------------------------------------------------------------------------

  const selectTemplate = (tpl: Template) => {
    setSelected(tpl);
    setActiveTab('overview');
    setVersions([]);
    setVersionsError(null);
    setRollbackSuccess(null);
    setRollbackError(null);
    setInstantiateResult(null);
    setInstantiateError(null);
  };

  const handleTabChange = (tab: 'overview' | 'versions' | 'instantiate') => {
    setActiveTab(tab);
    if (tab === 'versions' && selected && versions.length === 0 && !versionsLoading) {
      loadVersions(selected.id);
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Template Manager">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Template Manager
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Browse, import, export, and instantiate workflow templates.
          </p>
        </div>
        <button
          onClick={loadTemplates}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* ── Search + Category filter ── */}
      <section
        className="mb-6 rounded border border-slate-700 bg-slate-800/30 p-4"
        data-testid="search-section"
      >
        <div className="flex flex-wrap items-end gap-3">
          <form onSubmit={handleSearch} className="flex flex-wrap gap-2" data-testid="search-form">
            <input
              type="text"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              placeholder="Search by name / description"
              className="w-56 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="search-q-input"
            />
            <input
              type="text"
              value={searchTags}
              onChange={(e) => setSearchTags(e.target.value)}
              placeholder="Tags (space-separated)"
              className="w-40 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="search-tags-input"
            />
            <button
              type="submit"
              disabled={searching}
              className="rounded bg-indigo-700 px-3 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="search-btn"
            >
              {searching ? 'Searching…' : 'Search'}
            </button>
          </form>

          <div className="flex items-center gap-2">
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="category-select"
            >
              <option value="">All categories</option>
              <option value="notification">Notification</option>
              <option value="data-sync">Data Sync</option>
              <option value="monitoring">Monitoring</option>
              <option value="content">Content</option>
              <option value="devops">DevOps</option>
            </select>
          </div>
        </div>
        {searchError && (
          <p className="mt-2 text-sm text-red-400" data-testid="search-error">
            {searchError}
          </p>
        )}
      </section>

      {/* ── Import section ── */}
      <section
        className="mb-6 rounded border border-slate-700 bg-slate-800/30 p-4"
        data-testid="import-section"
      >
        <h2 className="mb-3 text-sm font-semibold text-slate-300">Import Template JSON</h2>
        <form onSubmit={handleImport} className="space-y-2" data-testid="import-form">
          <textarea
            value={importJson}
            onChange={(e) => setImportJson(e.target.value)}
            placeholder='{"name": "My Template", "nodes": [], "edges": []}'
            rows={3}
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-200 focus:outline-none"
            data-testid="import-json-input"
          />
          <button
            type="submit"
            disabled={importing || !importJson.trim()}
            className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
            data-testid="import-btn"
          >
            {importing ? 'Importing…' : 'Import'}
          </button>
        </form>
        {importError && (
          <p className="mt-2 text-sm text-red-400" data-testid="import-error">
            {importError}
          </p>
        )}
        {importSuccess && (
          <p className="mt-2 text-sm text-emerald-400" data-testid="import-success">
            {importSuccess}
          </p>
        )}
      </section>

      {/* ── Two-column: list + detail ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Left: template list */}
        <div>
          {listError && (
            <p className="mb-3 text-sm text-red-400" data-testid="list-error">
              {listError}
            </p>
          )}
          {loading && templates.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="list-loading">
              Loading…
            </p>
          )}
          {!loading && templates.length === 0 && !listError && (
            <p className="text-xs text-slate-500" data-testid="no-templates">
              No templates found.
            </p>
          )}
          {templates.length > 0 && (
            <div className="space-y-2" data-testid="templates-list">
              {templates.map((tpl) => (
                <button
                  key={tpl.id}
                  onClick={() => selectTemplate(tpl)}
                  className={`w-full rounded border px-4 py-3 text-left text-sm transition-colors ${
                    selected?.id === tpl.id
                      ? 'border-indigo-500 bg-indigo-900/20 text-slate-100'
                      : 'border-slate-700 bg-slate-800/30 text-slate-300 hover:border-slate-500'
                  }`}
                  data-testid="template-item"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{tpl.name}</span>
                    {tpl.semver && (
                      <span className="text-xs text-slate-500" data-testid="template-semver">
                        v{tpl.semver}
                      </span>
                    )}
                  </div>
                  {tpl.description && (
                    <p className="mt-0.5 text-xs text-slate-400 line-clamp-1">{tpl.description}</p>
                  )}
                  {tpl.tags && tpl.tags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {tpl.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-400"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: detail panel */}
        <div>
          {!selected ? (
            <p className="text-xs text-slate-500" data-testid="no-template-selected">
              Select a template to view details.
            </p>
          ) : (
            <div
              className="rounded border border-slate-700 bg-slate-800/30 p-4"
              data-testid="template-detail"
            >
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-base font-semibold text-slate-100" data-testid="detail-name">
                  {selected.name}
                </h2>
                <a
                  href={`${getBaseUrl()}/api/v1/templates/${encodeURIComponent(selected.id)}/export`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
                  data-testid="export-link"
                >
                  Export JSON
                </a>
              </div>

              {/* Tabs */}
              <div className="mb-4 flex gap-2 border-b border-slate-700 pb-2" data-testid="detail-tabs">
                {(['overview', 'versions', 'instantiate'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => handleTabChange(tab)}
                    className={`px-3 py-1 text-xs font-medium capitalize transition-colors ${
                      activeTab === tab
                        ? 'border-b-2 border-indigo-500 text-indigo-400'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                    data-testid={`tab-${tab}`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Overview tab */}
              {activeTab === 'overview' && (
                <div data-testid="tab-panel-overview">
                  {selected.description && (
                    <p className="mb-3 text-sm text-slate-300" data-testid="detail-description">
                      {selected.description}
                    </p>
                  )}
                  <dl className="space-y-1 text-xs">
                    <div className="flex gap-2">
                      <dt className="w-24 text-slate-500">ID</dt>
                      <dd className="font-mono text-slate-400" data-testid="detail-id">
                        {selected.id}
                      </dd>
                    </div>
                    {selected.semver && (
                      <div className="flex gap-2">
                        <dt className="w-24 text-slate-500">Version</dt>
                        <dd className="text-slate-400" data-testid="detail-semver">
                          {selected.semver}
                        </dd>
                      </div>
                    )}
                    <div className="flex gap-2">
                      <dt className="w-24 text-slate-500">Nodes</dt>
                      <dd className="text-slate-400" data-testid="detail-node-count">
                        {selected.nodes?.length ?? 0}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="w-24 text-slate-500">Edges</dt>
                      <dd className="text-slate-400" data-testid="detail-edge-count">
                        {selected.edges?.length ?? 0}
                      </dd>
                    </div>
                  </dl>
                  {selected.tags && selected.tags.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {selected.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-400"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Versions tab */}
              {activeTab === 'versions' && (
                <div data-testid="tab-panel-versions">
                  {versionsLoading && (
                    <p className="text-xs text-slate-500" data-testid="versions-loading">
                      Loading versions…
                    </p>
                  )}
                  {versionsError && (
                    <p className="text-sm text-red-400" data-testid="versions-error">
                      {versionsError}
                    </p>
                  )}
                  {!versionsLoading && !versionsError && versions.length === 0 && (
                    <p className="text-xs text-slate-500" data-testid="no-versions">
                      No versions found.
                    </p>
                  )}
                  {versions.length > 0 && (
                    <table className="mb-4 w-full text-xs" data-testid="versions-table">
                      <thead>
                        <tr className="border-b border-slate-700 text-left text-slate-500">
                          <th className="pb-1 pr-4 font-medium">#</th>
                          <th className="pb-1 pr-4 font-medium">Semver</th>
                          <th className="pb-1 font-medium">Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {versions.map((v) => (
                          <tr
                            key={v.version}
                            className="border-b border-slate-700/40"
                            data-testid="version-row"
                          >
                            <td className="py-1 pr-4 text-slate-400">{v.version}</td>
                            <td className="py-1 pr-4 font-mono text-slate-300">{v.semver}</td>
                            <td className="py-1 text-slate-500">
                              {v.created_at
                                ? typeof v.created_at === 'number'
                                  ? new Date(v.created_at * 1000).toLocaleDateString()
                                  : String(v.created_at)
                                : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {/* Rollback form */}
                  <form onSubmit={handleRollback} className="space-y-2" data-testid="rollback-form">
                    <label className="block text-xs text-slate-400">Rollback to semver:</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={rollbackTarget}
                        onChange={(e) => setRollbackTarget(e.target.value)}
                        placeholder="e.g. 1.0.0"
                        className="w-32 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-200 focus:outline-none"
                        data-testid="rollback-input"
                      />
                      <button
                        type="submit"
                        disabled={rolling || !rollbackTarget.trim()}
                        className="rounded bg-yellow-700 px-3 py-1 text-xs text-white hover:bg-yellow-600 disabled:opacity-50"
                        data-testid="rollback-btn"
                      >
                        {rolling ? 'Rolling back…' : 'Rollback'}
                      </button>
                    </div>
                  </form>
                  {rollbackError && (
                    <p className="mt-2 text-xs text-red-400" data-testid="rollback-error">
                      {rollbackError}
                    </p>
                  )}
                  {rollbackSuccess && (
                    <p className="mt-2 text-xs text-emerald-400" data-testid="rollback-success">
                      {rollbackSuccess}
                    </p>
                  )}
                </div>
              )}

              {/* Instantiate tab */}
              {activeTab === 'instantiate' && (
                <div data-testid="tab-panel-instantiate">
                  <p className="mb-3 text-xs text-slate-400">
                    Create a new workflow flow from this template.
                  </p>
                  <form onSubmit={handleInstantiate} className="space-y-2" data-testid="instantiate-form">
                    <input
                      type="text"
                      value={flowName}
                      onChange={(e) => setFlowName(e.target.value)}
                      placeholder={`${selected.name} (from template)`}
                      className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                      data-testid="flow-name-input"
                    />
                    <button
                      type="submit"
                      disabled={instantiating}
                      className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
                      data-testid="instantiate-btn"
                    >
                      {instantiating ? 'Creating…' : 'Create Flow'}
                    </button>
                  </form>
                  {instantiateError && (
                    <p className="mt-2 text-sm text-red-400" data-testid="instantiate-error">
                      {instantiateError}
                    </p>
                  )}
                  {instantiateResult && (
                    <div
                      className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
                      data-testid="instantiate-result"
                    >
                      <p className="mb-1 font-semibold text-emerald-400">Flow created!</p>
                      <p className="text-slate-300">
                        Flow ID:{' '}
                        <span className="font-mono" data-testid="new-flow-id">
                          {String((instantiateResult as Record<string, unknown>).id ?? (instantiateResult as Record<string, unknown>).flow_id ?? '—')}
                        </span>
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </MainLayout>
  );
};

export default TemplateManagerPage;
