/**
 * WorkflowPermissionsPage — Workflow Team Access Control (N-82).
 *
 * Wraps:
 *   GET  /api/v1/workflows/{flow_id}/permissions  → ownership + grants
 *   POST /api/v1/workflows/{flow_id}/share        → grant viewer/editor
 *   DELETE /api/v1/workflows/{flow_id}/share/{user_id} → revoke
 *
 * Route: /workflow-permissions (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PermissionGrant {
  user_id: string;
  role: 'viewer' | 'editor';
}

interface PermissionsResponse {
  flow_id: string;
  permissions: {
    owner?: string;
    grants?: PermissionGrant[];
    [key: string]: unknown;
  };
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

function roleBadgeClass(role: string): string {
  return role === 'editor'
    ? 'rounded px-1.5 py-0.5 text-xs bg-indigo-900/60 text-indigo-300'
    : 'rounded px-1.5 py-0.5 text-xs bg-slate-700/60 text-slate-400';
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const WorkflowPermissionsPage: React.FC = () => {
  // Flow selector
  const [flowId, setFlowId] = useState('');
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);

  // Permissions state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [perms, setPerms] = useState<PermissionsResponse | null>(null);

  // Share form
  const [shareUserId, setShareUserId] = useState('');
  const [shareRole, setShareRole] = useState<'viewer' | 'editor'>('viewer');
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [shareSuccess, setShareSuccess] = useState<string | null>(null);

  // Revoke
  const [revoking, setRevoking] = useState<string | null>(null);

  const loadPermissions = useCallback(async (fid: string) => {
    setLoading(true);
    setError(null);
    setPerms(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/workflows/${fid}/permissions`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(`Failed to load permissions (${resp.status})`);
        return;
      }
      setPerms(await resp.json());
    } catch {
      setError('Network error loading permissions');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleLoadFlow = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim()) return;
      setActiveFlowId(flowId.trim());
      loadPermissions(flowId.trim());
    },
    [flowId, loadPermissions],
  );

  const handleShare = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!activeFlowId || !shareUserId.trim()) return;
      setSharing(true);
      setShareError(null);
      setShareSuccess(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/workflows/${activeFlowId}/share`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: shareUserId.trim(), role: shareRole }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setShareError(data.detail ?? `Error ${resp.status}`);
          return;
        }
        const data = await resp.json();
        setShareSuccess(`Granted ${shareRole} to ${shareUserId.trim()}`);
        setShareUserId('');
        // Refresh permissions from response
        if (data.permissions) {
          setPerms((prev) =>
            prev ? { ...prev, permissions: data.permissions } : prev,
          );
        } else {
          loadPermissions(activeFlowId);
        }
      } catch {
        setShareError('Network error');
      } finally {
        setSharing(false);
      }
    },
    [activeFlowId, shareUserId, shareRole, loadPermissions],
  );

  const handleRevoke = useCallback(
    async (targetUserId: string) => {
      if (!activeFlowId) return;
      setRevoking(targetUserId);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/workflows/${activeFlowId}/share/${encodeURIComponent(targetUserId)}`,
          { method: 'DELETE', headers: authHeaders() },
        );
        if (!resp.ok) {
          return;
        }
        const data = await resp.json();
        if (data.permissions) {
          setPerms((prev) =>
            prev ? { ...prev, permissions: data.permissions } : prev,
          );
        } else {
          loadPermissions(activeFlowId);
        }
      } catch {
        // network error — silent; UI remains unchanged
      } finally {
        setRevoking(null);
      }
    },
    [activeFlowId, loadPermissions],
  );

  const grants: PermissionGrant[] = perms?.permissions?.grants ?? [];

  return (
    <MainLayout title="Workflow Permissions">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Workflow Permissions
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Manage team access — grant and revoke viewer or editor roles.
        </p>
      </div>

      {/* Flow selector */}
      <form onSubmit={handleLoadFlow} className="mb-6 flex gap-2" data-testid="flow-selector-form">
        <input
          type="text"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          placeholder="Workflow / Flow ID"
          className="flex-1 rounded border border-slate-600 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          data-testid="flow-id-input"
        />
        <button
          type="submit"
          disabled={!flowId.trim() || loading}
          className="rounded bg-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="load-flow-btn"
        >
          Load
        </button>
      </form>

      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="perms-error">{error}</p>
      )}

      {!activeFlowId && !loading && (
        <p className="text-xs text-slate-500" data-testid="no-flow-state">
          Enter a workflow ID to view and manage its permissions.
        </p>
      )}

      {perms && (
        <div data-testid="perms-panel">
          {/* Ownership */}
          {perms.permissions.owner && (
            <div className="mb-4 flex items-center gap-2 text-xs text-slate-400" data-testid="owner-row">
              <span>Owner:</span>
              <span className="font-mono text-slate-300">{perms.permissions.owner}</span>
              <span className="rounded bg-amber-900/50 px-1.5 py-0.5 text-xs text-amber-300">owner</span>
            </div>
          )}

          {/* Grants table */}
          {grants.length > 0 ? (
            <div className="mb-6 overflow-x-auto" data-testid="grants-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">User</th>
                    <th className="pb-2 pr-4 font-medium">Role</th>
                    <th className="pb-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {grants.map((g) => (
                    <tr
                      key={g.user_id}
                      className="border-b border-slate-700/40"
                      data-testid="grant-row"
                    >
                      <td className="py-1.5 pr-4 font-mono text-slate-300">{g.user_id}</td>
                      <td className="py-1.5 pr-4">
                        <span className={roleBadgeClass(g.role)} data-testid="role-badge">
                          {g.role}
                        </span>
                      </td>
                      <td className="py-1.5">
                        <button
                          onClick={() => handleRevoke(g.user_id)}
                          disabled={revoking === g.user_id}
                          className="rounded bg-red-900/40 px-2 py-0.5 text-xs text-red-400 hover:bg-red-900/70 disabled:opacity-50"
                          data-testid="revoke-btn"
                        >
                          {revoking === g.user_id ? 'Revoking…' : 'Revoke'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mb-6 text-xs text-slate-500" data-testid="no-grants">
              No grants — only the owner has access.
            </p>
          )}

          {/* Share form */}
          <section
            className="rounded border border-slate-700 bg-slate-800/40 p-5"
            data-testid="share-section"
          >
            <p className="mb-4 text-sm font-semibold text-slate-300">Grant Access</p>

            {shareError && (
              <p className="mb-3 text-sm text-red-400" data-testid="share-error">{shareError}</p>
            )}
            {shareSuccess && (
              <p className="mb-3 text-sm text-emerald-400" data-testid="share-success">{shareSuccess}</p>
            )}

            <form onSubmit={handleShare} className="flex gap-2" data-testid="share-form">
              <input
                type="text"
                value={shareUserId}
                onChange={(e) => setShareUserId(e.target.value)}
                placeholder="User ID or email"
                className="flex-1 rounded border border-slate-600 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
                data-testid="share-user-input"
              />
              <select
                value={shareRole}
                onChange={(e) => setShareRole(e.target.value as 'viewer' | 'editor')}
                className="rounded border border-slate-600 bg-slate-900 px-2 py-2 text-xs text-slate-300 focus:outline-none"
                data-testid="share-role-select"
              >
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
              <button
                type="submit"
                disabled={sharing || !shareUserId.trim()}
                className="rounded bg-indigo-700 px-4 py-2 text-xs text-white hover:bg-indigo-600 disabled:opacity-50"
                data-testid="share-btn"
              >
                {sharing ? 'Sharing…' : 'Share'}
              </button>
            </form>
          </section>
        </div>
      )}
    </MainLayout>
  );
};

export default WorkflowPermissionsPage;
