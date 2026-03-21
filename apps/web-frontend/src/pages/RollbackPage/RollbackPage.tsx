/**
 * RollbackPage — One-click rollback to a previous workflow version
 * with full audit log of all past rollbacks.
 *
 * Route: /workflows/:id/rollback
 */
import React, { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import MainLayout from '../../components/Layout/MainLayout';
import { apiService } from '../../services/ApiService';
import { FlowVersion, RollbackAuditEntry } from '../../types';

const RollbackPage: React.FC = () => {
  const { id: flowId } = useParams<{ id: string }>();

  const [versions, setVersions] = useState<FlowVersion[]>([]);
  const [auditEntries, setAuditEntries] = useState<RollbackAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Confirmation modal state
  const [confirmVersionId, setConfirmVersionId] = useState<string | null>(null);
  const [confirmVersionNumber, setConfirmVersionNumber] = useState<number | null>(null);
  const [reason, setReason] = useState('');

  const fetchData = useCallback(async () => {
    if (!flowId) return;
    setLoading(true);
    setError(null);
    try {
      const [versionRes, historyRes] = await Promise.all([
        apiService.getFlowVersions(flowId),
        apiService.getRollbackHistory(flowId),
      ]);
      setVersions(versionRes.items);
      setAuditEntries(historyRes.items);
    } catch {
      setError('Failed to load rollback data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [flowId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRollback = async () => {
    if (!flowId || !confirmVersionId) return;
    try {
      await apiService.rollbackFlow(flowId, confirmVersionId, reason);
      setSuccessMessage(`Rolled back to v${confirmVersionNumber}!`);
      setConfirmVersionId(null);
      setConfirmVersionNumber(null);
      setReason('');
      await fetchData();
    } catch {
      setError('Rollback failed. Please try again.');
    }
  };

  const openConfirmModal = (versionId: string, versionNumber: number) => {
    setConfirmVersionId(versionId);
    setConfirmVersionNumber(versionNumber);
    setReason('');
    setSuccessMessage(null);
  };

  const closeConfirmModal = () => {
    setConfirmVersionId(null);
    setConfirmVersionNumber(null);
    setReason('');
  };

  const formatTimestamp = (ts: string | number): string => {
    const date = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
    return date.toLocaleString();
  };

  return (
    <MainLayout title="Workflow Rollback">
      <div data-testid="rollback-page" className="mx-auto max-w-5xl p-6 text-slate-100">
        <h1 className="mb-6 text-2xl font-bold">Workflow Rollback</h1>

        {loading && (
          <div aria-label="Loading rollback data" className="text-slate-400">
            Loading...
          </div>
        )}

        {error && (
          <div data-testid="error-banner" className="mb-4 rounded bg-red-900/50 p-3 text-red-300">
            {error}
          </div>
        )}

        {successMessage && (
          <div
            data-testid="success-banner"
            className="mb-4 rounded bg-green-900/50 p-3 text-green-300"
          >
            {successMessage}
          </div>
        )}

        {!loading && !error && (
          <>
            {/* Version Timeline */}
            <section className="mb-8">
              <h2 className="mb-4 text-lg font-semibold">Version Timeline</h2>
              {versions.length === 0 ? (
                <p className="text-slate-400">No versions available.</p>
              ) : (
                <div className="space-y-2">
                  {versions.map((v) => (
                    <div
                      key={v.version_id}
                      data-testid={`version-row-${v.version_id}`}
                      className="flex items-center justify-between rounded border border-slate-700 bg-slate-800/50 p-4"
                    >
                      <div>
                        <span className="font-medium">v{v.version}</span>
                        <span className="ml-4 text-sm text-slate-400">
                          {formatTimestamp(v.snapshotted_at)}
                        </span>
                      </div>
                      <button
                        data-testid={`rollback-button-${v.version_id}`}
                        onClick={() => openConfirmModal(v.version_id, v.version)}
                        className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500"
                      >
                        Rollback to this version
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Rollback Audit Log */}
            <section>
              <h2 className="mb-4 text-lg font-semibold">Rollback Audit Log</h2>
              {auditEntries.length === 0 ? (
                <p data-testid="empty-audit-log" className="text-slate-400">
                  No rollbacks recorded yet.
                </p>
              ) : (
                <table
                  data-testid="audit-log-table"
                  className="w-full text-left text-sm"
                >
                  <thead className="border-b border-slate-700 text-slate-400">
                    <tr>
                      <th className="pb-2 pr-4">From Version</th>
                      <th className="pb-2 pr-4">To Version</th>
                      <th className="pb-2 pr-4">Performed By</th>
                      <th className="pb-2 pr-4">When</th>
                      <th className="pb-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditEntries.map((entry) => (
                      <tr key={entry.audit_id} className="border-b border-slate-800">
                        <td className="py-2 pr-4">{entry.from_version_id.slice(0, 8)}</td>
                        <td className="py-2 pr-4">{entry.to_version_id.slice(0, 8)}</td>
                        <td className="py-2 pr-4">{entry.performed_by}</td>
                        <td className="py-2 pr-4">{formatTimestamp(entry.rolled_back_at)}</td>
                        <td className="py-2">{entry.reason || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}

        {/* Confirmation Modal */}
        {confirmVersionId && (
          <div
            data-testid="confirm-rollback-modal"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          >
            <div className="w-full max-w-md rounded-lg bg-slate-800 p-6 shadow-xl">
              <h3 className="mb-4 text-lg font-semibold text-slate-100">
                Confirm Rollback to v{confirmVersionNumber}
              </h3>
              <label className="mb-1 block text-sm text-slate-300" htmlFor="rollback-reason">
                Reason (optional)
              </label>
              <textarea
                id="rollback-reason"
                data-testid="rollback-reason-textarea"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="mb-4 w-full rounded border border-slate-600 bg-slate-900 p-2 text-sm text-slate-100 placeholder-slate-500"
                placeholder="Why are you rolling back?"
                rows={3}
              />
              <div className="flex justify-end gap-3">
                <button
                  onClick={closeConfirmModal}
                  className="rounded px-4 py-2 text-sm text-slate-300 hover:text-slate-100"
                >
                  Cancel
                </button>
                <button
                  data-testid="confirm-rollback-button"
                  onClick={handleRollback}
                  className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500"
                >
                  Confirm Rollback
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </MainLayout>
  );
};

export default RollbackPage;
