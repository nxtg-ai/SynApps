/**
 * AnalyticsDashboard — N-33 Workflow Analytics Dashboard
 *
 * Displays execution insights: top workflows, avg node durations,
 * hourly error rate trends, and peak usage hours.
 */

import { useEffect, useState } from 'react';
import apiService from '../../services/ApiService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TopWorkflow {
  flow_id: string;
  run_count: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  error_rate: number;
  avg_duration_seconds: number | null;
}

interface NodeTypeDuration {
  node_type: string;
  avg_duration_ms: number;
  sample_count: number;
}

interface HourlyTrend {
  hour_label: string;
  total: number;
  errors: number;
  error_rate: number;
}

interface PeakHour {
  hour: number;
  execution_count: number;
}

interface DashboardData {
  top_workflows: TopWorkflow[];
  avg_duration_by_node_type: NodeTypeDuration[];
  error_rate_trends: HourlyTrend[];
  peak_usage_hours: PeakHour[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function ms(value: number | null): string {
  if (value === null || value === undefined) return '—';
  if (value < 1000) return `${value.toFixed(0)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

function bar(value: number, max: number, width = 80): string {
  if (max === 0) return '';
  const filled = Math.round((value / max) * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AnalyticsDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchDashboard() {
      try {
        const resp = await apiService['api'].get('/api/v1/analytics/dashboard');
        setData(resp.data as DashboardData);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load analytics');
      } finally {
        setLoading(false);
      }
    }
    fetchDashboard();
  }, []);

  const handleExportCsv = () => {
    window.open('/api/v1/analytics/dashboard/export.csv', '_blank');
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">
        Loading analytics…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-red-400">
        {error ?? 'No data available'}
      </div>
    );
  }

  const maxPeak = Math.max(...data.peak_usage_hours.map((h) => h.execution_count), 1);

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Analytics Dashboard</h1>
            <p className="mt-1 text-sm text-slate-400">Execution insights across all workflows</p>
          </div>
          <button
            onClick={handleExportCsv}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 focus:outline-none"
          >
            Export CSV
          </button>
        </div>

        {/* Top Workflows */}
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-200">Top Workflows by Executions</h2>
          {data.top_workflows.length === 0 ? (
            <p className="text-sm text-slate-500">No workflow runs yet.</p>
          ) : (
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-900 text-left text-xs uppercase text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Flow ID</th>
                    <th className="px-4 py-3 text-right">Runs</th>
                    <th className="px-4 py-3 text-right">Success</th>
                    <th className="px-4 py-3 text-right">Errors</th>
                    <th className="px-4 py-3 text-right">Success Rate</th>
                    <th className="px-4 py-3 text-right">Avg Duration</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {data.top_workflows.map((wf) => (
                    <tr key={wf.flow_id} className="bg-slate-950 hover:bg-slate-900/50">
                      <td className="px-4 py-3 font-mono text-xs text-slate-300">{wf.flow_id}</td>
                      <td className="px-4 py-3 text-right text-slate-200">{wf.run_count}</td>
                      <td className="px-4 py-3 text-right text-emerald-400">{wf.success_count}</td>
                      <td className="px-4 py-3 text-right text-red-400">{wf.error_count}</td>
                      <td className="px-4 py-3 text-right text-slate-300">{pct(wf.success_rate)}</td>
                      <td className="px-4 py-3 text-right text-slate-300">
                        {wf.avg_duration_seconds !== null
                          ? ms((wf.avg_duration_seconds ?? 0) * 1000)
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Avg Duration by Node Type */}
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-200">Avg Execution Duration by Node Type</h2>
          {data.avg_duration_by_node_type.length === 0 ? (
            <p className="text-sm text-slate-500">No node execution data yet.</p>
          ) : (
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-900 text-left text-xs uppercase text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Node Type</th>
                    <th className="px-4 py-3 text-right">Avg Duration</th>
                    <th className="px-4 py-3 text-right">Samples</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {data.avg_duration_by_node_type.map((nd) => (
                    <tr key={nd.node_type} className="bg-slate-950 hover:bg-slate-900/50">
                      <td className="px-4 py-3 font-mono text-xs text-slate-300">{nd.node_type}</td>
                      <td className="px-4 py-3 text-right text-slate-200">{ms(nd.avg_duration_ms)}</td>
                      <td className="px-4 py-3 text-right text-slate-400">{nd.sample_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Error Rate Trends (last 24 h) */}
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-200">Error Rate Trends — Last 24 Hours</h2>
          <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900/50 p-4">
            {data.error_rate_trends.every((h) => h.total === 0) ? (
              <p className="text-sm text-slate-500">No executions in the last 24 hours.</p>
            ) : (
              <div className="space-y-1">
                {data.error_rate_trends.map((h) => (
                  <div key={h.hour_label} className="flex items-center gap-3 text-xs">
                    <span className="w-14 text-right font-mono text-slate-500">
                      {h.hour_label.slice(11)}:00
                    </span>
                    <div className="flex-1">
                      {h.total > 0 ? (
                        <div className="flex gap-0.5">
                          <div
                            className="h-3 rounded-l bg-emerald-500/70"
                            style={{ width: `${((h.total - h.errors) / h.total) * 100}%` }}
                          />
                          {h.errors > 0 && (
                            <div
                              className="h-3 rounded-r bg-red-500/70"
                              style={{ width: `${(h.errors / h.total) * 100}%` }}
                            />
                          )}
                        </div>
                      ) : (
                        <div className="h-3 w-full rounded bg-slate-800" />
                      )}
                    </div>
                    <span className="w-16 text-right text-slate-400">
                      {h.total > 0 ? `${h.errors}/${h.total}` : '—'}
                    </span>
                    <span className="w-10 text-right text-slate-500">
                      {h.total > 0 ? pct(h.error_rate) : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Peak Usage Hours */}
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-200">Peak Usage Hours (UTC)</h2>
          <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900/50 p-4">
            <div className="grid grid-cols-6 gap-2 sm:grid-cols-8 md:grid-cols-12">
              {data.peak_usage_hours.map((h) => (
                <div key={h.hour} className="flex flex-col items-center gap-1">
                  <div className="relative flex h-16 w-full items-end justify-center">
                    <div
                      className="w-full rounded-t bg-indigo-500/70"
                      style={{
                        height: `${maxPeak > 0 ? (h.execution_count / maxPeak) * 100 : 0}%`,
                        minHeight: h.execution_count > 0 ? '4px' : '0',
                      }}
                    />
                  </div>
                  <span className="text-xs font-mono text-slate-500">
                    {String(h.hour).padStart(2, '0')}
                  </span>
                  <span className="text-xs text-slate-400">{h.execution_count}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
