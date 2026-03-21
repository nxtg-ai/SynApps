/**
 * ExecutionHistoryPage
 *
 * Covers:
 *   GET /api/v1/history              — enriched list with step counts, flow names, filtering
 *   GET /api/v1/history/{run_id}     — full execution detail + trace
 *
 * Route: /execution-history
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

function getBaseUrl(): string {
  return (window as any).__API_BASE__ ?? '';
}
function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}
function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

interface HistoryEntry {
  run_id: string;
  flow_id: string | null;
  flow_name: string | null;
  status: string;
  start_time: number | null;
  end_time: number | null;
  duration_ms: number | null;
  step_count: number;
  steps_succeeded: number;
  steps_failed: number;
  error: string | null;
  input_summary: Record<string, unknown> | null;
  output_summary: { keys: string[]; total_keys: number } | null;
}

interface HistoryList {
  history: HistoryEntry[];
  total: number;
  page: number;
  page_size: number;
}

interface TraceNode {
  node_id: string;
  node_type: string;
  status: string;
  duration_ms?: number;
  error?: string;
}

interface RunDetail extends HistoryEntry {
  input_data: unknown;
  trace: { nodes: TraceNode[]; duration_ms?: number };
}

type TabId = 'browse' | 'detail';

const STATUS_OPTIONS = ['', 'success', 'error', 'running', 'idle'];

const ExecutionHistoryPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('browse');

  // Browse tab state
  const [statusFilter, setStatusFilter] = useState('');
  const [templateFilter, setTemplateFilter] = useState('');
  const [page, setPage] = useState(1);
  const [browseResult, setBrowseResult] = useState<HistoryList | null>(null);
  const [browseError, setBrowseError] = useState('');
  const [browseLoading, setBrowseLoading] = useState(false);

  // Detail tab state
  const [runId, setRunId] = useState('');
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailError, setDetailError] = useState('');
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchHistory = async (pg = page) => {
    setBrowseLoading(true);
    setBrowseError('');
    setBrowseResult(null);
    const params = new URLSearchParams({ page: String(pg), page_size: '20' });
    if (statusFilter) params.set('status', statusFilter);
    if (templateFilter) params.set('template', templateFilter);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/history?${params}`, {
        headers: authHeaders(),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setBrowseResult(await resp.json());
    } catch (err: unknown) {
      setBrowseError(String(err));
    } finally {
      setBrowseLoading(false);
    }
  };

  const fetchDetail = async () => {
    if (!runId.trim()) return;
    setDetailLoading(true);
    setDetailError('');
    setDetail(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/history/${encodeURIComponent(runId.trim())}`, {
        headers: authHeaders(),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setDetail(await resp.json());
    } catch (err: unknown) {
      setDetailError(String(err));
    } finally {
      setDetailLoading(false);
    }
  };

  const openDetail = (entry: HistoryEntry) => {
    setRunId(entry.run_id);
    setActiveTab('detail');
    // auto-fetch
    setDetailLoading(true);
    setDetailError('');
    setDetail(null);
    fetch(`${getBaseUrl()}/api/v1/history/${encodeURIComponent(entry.run_id)}`, {
      headers: authHeaders(),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => setDetail(d))
      .catch((err) => setDetailError(String(err)))
      .finally(() => setDetailLoading(false));
  };

  const fmtTime = (ts: number | null) =>
    ts ? new Date(ts * 1000).toLocaleString() : '—';
  const fmtMs = (ms: number | null) =>
    ms != null ? `${ms.toFixed(0)} ms` : '—';

  const statusBadge = (s: string) => {
    const colors: Record<string, string> = {
      success: '#4ade80',
      error: '#f87171',
      running: '#60a5fa',
      idle: '#9ca3af',
    };
    return (
      <span
        data-testid="status-badge"
        style={{
          background: colors[s] ?? '#e5e7eb',
          color: '#111',
          borderRadius: 4,
          padding: '2px 8px',
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        {s}
      </span>
    );
  };

  return (
    <MainLayout title="Execution History">
      <div data-testid="execution-history-page" style={{ padding: 24, maxWidth: 1100 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          {(['browse', 'detail'] as TabId[]).map((t) => (
            <button
              key={t}
              data-testid={`tab-${t}`}
              onClick={() => setActiveTab(t)}
              style={{
                padding: '8px 20px',
                borderRadius: 6,
                border: 'none',
                cursor: 'pointer',
                background: activeTab === t ? '#6366f1' : '#374151',
                color: '#fff',
                fontWeight: activeTab === t ? 700 : 400,
              }}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        {/* ── Browse Tab ──────────────────────────────────────────── */}
        {activeTab === 'browse' && (
          <div data-testid="tab-browse-content">
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
              <select
                data-testid="status-filter"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #4b5563', background: '#1f2937', color: '#fff' }}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s || 'All statuses'}
                  </option>
                ))}
              </select>
              <input
                data-testid="template-filter"
                placeholder="Filter by template name…"
                value={templateFilter}
                onChange={(e) => setTemplateFilter(e.target.value)}
                style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #4b5563', background: '#1f2937', color: '#fff', minWidth: 200 }}
              />
              <button
                data-testid="fetch-history-btn"
                onClick={() => { setPage(1); fetchHistory(1); }}
                style={{ padding: '6px 18px', borderRadius: 6, background: '#6366f1', color: '#fff', border: 'none', cursor: 'pointer' }}
              >
                Search
              </button>
            </div>

            {browseLoading && <p data-testid="browse-loading">Loading…</p>}
            {browseError && <p data-testid="browse-error" style={{ color: '#f87171' }}>{browseError}</p>}

            {browseResult && (
              <div>
                <p data-testid="total-count" style={{ color: '#9ca3af', marginBottom: 8 }}>
                  {browseResult.total} run{browseResult.total !== 1 ? 's' : ''} — page {browseResult.page}
                </p>
                {browseResult.history.length === 0 ? (
                  <p data-testid="no-history">No runs found.</p>
                ) : (
                  <table data-testid="history-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: '#1f2937', color: '#9ca3af', fontSize: 13 }}>
                        <th style={{ padding: '8px 12px', textAlign: 'left' }}>Run ID</th>
                        <th style={{ padding: '8px 12px', textAlign: 'left' }}>Flow</th>
                        <th style={{ padding: '8px 12px', textAlign: 'left' }}>Status</th>
                        <th style={{ padding: '8px 12px', textAlign: 'left' }}>Start</th>
                        <th style={{ padding: '8px 12px', textAlign: 'left' }}>Duration</th>
                        <th style={{ padding: '8px 12px', textAlign: 'left' }}>Steps</th>
                      </tr>
                    </thead>
                    <tbody>
                      {browseResult.history.map((entry) => (
                        <tr
                          key={entry.run_id}
                          data-testid="history-row"
                          onClick={() => openDetail(entry)}
                          style={{ cursor: 'pointer', borderBottom: '1px solid #374151' }}
                        >
                          <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: 12 }}>
                            {entry.run_id.slice(0, 16)}…
                          </td>
                          <td style={{ padding: '8px 12px' }}>{entry.flow_name ?? entry.flow_id ?? '—'}</td>
                          <td style={{ padding: '8px 12px' }}>{statusBadge(entry.status)}</td>
                          <td style={{ padding: '8px 12px', fontSize: 12 }}>{fmtTime(entry.start_time)}</td>
                          <td style={{ padding: '8px 12px' }}>{fmtMs(entry.duration_ms)}</td>
                          <td style={{ padding: '8px 12px' }}>
                            {entry.steps_succeeded}/{entry.step_count}
                            {entry.steps_failed > 0 && (
                              <span style={{ color: '#f87171', marginLeft: 4 }}>
                                ({entry.steps_failed} failed)
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                {browseResult.total > browseResult.page_size && (
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button
                      data-testid="prev-page"
                      disabled={page <= 1}
                      onClick={() => { const p = page - 1; setPage(p); fetchHistory(p); }}
                      style={{ padding: '4px 12px', borderRadius: 4, border: 'none', background: '#374151', color: '#fff', cursor: 'pointer' }}
                    >
                      Prev
                    </button>
                    <button
                      data-testid="next-page"
                      disabled={browseResult.history.length < browseResult.page_size}
                      onClick={() => { const p = page + 1; setPage(p); fetchHistory(p); }}
                      style={{ padding: '4px 12px', borderRadius: 4, border: 'none', background: '#374151', color: '#fff', cursor: 'pointer' }}
                    >
                      Next
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Detail Tab ──────────────────────────────────────────── */}
        {activeTab === 'detail' && (
          <div data-testid="tab-detail-content">
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <input
                data-testid="run-id-input"
                placeholder="Run ID…"
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
                style={{ flex: 1, padding: '6px 10px', borderRadius: 6, border: '1px solid #4b5563', background: '#1f2937', color: '#fff' }}
              />
              <button
                data-testid="fetch-detail-btn"
                disabled={!runId.trim()}
                onClick={fetchDetail}
                style={{ padding: '6px 18px', borderRadius: 6, background: '#6366f1', color: '#fff', border: 'none', cursor: 'pointer' }}
              >
                Fetch Detail
              </button>
            </div>

            {detailLoading && <p data-testid="detail-loading">Loading…</p>}
            {detailError && <p data-testid="detail-error" style={{ color: '#f87171' }}>{detailError}</p>}

            {detail && (
              <div data-testid="detail-panel">
                <div style={{ background: '#1f2937', borderRadius: 8, padding: 16, marginBottom: 16 }}>
                  <h3 data-testid="detail-run-id" style={{ margin: '0 0 8px', fontFamily: 'monospace', fontSize: 14 }}>{detail.run_id}</h3>
                  <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', color: '#9ca3af', fontSize: 13 }}>
                    <span>Status: {statusBadge(detail.status)}</span>
                    <span>Flow: <strong>{detail.flow_name ?? detail.flow_id ?? '—'}</strong></span>
                    <span>Start: {fmtTime(detail.start_time)}</span>
                    <span>Duration: {fmtMs(detail.duration_ms)}</span>
                    <span data-testid="detail-steps">Steps: {detail.steps_succeeded}/{detail.step_count}</span>
                  </div>
                  {detail.error && (
                    <p data-testid="detail-run-error" style={{ color: '#f87171', marginTop: 8 }}>{detail.error}</p>
                  )}
                </div>

                {detail.trace?.nodes?.length > 0 && (
                  <div>
                    <h4 style={{ color: '#e5e7eb', marginBottom: 8 }}>Execution Trace</h4>
                    <table data-testid="trace-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ background: '#1f2937', color: '#9ca3af', fontSize: 13 }}>
                          <th style={{ padding: '6px 10px', textAlign: 'left' }}>Node ID</th>
                          <th style={{ padding: '6px 10px', textAlign: 'left' }}>Type</th>
                          <th style={{ padding: '6px 10px', textAlign: 'left' }}>Status</th>
                          <th style={{ padding: '6px 10px', textAlign: 'left' }}>Duration</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.trace.nodes.map((n, i) => (
                          <tr key={i} data-testid="trace-node" style={{ borderBottom: '1px solid #374151' }}>
                            <td style={{ padding: '6px 10px', fontFamily: 'monospace', fontSize: 12 }}>{n.node_id}</td>
                            <td style={{ padding: '6px 10px' }}>{n.node_type}</td>
                            <td style={{ padding: '6px 10px' }}>{statusBadge(n.status)}</td>
                            <td style={{ padding: '6px 10px' }}>{fmtMs(n.duration_ms ?? null)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </MainLayout>
  );
};

export default ExecutionHistoryPage;
