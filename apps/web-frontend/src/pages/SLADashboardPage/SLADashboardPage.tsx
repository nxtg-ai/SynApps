/**
 * SLADashboardPage -- Workflow execution SLA tracking dashboard.
 *
 * Shows:
 *   - Compliance rate as a big percentage (green >= 95%, yellow >= 80%, red < 80%)
 *   - Summary cards: Total Runs, Violations, Compliance Rate
 *   - Violations table: flow name, run id, actual duration, max duration, % over, timestamp
 *   - Policy management section with inline edit and delete
 *
 * Route: /sla (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ComplianceStats {
  total_runs: number;
  violations: number;
  compliance_rate_pct: number;
  by_flow: Array<{ flow_id: string; violations: number }>;
}

interface SLAViolation {
  violation_id: string;
  policy_id: string;
  flow_id: string;
  run_id: string;
  actual_duration_seconds: number;
  max_duration_seconds: number;
  pct_over: number;
  created_at: number;
}

interface SLAPolicy {
  policy_id: string;
  flow_id: string;
  owner_id: string;
  max_duration_seconds: number;
  alert_threshold_pct: number;
  created_at: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string; REACT_APP_API_URL?: string } }).env
      ?.VITE_API_URL ||
    (import.meta as unknown as { env?: { REACT_APP_API_URL?: string } }).env?.REACT_APP_API_URL ||
    'http://localhost:8000'
  );
}

function getAuthToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options?.headers ?? {}),
  };
  const resp = await fetch(`${getBaseUrl()}${path}`, { ...options, headers });
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}: ${resp.statusText}`);
  }
  if (resp.status === 204) return undefined as unknown as T;
  return resp.json();
}

function formatDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function formatTimestamp(epoch: number): string {
  return new Date(epoch * 1000).toLocaleString();
}

function truncateId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 12)}...` : id;
}

function complianceColor(rate: number): string {
  if (rate >= 95) return 'text-green-500';
  if (rate >= 80) return 'text-yellow-500';
  return 'text-red-500';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const SLADashboardPage: React.FC = () => {
  const [stats, setStats] = useState<ComplianceStats | null>(null);
  const [violations, setViolations] = useState<SLAViolation[]>([]);
  const [policies, setPolicies] = useState<SLAPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingFlowId, setEditingFlowId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashboardData, violationsData, policiesData] = await Promise.all([
        apiFetch<ComplianceStats>('/api/v1/sla/dashboard'),
        apiFetch<SLAViolation[]>('/api/v1/sla/violations?limit=20'),
        apiFetch<SLAPolicy[]>('/api/v1/sla/policies'),
      ]);
      setStats(dashboardData);
      setViolations(violationsData);
      setPolicies(policiesData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load SLA data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSavePolicy = async (flowId: string) => {
    const maxDuration = parseFloat(editValue);
    if (isNaN(maxDuration) || maxDuration <= 0) return;
    await apiFetch(`/api/v1/sla/policies/${flowId}`, {
      method: 'PUT',
      body: JSON.stringify({ max_duration_seconds: maxDuration }),
    });
    setEditingFlowId(null);
    setEditValue('');
    await loadData();
  };

  const handleDeletePolicy = async (flowId: string) => {
    await apiFetch(`/api/v1/sla/policies/${flowId}`, { method: 'DELETE' });
    await loadData();
  };

  const handleStartEdit = (policy: SLAPolicy) => {
    setEditingFlowId(policy.flow_id);
    setEditValue(String(policy.max_duration_seconds));
  };

  if (loading) {
    return (
      <MainLayout title="SLA Dashboard">
        <div className="flex items-center justify-center min-h-[200px]" aria-label="Loading SLA data">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      </MainLayout>
    );
  }

  if (error) {
    return (
      <MainLayout title="SLA Dashboard">
        <div role="alert" className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          Error loading SLA data: {error}
        </div>
      </MainLayout>
    );
  }

  const rate = stats?.compliance_rate_pct ?? 100;

  return (
    <MainLayout title="SLA Dashboard">
      <div className="space-y-6">
        {/* Compliance Rate Hero */}
        <div className="text-center py-8">
          <div
            data-testid="compliance-rate"
            className={`text-6xl font-bold ${complianceColor(rate)}`}
          >
            {rate.toFixed(1)}%
          </div>
          <div className="text-gray-500 mt-2">Overall Compliance Rate</div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white rounded-lg shadow p-4 text-center">
            <div className="text-2xl font-semibold" data-testid="total-runs">
              {stats?.total_runs ?? 0}
            </div>
            <div className="text-gray-500 text-sm">Total Runs</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4 text-center">
            <div className="text-2xl font-semibold text-red-500" data-testid="total-violations">
              {stats?.violations ?? 0}
            </div>
            <div className="text-gray-500 text-sm">Violations</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4 text-center">
            <div className={`text-2xl font-semibold ${complianceColor(rate)}`}>
              {rate.toFixed(1)}%
            </div>
            <div className="text-gray-500 text-sm">Compliance Rate</div>
          </div>
        </div>

        {/* Violations Table */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-4 py-3 border-b">
            <h2 className="text-lg font-semibold">Recent Violations</h2>
          </div>
          {violations.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-400">
              No violations recorded
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left">Flow ID</th>
                    <th className="px-4 py-2 text-left">Run ID</th>
                    <th className="px-4 py-2 text-right">Actual</th>
                    <th className="px-4 py-2 text-right">Max</th>
                    <th className="px-4 py-2 text-right">% Over</th>
                    <th className="px-4 py-2 text-left">Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {violations.map((v) => (
                    <tr key={v.violation_id} className="border-t hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono text-xs">{truncateId(v.flow_id)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{truncateId(v.run_id)}</td>
                      <td className="px-4 py-2 text-right">{formatDuration(v.actual_duration_seconds)}</td>
                      <td className="px-4 py-2 text-right">{formatDuration(v.max_duration_seconds)}</td>
                      <td className="px-4 py-2 text-right text-red-500">{v.pct_over.toFixed(1)}%</td>
                      <td className="px-4 py-2 text-gray-500">{formatTimestamp(v.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Manage SLA Policies */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-4 py-3 border-b">
            <h2 className="text-lg font-semibold">Manage SLA Policies</h2>
          </div>
          {policies.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-400">
              No SLA policies configured
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left">Flow ID</th>
                    <th className="px-4 py-2 text-right">Max Duration (s)</th>
                    <th className="px-4 py-2 text-right">Alert Threshold</th>
                    <th className="px-4 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {policies.map((p) => (
                    <tr key={p.policy_id} className="border-t hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono text-xs">{truncateId(p.flow_id)}</td>
                      <td className="px-4 py-2 text-right">
                        {editingFlowId === p.flow_id ? (
                          <input
                            type="number"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            className="w-24 border rounded px-2 py-1 text-right"
                            aria-label="Max duration seconds"
                            min="0.1"
                            step="0.1"
                          />
                        ) : (
                          p.max_duration_seconds
                        )}
                      </td>
                      <td className="px-4 py-2 text-right">
                        {(p.alert_threshold_pct * 100).toFixed(0)}%
                      </td>
                      <td className="px-4 py-2 text-right space-x-2">
                        {editingFlowId === p.flow_id ? (
                          <button
                            onClick={() => handleSavePolicy(p.flow_id)}
                            className="text-green-600 hover:text-green-800 text-xs font-medium"
                          >
                            Save
                          </button>
                        ) : (
                          <button
                            onClick={() => handleStartEdit(p)}
                            className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                          >
                            Edit
                          </button>
                        )}
                        <button
                          onClick={() => handleDeletePolicy(p.flow_id)}
                          className="text-red-600 hover:text-red-800 text-xs font-medium"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </MainLayout>
  );
};

export default SLADashboardPage;
