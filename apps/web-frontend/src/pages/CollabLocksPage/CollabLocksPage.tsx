/** N-114 — Collaboration Locks & Bulk Cost Estimate */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LockEntry {
  user_id: string;
  username: string;
  locked_at: number;
}

interface LocksResponse {
  locks: Record<string, LockEntry>;
}

interface AcquireResponse {
  locked: boolean;
  node_id: string;
  user_id: string;
}

interface ReleaseResponse {
  released: boolean;
  node_id: string;
}

interface EstimateBreakdownItem {
  node_id: string;
  node_type: string;
  cost: number;
}

interface EstimateResponse {
  total_cost: number;
  currency: string;
  breakdown: EstimateBreakdownItem[];
}

type ActiveTab = 'locks' | 'cost';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
}

function authHeaders(): Record<string, string> {
  const tok = localStorage.getItem('access_token') ?? '';
  return { Authorization: `Bearer ${tok}` };
}

function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const CollabLocksPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('locks');

  // --- Tab 1: Node Locks ---
  const [lockFlowId, setLockFlowId] = useState('');
  const [lockNodeId, setLockNodeId] = useState('');

  const [acquireResult, setAcquireResult] = useState<AcquireResponse | null>(null);
  const [acquireError, setAcquireError] = useState<string | null>(null);

  const [releaseResult, setReleaseResult] = useState<ReleaseResponse | null>(null);
  const [releaseError, setReleaseError] = useState<string | null>(null);

  const [locksLoading, setLocksLoading] = useState(false);
  const [locksError, setLocksError] = useState<string | null>(null);
  const [locksData, setLocksData] = useState<LocksResponse | null>(null);

  // --- Tab 2: Bulk Cost Estimate ---
  const [nodesJson, setNodesJson] = useState('');
  const [foreachIterations, setForeachIterations] = useState(10);
  const [estimateResult, setEstimateResult] = useState<EstimateResponse | null>(null);
  const [estimateError, setEstimateError] = useState<string | null>(null);

  // -------------------------------------------------------------------------
  // Handlers — Tab 1
  // -------------------------------------------------------------------------

  async function handleAcquire() {
    setAcquireResult(null);
    setAcquireError(null);
    try {
      const res = await fetch(
        `${getBaseUrl()}/api/v1/flows/${encodeURIComponent(lockFlowId)}/collaboration/lock/${encodeURIComponent(lockNodeId)}`,
        { method: 'POST', headers: authHeaders() },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (res.status === 409) {
          setAcquireError(data.detail ?? 'already locked');
        } else {
          setAcquireError(data.detail ?? `Error ${res.status}`);
        }
        return;
      }
      const data: AcquireResponse = await res.json();
      setAcquireResult(data);
    } catch {
      setAcquireError('Network error');
    }
  }

  async function handleRelease() {
    setReleaseResult(null);
    setReleaseError(null);
    try {
      const res = await fetch(
        `${getBaseUrl()}/api/v1/flows/${encodeURIComponent(lockFlowId)}/collaboration/lock/${encodeURIComponent(lockNodeId)}`,
        { method: 'DELETE', headers: authHeaders() },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setReleaseError(data.detail ?? `Error ${res.status}`);
        return;
      }
      const data: ReleaseResponse = await res.json();
      setReleaseResult(data);
    } catch {
      setReleaseError('Network error');
    }
  }

  async function handleLoadLocks() {
    setLocksLoading(true);
    setLocksError(null);
    setLocksData(null);
    try {
      const res = await fetch(
        `${getBaseUrl()}/api/v1/flows/${encodeURIComponent(lockFlowId)}/collaboration/locks`,
        { headers: authHeaders() },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setLocksError(data.detail ?? `Error ${res.status}`);
        return;
      }
      const data: LocksResponse = await res.json();
      setLocksData(data);
    } catch {
      setLocksError('Network error');
    } finally {
      setLocksLoading(false);
    }
  }

  // -------------------------------------------------------------------------
  // Handlers — Tab 2
  // -------------------------------------------------------------------------

  async function handleEstimate() {
    setEstimateResult(null);
    setEstimateError(null);

    let parsedNodes: unknown;
    try {
      parsedNodes = JSON.parse(nodesJson);
    } catch {
      setEstimateError('Invalid JSON');
      return;
    }

    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/flows/estimate-cost`, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ nodes: parsedNodes, foreach_iterations: foreachIterations }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setEstimateError(data.detail ?? `Error ${res.status}`);
        return;
      }
      const data: EstimateResponse = await res.json();
      setEstimateResult(data);
    } catch {
      setEstimateError('Network error');
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const lockEntries = locksData ? Object.entries(locksData.locks) : [];

  return (
    <MainLayout title="Collab Locks & Cost">
      <div style={{ maxWidth: 860, margin: '0 auto', padding: 24 }}>
        <h1
          data-testid="page-title"
          style={{ fontSize: 22, fontWeight: 700, marginBottom: 24, color: '#e2e8f0' }}
        >
          Collab Locks &amp; Cost
        </h1>

        {/* Tab bar */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          <button
            data-testid="tab-locks"
            onClick={() => setActiveTab('locks')}
            style={{
              padding: '8px 20px',
              borderRadius: 6,
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              background: activeTab === 'locks' ? '#6366f1' : '#334155',
              color: '#e2e8f0',
            }}
          >
            Node Locks
          </button>
          <button
            data-testid="tab-cost"
            onClick={() => setActiveTab('cost')}
            style={{
              padding: '8px 20px',
              borderRadius: 6,
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              background: activeTab === 'cost' ? '#6366f1' : '#334155',
              color: '#e2e8f0',
            }}
          >
            Bulk Cost Estimate
          </button>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* Tab 1 — Node Locks                                                 */}
        {/* ----------------------------------------------------------------- */}
        {activeTab === 'locks' && (
          <div data-testid="tab-panel-locks">
            {/* Acquire / Release section */}
            <section
              style={{
                marginBottom: 32,
                padding: 20,
                borderRadius: 8,
                border: '1px solid #334155',
                background: '#1e293b',
              }}
            >
              <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: '#cbd5e1' }}>
                Acquire / Release Lock
              </h2>

              <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                <input
                  data-testid="lock-flow-id"
                  type="text"
                  placeholder="Flow ID"
                  value={lockFlowId}
                  onChange={(e) => setLockFlowId(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 6,
                    border: '1px solid #475569',
                    background: '#0f172a',
                    color: '#e2e8f0',
                    minWidth: 180,
                  }}
                />
                <input
                  data-testid="lock-node-id"
                  type="text"
                  placeholder="Node ID"
                  value={lockNodeId}
                  onChange={(e) => setLockNodeId(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 6,
                    border: '1px solid #475569',
                    background: '#0f172a',
                    color: '#e2e8f0',
                    minWidth: 180,
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: 12 }}>
                <button
                  data-testid="acquire-btn"
                  onClick={handleAcquire}
                  style={{
                    padding: '8px 20px',
                    borderRadius: 6,
                    border: 'none',
                    cursor: 'pointer',
                    background: '#6366f1',
                    color: '#fff',
                    fontWeight: 600,
                  }}
                >
                  Acquire Lock
                </button>
                <button
                  data-testid="release-btn"
                  onClick={handleRelease}
                  style={{
                    padding: '8px 20px',
                    borderRadius: 6,
                    border: 'none',
                    cursor: 'pointer',
                    background: '#ef4444',
                    color: '#fff',
                    fontWeight: 600,
                  }}
                >
                  Release Lock
                </button>
              </div>

              {acquireError && (
                <p
                  data-testid="acquire-error"
                  style={{ marginTop: 12, color: '#f87171', fontSize: 14 }}
                >
                  {acquireError}
                </p>
              )}

              {acquireResult && (
                <div
                  data-testid="acquire-result"
                  style={{ marginTop: 12, fontSize: 14, color: '#94a3b8' }}
                >
                  Locked:{' '}
                  <span data-testid="acquire-locked">
                    {String(acquireResult.locked)}
                  </span>
                </div>
              )}

              {releaseError && (
                <p
                  data-testid="release-error"
                  style={{ marginTop: 12, color: '#f87171', fontSize: 14 }}
                >
                  {releaseError}
                </p>
              )}

              {releaseResult && (
                <div
                  data-testid="release-result"
                  style={{ marginTop: 12, fontSize: 14, color: '#94a3b8' }}
                >
                  Released:{' '}
                  <span data-testid="release-released">
                    {String(releaseResult.released)}
                  </span>
                </div>
              )}
            </section>

            {/* Lock list section */}
            <section
              style={{
                padding: 20,
                borderRadius: 8,
                border: '1px solid #334155',
                background: '#1e293b',
              }}
            >
              <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: '#cbd5e1' }}>
                Flow Locks
              </h2>

              <button
                data-testid="load-locks-btn"
                onClick={handleLoadLocks}
                style={{
                  padding: '8px 20px',
                  borderRadius: 6,
                  border: 'none',
                  cursor: 'pointer',
                  background: '#0ea5e9',
                  color: '#fff',
                  fontWeight: 600,
                  marginBottom: 16,
                }}
              >
                Load Locks
              </button>

              {locksLoading && (
                <p data-testid="locks-loading" style={{ color: '#94a3b8', fontSize: 14 }}>
                  Loading…
                </p>
              )}

              {locksError && (
                <p data-testid="locks-error" style={{ color: '#f87171', fontSize: 14 }}>
                  {locksError}
                </p>
              )}

              {locksData && !locksLoading && !locksError && lockEntries.length === 0 && (
                <p data-testid="no-locks" style={{ color: '#94a3b8', fontSize: 14 }}>
                  No locks found for this flow.
                </p>
              )}

              {locksData && lockEntries.length > 0 && (
                <ul data-testid="locks-list" style={{ listStyle: 'none', padding: 0 }}>
                  {lockEntries.map(([nodeId, lock]) => (
                    <li
                      key={nodeId}
                      data-testid="lock-item"
                      style={{
                        padding: '10px 0',
                        borderBottom: '1px solid #334155',
                        display: 'flex',
                        gap: 16,
                        fontSize: 14,
                      }}
                    >
                      <span
                        data-testid="lock-item-node-id"
                        style={{ fontFamily: 'monospace', color: '#7dd3fc' }}
                      >
                        {nodeId}
                      </span>
                      <span data-testid="lock-item-user" style={{ color: '#94a3b8' }}>
                        {lock.username}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}

        {/* ----------------------------------------------------------------- */}
        {/* Tab 2 — Bulk Cost Estimate                                         */}
        {/* ----------------------------------------------------------------- */}
        {activeTab === 'cost' && (
          <div data-testid="tab-panel-cost">
            <section
              style={{
                padding: 20,
                borderRadius: 8,
                border: '1px solid #334155',
                background: '#1e293b',
              }}
            >
              <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: '#cbd5e1' }}>
                Bulk Cost Estimate
              </h2>

              <div style={{ marginBottom: 16 }}>
                <label
                  htmlFor="nodes-json-input"
                  style={{ display: 'block', fontSize: 13, color: '#94a3b8', marginBottom: 6 }}
                >
                  Nodes JSON array
                </label>
                <textarea
                  id="nodes-json-input"
                  data-testid="nodes-json"
                  rows={6}
                  placeholder={`[{"type": "llm", ...}]`}
                  value={nodesJson}
                  onChange={(e) => setNodesJson(e.target.value)}
                  style={{
                    width: '100%',
                    maxWidth: 580,
                    padding: '8px 12px',
                    borderRadius: 6,
                    border: '1px solid #475569',
                    background: '#0f172a',
                    color: '#e2e8f0',
                    fontFamily: 'monospace',
                    fontSize: 13,
                    resize: 'vertical',
                  }}
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label
                  htmlFor="foreach-iterations-input"
                  style={{ display: 'block', fontSize: 13, color: '#94a3b8', marginBottom: 6 }}
                >
                  ForEach iterations
                </label>
                <input
                  id="foreach-iterations-input"
                  data-testid="foreach-iterations"
                  type="number"
                  min={1}
                  value={foreachIterations}
                  onChange={(e) => setForeachIterations(Number(e.target.value))}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 6,
                    border: '1px solid #475569',
                    background: '#0f172a',
                    color: '#e2e8f0',
                    width: 120,
                  }}
                />
              </div>

              <button
                data-testid="estimate-btn"
                onClick={handleEstimate}
                style={{
                  padding: '8px 20px',
                  borderRadius: 6,
                  border: 'none',
                  cursor: 'pointer',
                  background: '#6366f1',
                  color: '#fff',
                  fontWeight: 600,
                }}
              >
                Estimate Cost
              </button>

              {estimateError && (
                <p
                  data-testid="estimate-error"
                  style={{ marginTop: 12, color: '#f87171', fontSize: 14 }}
                >
                  {estimateError}
                </p>
              )}
            </section>

            {estimateResult && (
              <section
                data-testid="estimate-result"
                style={{
                  marginTop: 24,
                  padding: 20,
                  borderRadius: 8,
                  border: '1px solid #334155',
                  background: '#1e293b',
                }}
              >
                <div style={{ marginBottom: 16, display: 'flex', gap: 32 }}>
                  <div>
                    <p style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>Total Cost</p>
                    <p
                      data-testid="estimate-total"
                      style={{ fontSize: 22, fontWeight: 700, color: '#34d399' }}
                    >
                      {estimateResult.total_cost}
                    </p>
                  </div>
                  <div>
                    <p style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>Currency</p>
                    <p
                      data-testid="estimate-currency"
                      style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0' }}
                    >
                      {estimateResult.currency}
                    </p>
                  </div>
                </div>

                {Array.isArray(estimateResult.breakdown) && estimateResult.breakdown.length > 0 && (
                  <ul data-testid="estimate-breakdown" style={{ listStyle: 'none', padding: 0 }}>
                    {estimateResult.breakdown.map((item) => (
                      <li
                        key={item.node_id}
                        data-testid="estimate-item"
                        style={{
                          display: 'flex',
                          gap: 16,
                          padding: '8px 0',
                          borderBottom: '1px solid #334155',
                          fontSize: 14,
                        }}
                      >
                        <span
                          data-testid="estimate-item-node"
                          style={{ fontFamily: 'monospace', color: '#7dd3fc', minWidth: 140 }}
                        >
                          {item.node_id} ({item.node_type})
                        </span>
                        <span data-testid="estimate-item-cost" style={{ color: '#34d399' }}>
                          {item.cost}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
          </div>
        )}
      </div>
    </MainLayout>
  );
};

export default CollabLocksPage;
