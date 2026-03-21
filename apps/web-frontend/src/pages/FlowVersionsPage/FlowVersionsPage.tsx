/**
 * FlowVersionsPage — Flow Version History & Rollback (N-97).
 *
 * Covers:
 *   GET    /api/v1/flows/{flow_id}/versions                  → list flow versions
 *   GET    /api/v1/flows/{flow_id}/versions/{version_id}     → version detail/snapshot
 *   POST   /api/v1/flows/{flow_id}/rollback?version_id=      → rollback to version
 *   GET    /api/v1/flows/{flow_id}/rollback/history          → per-flow rollback audit
 *   GET    /api/v1/rollback/history                          → global rollback audit
 *
 * Route: /flow-versions (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FlowVersion {
  version_id: string;
  version: number;
  snapshotted_at?: string | number;
}

interface AuditEntry {
  id?: string;
  flow_id: string;
  from_version_id: string;
  to_version_id: string;
  performed_by?: string;
  reason?: string;
  rolled_back_at?: string | number;
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

function fmtTs(ts?: string | number): string {
  if (ts == null) return '—';
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  return isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type ActiveSection = 'versions' | 'audit' | 'global-audit';

const FlowVersionsPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [activeSection, setActiveSection] = useState<ActiveSection>('versions');

  // ── Versions state ────────────────────────────────────────────────────────
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versions, setVersions] = useState<FlowVersion[]>([]);

  // ── Version detail ────────────────────────────────────────────────────────
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [versionDetail, setVersionDetail] = useState<Record<string, unknown> | null>(null);

  // ── Rollback state ────────────────────────────────────────────────────────
  const [rollbackVersionId, setRollbackVersionId] = useState('');
  const [rollbackReason, setRollbackReason] = useState('');
  const [rolling, setRolling] = useState(false);
  const [rollbackError, setRollbackError] = useState<string | null>(null);
  const [rollbackResult, setRollbackResult] = useState<Record<string, unknown> | null>(null);

  // ── Per-flow audit state ──────────────────────────────────────────────────
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);

  // ── Global audit state ────────────────────────────────────────────────────
  const [globalLoading, setGlobalLoading] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [globalEntries, setGlobalEntries] = useState<AuditEntry[]>([]);

  // ---------------------------------------------------------------------------
  // Load versions
  // ---------------------------------------------------------------------------

  const handleLoadVersions = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim()) return;
      setVersionsLoading(true);
      setVersionsError(null);
      setVersions([]);
      setVersionDetail(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/flows/${encodeURIComponent(flowId.trim())}/versions`,
          { headers: authHeaders() },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setVersionsError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const data = await resp.json();
        setVersions(Array.isArray(data) ? data : Array.isArray(data.items) ? data.items : []);
      } catch {
        setVersionsError('Network error loading versions');
      } finally {
        setVersionsLoading(false);
      }
    },
    [flowId],
  );

  // ---------------------------------------------------------------------------
  // Load version detail
  // ---------------------------------------------------------------------------

  const loadVersionDetail = useCallback(
    async (versionId: string) => {
      if (!flowId.trim()) return;
      setDetailLoading(true);
      setDetailError(null);
      setVersionDetail(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/flows/${encodeURIComponent(flowId.trim())}/versions/${encodeURIComponent(versionId)}`,
          { headers: authHeaders() },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setDetailError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setVersionDetail(await resp.json());
      } catch {
        setDetailError('Network error loading version detail');
      } finally {
        setDetailLoading(false);
      }
    },
    [flowId],
  );

  // ---------------------------------------------------------------------------
  // Rollback
  // ---------------------------------------------------------------------------

  const handleRollback = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim() || !rollbackVersionId.trim()) return;
      setRolling(true);
      setRollbackError(null);
      setRollbackResult(null);
      try {
        const params = new URLSearchParams({ version_id: rollbackVersionId.trim() });
        const resp = await fetch(
          `${getBaseUrl()}/flows/${encodeURIComponent(flowId.trim())}/rollback?${params}`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: rollbackReason.trim() }),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setRollbackError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const result = await resp.json();
        setRollbackResult(result as Record<string, unknown>);
        setRollbackVersionId('');
        setRollbackReason('');
      } catch {
        setRollbackError('Network error during rollback');
      } finally {
        setRolling(false);
      }
    },
    [flowId, rollbackVersionId, rollbackReason],
  );

  // ---------------------------------------------------------------------------
  // Per-flow audit
  // ---------------------------------------------------------------------------

  const handleLoadAudit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim()) return;
      setAuditLoading(true);
      setAuditError(null);
      setAuditEntries([]);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/flows/${encodeURIComponent(flowId.trim())}/rollback/history`,
          { headers: authHeaders() },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setAuditError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const data = await resp.json();
        setAuditEntries(Array.isArray(data) ? data : Array.isArray(data.items) ? data.items : []);
      } catch {
        setAuditError('Network error loading audit history');
      } finally {
        setAuditLoading(false);
      }
    },
    [flowId],
  );

  // ---------------------------------------------------------------------------
  // Global audit
  // ---------------------------------------------------------------------------

  const handleLoadGlobal = useCallback(async () => {
    setGlobalLoading(true);
    setGlobalError(null);
    setGlobalEntries([]);
    try {
      const resp = await fetch(`${getBaseUrl()}/rollback/history`, { headers: authHeaders() });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setGlobalError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      const data = await resp.json();
      setGlobalEntries(Array.isArray(data) ? data : Array.isArray(data.items) ? data.items : []);
    } catch {
      setGlobalError('Network error loading global audit');
    } finally {
      setGlobalLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  function renderAuditTable(entries: AuditEntry[], testIdPrefix: string) {
    if (entries.length === 0) return null;
    return (
      <div className="overflow-x-auto" data-testid={`${testIdPrefix}-table`}>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-700 text-left text-slate-500">
              <th className="pb-1 pr-3 font-medium">Flow</th>
              <th className="pb-1 pr-3 font-medium">From</th>
              <th className="pb-1 pr-3 font-medium">To</th>
              <th className="pb-1 pr-3 font-medium">By</th>
              <th className="pb-1 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr
                key={e.id ?? i}
                className="border-b border-slate-700/40"
                data-testid={`${testIdPrefix}-row`}
              >
                <td className="py-1 pr-3 font-mono text-slate-400">{e.flow_id}</td>
                <td className="py-1 pr-3 font-mono text-slate-400">{e.from_version_id}</td>
                <td className="py-1 pr-3 font-mono text-slate-300">{e.to_version_id}</td>
                <td className="py-1 pr-3 text-slate-400">{e.performed_by ?? '—'}</td>
                <td className="py-1 text-slate-400">{e.reason || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Flow Versions">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Flow Version History
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Browse snapshots, roll back flows, and audit rollback history.
        </p>
      </div>

      {/* Flow ID input (shared across sections) */}
      <div className="mb-6 flex items-center gap-3">
        <input
          type="text"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          placeholder="Flow ID"
          className="w-64 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
          data-testid="flow-id-input"
        />
      </div>

      {/* Section tabs */}
      <div className="mb-6 flex gap-2 border-b border-slate-700 pb-2" data-testid="section-tabs">
        {(['versions', 'audit', 'global-audit'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setActiveSection(s)}
            className={`px-4 py-1.5 text-xs font-medium capitalize transition-colors ${
              activeSection === s
                ? 'border-b-2 border-indigo-500 text-indigo-400'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            data-testid={`tab-${s}`}
          >
            {s === 'global-audit' ? 'Global Audit' : s === 'audit' ? 'Flow Audit' : 'Versions'}
          </button>
        ))}
      </div>

      {/* ── Versions section ── */}
      {activeSection === 'versions' && (
        <div data-testid="versions-section">
          <form onSubmit={handleLoadVersions} className="mb-4 flex gap-2" data-testid="versions-form">
            <button
              type="submit"
              disabled={versionsLoading || !flowId.trim()}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="load-versions-btn"
            >
              {versionsLoading ? 'Loading…' : 'Load Versions'}
            </button>
          </form>

          {versionsError && (
            <p className="mb-3 text-sm text-red-400" data-testid="versions-error">
              {versionsError}
            </p>
          )}

          {!versionsLoading && versions.length === 0 && !versionsError && (
            <p className="text-xs text-slate-500" data-testid="no-versions">
              No versions loaded.
            </p>
          )}

          {/* Version list + detail */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {versions.length > 0 && (
              <div data-testid="versions-list">
                {versions.map((v) => (
                  <button
                    key={v.version_id}
                    onClick={() => loadVersionDetail(v.version_id)}
                    className="mb-2 w-full rounded border border-slate-700 bg-slate-800/30 px-4 py-2 text-left text-xs text-slate-300 hover:border-slate-500"
                    data-testid="version-item"
                  >
                    <span className="font-mono text-slate-400">{v.version_id}</span>
                    <span className="ml-3 text-slate-500">v{v.version}</span>
                    <span className="ml-3 text-slate-500">{fmtTs(v.snapshotted_at)}</span>
                  </button>
                ))}
              </div>
            )}

            <div>
              {detailLoading && (
                <p className="text-xs text-slate-500" data-testid="detail-loading">
                  Loading snapshot…
                </p>
              )}
              {detailError && (
                <p className="text-sm text-red-400" data-testid="detail-error">
                  {detailError}
                </p>
              )}
              {versionDetail && (
                <div
                  className="rounded border border-slate-700 bg-slate-900 p-3"
                  data-testid="version-detail"
                >
                  <p className="mb-2 text-xs font-semibold text-slate-400">Snapshot</p>
                  <pre className="overflow-auto text-xs text-slate-300">
                    {JSON.stringify(versionDetail, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>

          {/* Rollback form */}
          <section
            className="mt-6 rounded border border-slate-700 bg-slate-800/30 p-4"
            data-testid="rollback-section"
          >
            <h2 className="mb-3 text-sm font-semibold text-slate-300">Rollback Flow</h2>
            <form onSubmit={handleRollback} className="space-y-3" data-testid="rollback-form">
              <div className="flex flex-wrap gap-3">
                <input
                  type="text"
                  value={rollbackVersionId}
                  onChange={(e) => setRollbackVersionId(e.target.value)}
                  placeholder="Version ID to rollback to"
                  className="w-64 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                  data-testid="rollback-version-id-input"
                />
                <input
                  type="text"
                  value={rollbackReason}
                  onChange={(e) => setRollbackReason(e.target.value)}
                  placeholder="Reason (optional)"
                  className="w-48 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                  data-testid="rollback-reason-input"
                />
              </div>
              <button
                type="submit"
                disabled={rolling || !flowId.trim() || !rollbackVersionId.trim()}
                className="rounded bg-yellow-700 px-4 py-1.5 text-sm text-white hover:bg-yellow-600 disabled:opacity-50"
                data-testid="rollback-btn"
              >
                {rolling ? 'Rolling back…' : 'Rollback'}
              </button>
            </form>
            {rollbackError && (
              <p className="mt-2 text-sm text-red-400" data-testid="rollback-error">
                {rollbackError}
              </p>
            )}
            {rollbackResult && (
              <div
                className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
                data-testid="rollback-result"
              >
                <p className="mb-1 font-semibold text-emerald-400">Rollback successful!</p>
                <p className="text-slate-300">
                  Rolled back to:{' '}
                  <span className="font-mono" data-testid="rolled-back-to">
                    {String(rollbackResult.rolled_back_to ?? '—')}
                  </span>
                </p>
              </div>
            )}
          </section>
        </div>
      )}

      {/* ── Per-flow audit section ── */}
      {activeSection === 'audit' && (
        <div data-testid="audit-section">
          <form onSubmit={handleLoadAudit} className="mb-4 flex gap-2" data-testid="audit-form">
            <button
              type="submit"
              disabled={auditLoading || !flowId.trim()}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="load-audit-btn"
            >
              {auditLoading ? 'Loading…' : 'Load Audit'}
            </button>
          </form>
          {auditError && (
            <p className="mb-3 text-sm text-red-400" data-testid="audit-error">
              {auditError}
            </p>
          )}
          {!auditLoading && auditEntries.length === 0 && !auditError && (
            <p className="text-xs text-slate-500" data-testid="no-audit">
              No rollback history for this flow.
            </p>
          )}
          {renderAuditTable(auditEntries, 'audit')}
        </div>
      )}

      {/* ── Global audit section ── */}
      {activeSection === 'global-audit' && (
        <div data-testid="global-audit-section">
          <button
            onClick={handleLoadGlobal}
            disabled={globalLoading}
            className="mb-4 rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
            data-testid="load-global-btn"
          >
            {globalLoading ? 'Loading…' : 'Load Global History'}
          </button>
          {globalError && (
            <p className="mb-3 text-sm text-red-400" data-testid="global-error">
              {globalError}
            </p>
          )}
          {!globalLoading && globalEntries.length === 0 && !globalError && (
            <p className="text-xs text-slate-500" data-testid="no-global">
              No global rollback history.
            </p>
          )}
          {renderAuditTable(globalEntries, 'global')}
        </div>
      )}
    </MainLayout>
  );
};

export default FlowVersionsPage;
