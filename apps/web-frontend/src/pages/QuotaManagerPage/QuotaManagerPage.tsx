/**
 * QuotaManagerPage — API Key Quota Administration (N-87).
 *
 * Wraps:
 *   GET /api/v1/quotas               → all keys with usage vs quota
 *   PUT /api/v1/quotas/{key_id}      → set or clear monthly limit
 *
 * Route: /quota-manager (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface QuotaEntry {
  key_id: string;
  requests_this_month?: number;
  monthly_limit?: number | null;
  pct_consumed?: number;
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

function pctBar(pct: number): string {
  if (pct >= 90) return 'bg-red-600';
  if (pct >= 70) return 'bg-yellow-600';
  return 'bg-emerald-600';
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const QuotaManagerPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quotas, setQuotas] = useState<QuotaEntry[]>([]);

  // Inline edit state
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const loadQuotas = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/quotas`, { headers: authHeaders() });
      if (!resp.ok) {
        setError(`Failed to load quotas (${resp.status})`);
        return;
      }
      const data = await resp.json();
      // Backend may return array or object with keys
      const entries: QuotaEntry[] = Array.isArray(data)
        ? data
        : Object.entries(data).map(([key_id, v]) =>
            typeof v === 'object' && v !== null
              ? { key_id, ...(v as Record<string, unknown>) }
              : { key_id },
          );
      setQuotas(entries);
    } catch {
      setError('Network error loading quotas');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQuotas();
  }, [loadQuotas]);

  const startEdit = useCallback((entry: QuotaEntry) => {
    setEditingKey(entry.key_id);
    setEditValue(entry.monthly_limit != null ? String(entry.monthly_limit) : '');
    setSaveError(null);
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingKey(null);
    setEditValue('');
    setSaveError(null);
  }, []);

  const handleSave = useCallback(
    async (keyId: string) => {
      setSaving(true);
      setSaveError(null);
      const monthly_limit = editValue.trim() === '' ? null : Number(editValue.trim());
      if (editValue.trim() !== '' && (isNaN(monthly_limit!) || monthly_limit! < 1)) {
        setSaveError('Limit must be a positive integer or empty to clear.');
        setSaving(false);
        return;
      }
      try {
        const resp = await fetch(`${getBaseUrl()}/quotas/${encodeURIComponent(keyId)}`, {
          method: 'PUT',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ monthly_limit }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setSaveError(data.detail ?? `Error ${resp.status}`);
          return;
        }
        // Update local state
        setQuotas((prev) =>
          prev.map((q) =>
            q.key_id === keyId ? { ...q, monthly_limit } : q,
          ),
        );
        setEditingKey(null);
        setEditValue('');
      } catch {
        setSaveError('Network error');
      } finally {
        setSaving(false);
      }
    },
    [editValue],
  );

  return (
    <MainLayout title="Quota Manager">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Quota Manager
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            View and set monthly request quotas for API keys.
          </p>
        </div>
        <button
          onClick={loadQuotas}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="quotas-error">{error}</p>
      )}

      {loading && quotas.length === 0 && (
        <p className="text-xs text-slate-500" data-testid="quotas-loading">Loading…</p>
      )}

      {!loading && quotas.length === 0 && !error && (
        <p className="text-xs text-slate-500" data-testid="no-quotas">
          No quota records found.
        </p>
      )}

      {quotas.length > 0 && (
        <div className="overflow-x-auto" data-testid="quotas-table">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-500">
                <th className="pb-2 pr-4 font-medium">Key ID</th>
                <th className="pb-2 pr-4 font-medium">This Month</th>
                <th className="pb-2 pr-4 font-medium">Monthly Limit</th>
                <th className="pb-2 pr-4 font-medium">Usage</th>
                <th className="pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {quotas.map((q) => {
                const pct =
                  q.pct_consumed != null
                    ? q.pct_consumed
                    : q.monthly_limit && q.requests_this_month != null
                      ? Math.min(100, Math.round((q.requests_this_month / q.monthly_limit) * 100))
                      : null;

                return (
                  <tr
                    key={q.key_id}
                    className="border-b border-slate-700/40"
                    data-testid="quota-row"
                  >
                    <td className="py-2 pr-4 font-mono text-slate-300">{q.key_id}</td>
                    <td className="py-2 pr-4 text-slate-300">
                      {q.requests_this_month?.toLocaleString() ?? '—'}
                    </td>
                    <td className="py-2 pr-4">
                      {editingKey === q.key_id ? (
                        <input
                          type="number"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          placeholder="unlimited"
                          className="w-28 rounded border border-slate-600 bg-slate-900 px-2 py-0.5 text-xs text-slate-200 focus:outline-none"
                          data-testid="limit-input"
                        />
                      ) : (
                        <span className={q.monthly_limit == null ? 'text-slate-500' : 'text-slate-300'}>
                          {q.monthly_limit != null ? q.monthly_limit.toLocaleString() : 'unlimited'}
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      {pct != null ? (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-24 overflow-hidden rounded bg-slate-700">
                            <div
                              className={`h-1.5 rounded ${pctBar(pct)}`}
                              style={{ width: `${pct}%` }}
                              data-testid="usage-bar"
                            />
                          </div>
                          <span className="text-slate-400">{pct}%</span>
                        </div>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="py-2">
                      {editingKey === q.key_id ? (
                        <div className="flex gap-1">
                          <button
                            onClick={() => handleSave(q.key_id)}
                            disabled={saving}
                            className="rounded bg-indigo-700 px-2 py-0.5 text-xs text-white hover:bg-indigo-600 disabled:opacity-50"
                            data-testid="save-btn"
                          >
                            {saving ? 'Saving…' : 'Save'}
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-600"
                            data-testid="cancel-btn"
                          >
                            Cancel
                          </button>
                          {saveError && (
                            <span className="ml-1 text-xs text-red-400" data-testid="save-error">
                              {saveError}
                            </span>
                          )}
                        </div>
                      ) : (
                        <button
                          onClick={() => startEdit(q)}
                          className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-600"
                          data-testid="edit-btn"
                        >
                          Set Limit
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </MainLayout>
  );
};

export default QuotaManagerPage;
