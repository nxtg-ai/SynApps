/**
 * FlowExportImportPage — Flow-level export + import (N-120).
 *
 * Covers:
 *   GET  /api/v1/flows/{flow_id}/export  → download flow as SynApps JSON
 *   POST /api/v1/flows/import            → create a new flow from a JSON export
 *
 * Route: /flow-export-import (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ImportedFlow {
  id: string;
  name: string;
  node_count?: number;
  edge_count?: number;
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

const FlowExportImportPage: React.FC = () => {
  const [tab, setTab] = useState<'export' | 'import'>('export');

  // Export
  const [exportFlowId, setExportFlowId] = useState('');
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportData, setExportData] = useState<Record<string, unknown> | null>(null);

  // Import
  const [importJson, setImportJson] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportedFlow | null>(null);

  // ---------------------------------------------------------------------------
  // Export handler
  // ---------------------------------------------------------------------------

  async function handleExport(e: React.FormEvent) {
    e.preventDefault();
    if (!exportFlowId.trim()) return;
    setExportLoading(true);
    setExportError(null);
    setExportData(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/flows/${encodeURIComponent(exportFlowId.trim())}/export`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setExportError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setExportData(data as Record<string, unknown>);
    } catch {
      setExportError('Network error');
    } finally {
      setExportLoading(false);
    }
  }

  function handleDownload() {
    if (!exportData) return;
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `flow-${exportFlowId.trim()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---------------------------------------------------------------------------
  // Import handler
  // ---------------------------------------------------------------------------

  async function handleImport(e: React.FormEvent) {
    e.preventDefault();
    setImportLoading(true);
    setImportError(null);
    setImportResult(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(importJson) as Record<string, unknown>;
    } catch {
      setImportError('Invalid JSON — please paste a valid flow export.');
      setImportLoading(false);
      return;
    }
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/flows/import`, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify(parsed),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setImportError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setImportResult(data as ImportedFlow);
    } catch {
      setImportError('Network error');
    } finally {
      setImportLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Flow Export / Import">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Flow Export / Import
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Download flows as portable JSON or import from a previous export.
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-2" data-testid="tabs">
        {(['export', 'import'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded px-4 py-1.5 text-sm font-medium ${
              tab === t
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:text-slate-200'
            }`}
            data-testid={`tab-${t}`}
          >
            {t === 'export' ? 'Export Flow' : 'Import Flow'}
          </button>
        ))}
      </div>

      {/* ---- Export tab ---- */}
      {tab === 'export' && (
        <section data-testid="export-section">
          <form onSubmit={handleExport} className="mb-4 flex items-end gap-3" data-testid="export-form">
            <div>
              <label className="mb-1 block text-xs text-slate-400">Flow ID</label>
              <input
                className="w-72 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
                placeholder="flow-id"
                value={exportFlowId}
                onChange={(e) => setExportFlowId(e.target.value)}
                required
                data-testid="export-flow-id-input"
              />
            </div>
            <button
              type="submit"
              disabled={exportLoading || !exportFlowId.trim()}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="export-btn"
            >
              {exportLoading ? 'Exporting…' : 'Export'}
            </button>
          </form>

          {exportError && (
            <p className="mb-3 text-sm text-red-400" data-testid="export-error">{exportError}</p>
          )}

          {exportData && (
            <div className="space-y-3" data-testid="export-result">
              <div className="flex items-center gap-3">
                <p className="text-sm text-emerald-300">Export ready.</p>
                <button
                  onClick={handleDownload}
                  className="rounded bg-emerald-700 px-3 py-1 text-xs text-white hover:bg-emerald-600"
                  data-testid="download-btn"
                >
                  Download JSON
                </button>
              </div>
              <div className="flex gap-6 text-xs text-slate-400" data-testid="export-meta">
                {exportData.name && (
                  <span>Name: <strong className="text-slate-300" data-testid="export-name">{String(exportData.name)}</strong></span>
                )}
                {Array.isArray(exportData.nodes) && (
                  <span data-testid="export-node-count">Nodes: {(exportData.nodes as unknown[]).length}</span>
                )}
                {Array.isArray(exportData.edges) && (
                  <span data-testid="export-edge-count">Edges: {(exportData.edges as unknown[]).length}</span>
                )}
              </div>
              <pre
                className="max-h-64 overflow-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-300"
                data-testid="export-preview"
              >
                {JSON.stringify(exportData, null, 2).slice(0, 800)}
                {JSON.stringify(exportData, null, 2).length > 800 ? '\n…' : ''}
              </pre>
            </div>
          )}
        </section>
      )}

      {/* ---- Import tab ---- */}
      {tab === 'import' && (
        <section data-testid="import-section">
          <form onSubmit={handleImport} className="space-y-4" data-testid="import-form">
            <div>
              <label className="mb-1 block text-xs text-slate-400">
                Paste flow JSON export
              </label>
              <textarea
                className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 font-mono text-xs text-slate-200"
                rows={12}
                placeholder='{"synapps_version":"1.0.0","name":"My Flow","nodes":[...],"edges":[...]}'
                value={importJson}
                onChange={(e) => setImportJson(e.target.value)}
                required
                data-testid="import-json-input"
              />
            </div>
            <button
              type="submit"
              disabled={importLoading || !importJson.trim()}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="import-btn"
            >
              {importLoading ? 'Importing…' : 'Import Flow'}
            </button>
          </form>

          {importError && (
            <p className="mt-3 text-sm text-red-400" data-testid="import-error">{importError}</p>
          )}

          {importResult && (
            <div
              className="mt-4 rounded border border-emerald-700/40 bg-emerald-900/10 p-4"
              data-testid="import-result"
            >
              <p className="text-sm text-emerald-300">Flow imported successfully.</p>
              <div className="mt-2 flex gap-6 text-xs text-slate-400">
                <span>
                  ID: <span className="font-mono text-slate-300" data-testid="import-flow-id">{importResult.id}</span>
                </span>
                <span>
                  Name: <span className="text-slate-300" data-testid="import-flow-name">{importResult.name}</span>
                </span>
              </div>
            </div>
          )}
        </section>
      )}
    </MainLayout>
  );
};

export default FlowExportImportPage;
