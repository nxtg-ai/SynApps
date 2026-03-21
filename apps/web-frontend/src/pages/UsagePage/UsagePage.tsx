/**
 * UsagePage — API Usage & Execution Quota Dashboard (N-80).
 *
 * Wraps:
 *   GET /api/v1/usage/me  → user's execution quota status
 *   GET /api/v1/usage     → all consumer API key usage (admin)
 *
 * Route: /usage (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface QuotaStatus {
  user: string;
  executions_this_hour: number;
  hourly_limit: number;
  hourly_remaining: number;
  hourly_reset_in_seconds: number;
  executions_this_month: number;
  monthly_limit: number;
  monthly_remaining: number;
  month: string;
}

interface ConsumerUsage {
  key_id: string;
  requests_today: number;
  requests_week: number;
  requests_month: number;
  errors_month: number;
  bandwidth_bytes: number;
  error_rate_pct?: number;
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

function pct(used: number, limit: number): number {
  if (limit === 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

function barColor(p: number): string {
  if (p >= 90) return 'bg-red-600';
  if (p >= 70) return 'bg-yellow-600';
  return 'bg-emerald-600';
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

// ---------------------------------------------------------------------------
// QuotaCard
// ---------------------------------------------------------------------------

interface QuotaBarProps {
  label: string;
  used: number;
  limit: number;
  remaining: number;
  suffix?: string;
  testId: string;
}

const QuotaBar: React.FC<QuotaBarProps> = ({ label, used, limit, remaining, suffix = '', testId }) => {
  const p = pct(used, limit);
  return (
    <div className="mb-4" data-testid={testId}>
      <div className="mb-1 flex justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span>
          {used.toLocaleString()} / {limit.toLocaleString()}{suffix}
          {' '}
          <span className="text-slate-500">({remaining.toLocaleString()} remaining)</span>
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded bg-slate-700" data-testid="quota-bar-track">
        <div
          className={`h-2 rounded transition-all ${barColor(p)}`}
          style={{ width: `${p}%` }}
          data-testid="quota-bar-fill"
        />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const UsagePage: React.FC = () => {
  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  const [allUsage, setAllUsage] = useState<ConsumerUsage[]>([]);
  const [loadingQuota, setLoadingQuota] = useState(false);
  const [loadingAll, setLoadingAll] = useState(false);
  const [errorQuota, setErrorQuota] = useState<string | null>(null);
  const [errorAll, setErrorAll] = useState<string | null>(null);

  const loadQuota = useCallback(async () => {
    setLoadingQuota(true);
    setErrorQuota(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/usage/me`, { headers: authHeaders() });
      if (!resp.ok) {
        setErrorQuota(`Failed to load quota (${resp.status})`);
        return;
      }
      setQuota(await resp.json());
    } catch {
      setErrorQuota('Network error loading quota');
    } finally {
      setLoadingQuota(false);
    }
  }, []);

  const loadAllUsage = useCallback(async () => {
    setLoadingAll(true);
    setErrorAll(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/usage`, { headers: authHeaders() });
      if (!resp.ok) {
        setErrorAll(`Failed to load usage (${resp.status})`);
        return;
      }
      const data: ConsumerUsage[] = await resp.json();
      setAllUsage(data);
    } catch {
      setErrorAll('Network error loading usage');
    } finally {
      setLoadingAll(false);
    }
  }, []);

  useEffect(() => {
    loadQuota();
    loadAllUsage();
  }, [loadQuota, loadAllUsage]);

  const handleRefresh = useCallback(() => {
    loadQuota();
    loadAllUsage();
  }, [loadQuota, loadAllUsage]);

  return (
    <MainLayout title="Usage & Quota">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Usage &amp; Quota
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Execution quota status and API key usage statistics.
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={loadingQuota || loadingAll}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* My Quota */}
      <section
        className="mb-6 rounded border border-slate-700 bg-slate-800/40 p-5"
        data-testid="my-quota-section"
      >
        <p className="mb-4 text-sm font-semibold text-slate-300">My Execution Quota</p>

        {errorQuota && (
          <p className="mb-3 text-sm text-red-400" data-testid="quota-error">{errorQuota}</p>
        )}

        {loadingQuota && !quota && (
          <p className="text-xs text-slate-500" data-testid="quota-loading">Loading…</p>
        )}

        {quota && (
          <div data-testid="quota-panel">
            <p className="mb-3 text-xs text-slate-400">
              User: <span className="text-slate-300">{quota.user}</span>
              {' · '}
              Month: <span className="text-slate-300">{quota.month}</span>
              {' · '}
              Hourly reset in: <span className="text-slate-300">{formatSeconds(quota.hourly_reset_in_seconds)}</span>
            </p>
            <QuotaBar
              label="This Hour"
              used={quota.executions_this_hour}
              limit={quota.hourly_limit}
              remaining={quota.hourly_remaining}
              suffix=" executions"
              testId="hourly-bar"
            />
            <QuotaBar
              label="This Month"
              used={quota.executions_this_month}
              limit={quota.monthly_limit}
              remaining={quota.monthly_remaining}
              suffix=" executions"
              testId="monthly-bar"
            />
          </div>
        )}
      </section>

      {/* All Consumer Usage */}
      <section
        className="rounded border border-slate-700 bg-slate-800/40 p-5"
        data-testid="all-usage-section"
      >
        <p className="mb-4 text-sm font-semibold text-slate-300">
          API Key Usage
          {allUsage.length > 0 && (
            <span className="ml-2 text-xs text-slate-500">({allUsage.length} consumers)</span>
          )}
        </p>

        {errorAll && (
          <p className="mb-3 text-sm text-red-400" data-testid="all-usage-error">{errorAll}</p>
        )}

        {!loadingAll && allUsage.length === 0 && !errorAll && (
          <p className="text-xs text-slate-500" data-testid="no-usage">
            No API key usage recorded yet.
          </p>
        )}

        {allUsage.length > 0 && (
          <div className="overflow-x-auto" data-testid="usage-table">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700 text-left text-slate-500">
                  <th className="pb-2 pr-4 font-medium">Consumer</th>
                  <th className="pb-2 pr-4 font-medium">Today</th>
                  <th className="pb-2 pr-4 font-medium">Week</th>
                  <th className="pb-2 pr-4 font-medium">Month</th>
                  <th className="pb-2 pr-4 font-medium">Errors</th>
                  <th className="pb-2 font-medium">Bandwidth</th>
                </tr>
              </thead>
              <tbody>
                {allUsage.map((u) => (
                  <tr
                    key={u.key_id}
                    className="border-b border-slate-700/40"
                    data-testid="usage-row"
                  >
                    <td className="py-1.5 pr-4 font-mono text-slate-300">{u.key_id}</td>
                    <td className="py-1.5 pr-4 text-slate-300">{u.requests_today.toLocaleString()}</td>
                    <td className="py-1.5 pr-4 text-slate-300">{u.requests_week.toLocaleString()}</td>
                    <td className="py-1.5 pr-4 text-slate-300">{u.requests_month.toLocaleString()}</td>
                    <td className="py-1.5 pr-4">
                      <span className={u.errors_month > 0 ? 'text-red-400' : 'text-slate-400'}>
                        {u.errors_month}
                      </span>
                    </td>
                    <td className="py-1.5 text-slate-400">{formatBytes(u.bandwidth_bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </MainLayout>
  );
};

export default UsagePage;
