/**
 * PlaygroundPage component
 * Interactive API Playground for testing workflows, streaming events, and browsing the marketplace.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Flow {
  id: string;
  name: string;
}

interface RunResult {
  run_id: string;
  status: string;
}

interface SseEvent {
  id: number;
  eventType: string;
  data: string;
  timestamp: string;
}

interface MarketplaceListing {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  install_count: number;
}

type TabId = 'runner' | 'stream' | 'marketplace';

// ── Helpers ──────────────────────────────────────────────────────────────────

function getApiBase(): string {
  return (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';
}

function getToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
}

function buildHeaders(): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

/** SSE event color by event type. */
function eventColor(eventType: string): string {
  switch (eventType) {
    case 'node_started':
      return '#3b82f6'; // blue-500
    case 'node_completed':
      return '#22c55e'; // green-500
    case 'node_failed':
      return '#ef4444'; // red-500
    case 'execution_complete':
      return '#a855f7'; // purple-500
    default:
      return '#9ca3af'; // gray-400
  }
}

// ── Sub-components ─────────────────────────────────────────────────────────

// Spinner
const Spinner: React.FC = () => (
  <span
    style={{
      display: 'inline-block',
      width: 16,
      height: 16,
      border: '2px solid #4b5563',
      borderTop: '2px solid #60a5fa',
      borderRadius: '50%',
      animation: 'pg-spin 0.8s linear infinite',
      verticalAlign: 'middle',
      marginRight: 6,
    }}
  />
);

// Error banner
const ErrorBanner: React.FC<{ message: string }> = ({ message }) => (
  <div
    style={{
      marginTop: 8,
      padding: '8px 12px',
      background: 'rgba(239,68,68,0.12)',
      border: '1px solid #ef4444',
      borderRadius: 6,
      color: '#f87171',
      fontSize: 13,
    }}
  >
    {message}
  </div>
);

// Toast notification
const Toast: React.FC<{ message: string; onDone: () => void }> = ({ message, onDone }) => {
  useEffect(() => {
    const t = setTimeout(onDone, 3000);
    return () => clearTimeout(t);
  }, [onDone]);

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        background: '#22c55e',
        color: '#fff',
        padding: '10px 16px',
        borderRadius: 8,
        fontWeight: 600,
        fontSize: 14,
        zIndex: 9999,
        boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
      }}
    >
      {message}
    </div>
  );
};

// ── Tab 1: Workflow Runner ───────────────────────────────────────────────────

const WorkflowRunner: React.FC<{ onRunComplete: (runId: string) => void }> = ({
  onRunComplete,
}) => {
  const [flows, setFlows] = useState<Flow[]>([]);
  const [selectedFlowId, setSelectedFlowId] = useState<string>('');
  const [jsonInput, setJsonInput] = useState<string>('');
  const [jsonError, setJsonError] = useState<string>('');
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string>('');
  const [loadingFlows, setLoadingFlows] = useState<boolean>(true);

  useEffect(() => {
    const load = async () => {
      setLoadingFlows(true);
      try {
        const res = await fetch(`${getApiBase()}/api/v1/flows`, {
          headers: buildHeaders(),
        });
        if (!res.ok) throw new Error(`Failed to load workflows (${res.status})`);
        const data: unknown = await res.json();
        let items: Flow[] = [];
        if (Array.isArray(data)) {
          items = data as Flow[];
        } else if (data && typeof data === 'object' && 'items' in data) {
          items = (data as { items: Flow[] }).items;
        }
        setFlows(items);
        if (items.length > 0) setSelectedFlowId(items[0].id);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load workflows');
      } finally {
        setLoadingFlows(false);
      }
    };
    void load();
  }, []);

  const handleJsonChange = (value: string) => {
    setJsonInput(value);
    if (value.trim() === '') {
      setJsonError('');
      return;
    }
    try {
      JSON.parse(value);
      setJsonError('');
    } catch {
      setJsonError('Invalid JSON — check syntax');
    }
  };

  const handleRun = async () => {
    if (!selectedFlowId) {
      setError('Please select a workflow');
      return;
    }

    let parsed: Record<string, unknown> = {};
    if (jsonInput.trim()) {
      try {
        parsed = JSON.parse(jsonInput) as Record<string, unknown>;
      } catch {
        setJsonError('Invalid JSON — cannot submit');
        return;
      }
    }

    setIsRunning(true);
    setError('');
    setRunResult(null);

    try {
      const res = await fetch(
        `${getApiBase()}/api/v1/flows/${selectedFlowId}/runs`,
        {
          method: 'POST',
          headers: buildHeaders(),
          body: JSON.stringify({ input: parsed }),
        },
      );

      if (!res.ok) {
        const body = await res.text();
        throw new Error(`Run failed (${res.status}): ${body}`);
      }

      const result = (await res.json()) as RunResult;
      setRunResult(result);
      onRunComplete(result.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Run failed');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div style={styles.panel}>
      <h2 style={styles.panelTitle}>Workflow Runner</h2>

      {/* Workflow selector */}
      <div style={styles.field}>
        <label style={styles.label}>Select Workflow</label>
        {loadingFlows ? (
          <div style={styles.subtle}>
            <Spinner /> Loading workflows…
          </div>
        ) : (
          <select
            value={selectedFlowId}
            onChange={(e) => setSelectedFlowId(e.target.value)}
            style={styles.select}
          >
            {flows.length === 0 && (
              <option value="">No workflows available</option>
            )}
            {flows.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* JSON input */}
      <div style={styles.field}>
        <label style={styles.label}>Input JSON</label>
        <textarea
          value={jsonInput}
          onChange={(e) => handleJsonChange(e.target.value)}
          placeholder={'{"key": "value"}'}
          rows={6}
          style={{
            ...styles.textarea,
            borderColor: jsonError ? '#ef4444' : '#374151',
          }}
        />
        {jsonError && <ErrorBanner message={jsonError} />}
      </div>

      {/* Run button */}
      <button
        onClick={() => void handleRun()}
        disabled={isRunning || loadingFlows}
        style={{
          ...styles.btn,
          opacity: isRunning || loadingFlows ? 0.6 : 1,
          cursor: isRunning || loadingFlows ? 'not-allowed' : 'pointer',
        }}
      >
        {isRunning ? (
          <>
            <Spinner /> Running…
          </>
        ) : (
          'Run Workflow'
        )}
      </button>

      {/* Error */}
      {error && <ErrorBanner message={error} />}

      {/* Result */}
      {runResult && (
        <div style={styles.resultBox}>
          <div style={styles.resultRow}>
            <span style={styles.resultLabel}>Run ID</span>
            <code style={styles.code}>{runResult.run_id}</code>
          </div>
          <div style={styles.resultRow}>
            <span style={styles.resultLabel}>Status</span>
            <span style={{ color: '#60a5fa' }}>{runResult.status}</span>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Tab 2: SSE Live Stream ───────────────────────────────────────────────────

const SseStream: React.FC<{ prefillRunId: string }> = ({ prefillRunId }) => {
  const [runId, setRunId] = useState<string>(prefillRunId);
  const [events, setEvents] = useState<SseEvent[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const abortRef = useRef<AbortController | null>(null);
  const eventListRef = useRef<HTMLDivElement | null>(null);
  const eventIdRef = useRef<number>(0);

  // Keep runId in sync when parent populates it (after a run)
  useEffect(() => {
    if (prefillRunId && !isConnected) {
      setRunId(prefillRunId);
    }
  }, [prefillRunId, isConnected]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (eventListRef.current) {
      eventListRef.current.scrollTop = eventListRef.current.scrollHeight;
    }
  }, [events]);

  const connect = useCallback(async () => {
    if (!runId.trim()) {
      setError('Please enter an Execution ID');
      return;
    }

    const token = getToken();
    const headers: Record<string, string> = { Accept: 'text/event-stream' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const controller = new AbortController();
    abortRef.current = controller;

    setEvents([]);
    setError('');
    setIsConnected(true);

    try {
      const res = await fetch(
        `${getApiBase()}/api/v1/executions/${encodeURIComponent(runId.trim())}/stream`,
        { headers, signal: controller.signal },
      );

      if (!res.ok) {
        const body = await res.text();
        throw new Error(`Stream error (${res.status}): ${body}`);
      }

      if (!res.body) throw new Error('Response body is null');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // Parse SSE format manually
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        let currentEvent = 'message';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            currentData = line.slice(5).trim();
          } else if (line === '') {
            // Blank line = end of event block
            if (currentData) {
              const entry: SseEvent = {
                id: ++eventIdRef.current,
                eventType: currentEvent,
                data: currentData,
                timestamp: new Date().toISOString(),
              };
              setEvents((prev) => [...prev, entry]);

              if (currentEvent === 'execution_complete') {
                reader.cancel();
                setIsConnected(false);
                return;
              }
            }
            currentEvent = 'message';
            currentData = '';
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // User disconnected intentionally
        return;
      }
      setError(err instanceof Error ? err.message : 'Stream error');
    } finally {
      setIsConnected(false);
    }
  }, [runId]);

  const disconnect = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setIsConnected(false);
  };

  const formatData = (raw: string): string => {
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw;
    }
  };

  return (
    <div style={styles.panel}>
      <h2 style={styles.panelTitle}>SSE Live Stream</h2>

      <div style={styles.field}>
        <label style={styles.label}>Execution ID (run_id)</label>
        <input
          type="text"
          value={runId}
          onChange={(e) => setRunId(e.target.value)}
          placeholder="Enter execution run_id"
          disabled={isConnected}
          style={{
            ...styles.input,
            opacity: isConnected ? 0.6 : 1,
          }}
        />
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={() => void connect()}
          disabled={isConnected}
          style={{
            ...styles.btn,
            opacity: isConnected ? 0.5 : 1,
            cursor: isConnected ? 'not-allowed' : 'pointer',
          }}
        >
          Connect
        </button>
        <button
          onClick={disconnect}
          disabled={!isConnected}
          style={{
            ...styles.btn,
            background: '#374151',
            opacity: !isConnected ? 0.5 : 1,
            cursor: !isConnected ? 'not-allowed' : 'pointer',
          }}
        >
          Disconnect
        </button>
      </div>

      {error && <ErrorBanner message={error} />}

      {/* Status indicator */}
      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: isConnected ? '#22c55e' : '#4b5563',
          }}
        />
        <span style={styles.subtle}>{isConnected ? 'Connected — streaming events' : 'Disconnected'}</span>
      </div>

      {/* Event log */}
      <div
        ref={eventListRef}
        style={{
          marginTop: 12,
          height: 340,
          overflowY: 'auto',
          background: '#111827',
          borderRadius: 8,
          border: '1px solid #1f2937',
          padding: 8,
          fontFamily: 'monospace',
          fontSize: 12,
        }}
      >
        {events.length === 0 ? (
          <div style={{ color: '#4b5563', padding: 8 }}>
            {isConnected ? 'Waiting for events…' : 'No events yet. Connect to a run to see live data.'}
          </div>
        ) : (
          events.map((ev) => (
            <div
              key={ev.id}
              style={{
                marginBottom: 10,
                padding: '6px 8px',
                borderLeft: `3px solid ${eventColor(ev.eventType)}`,
                background: 'rgba(255,255,255,0.02)',
                borderRadius: '0 4px 4px 0',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ color: eventColor(ev.eventType), fontWeight: 700 }}>
                  {ev.eventType}
                </span>
                <span style={{ color: '#4b5563', fontSize: 11 }}>
                  {ev.timestamp.slice(11, 23)}
                </span>
              </div>
              <pre
                style={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                  color: '#d1d5db',
                }}
              >
                {formatData(ev.data)}
              </pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// ── Tab 3: Marketplace Browser ───────────────────────────────────────────────

const MarketplaceBrowser: React.FC = () => {
  const [query, setQuery] = useState<string>('');
  const [listings, setListings] = useState<MarketplaceListing[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [installing, setInstalling] = useState<string>(''); // listing id being installed
  const [toast, setToast] = useState<string>('');
  const [hasSearched, setHasSearched] = useState<boolean>(false);

  const search = useCallback(async () => {
    setIsLoading(true);
    setError('');
    setHasSearched(true);

    try {
      const params = new URLSearchParams({ per_page: '20' });
      if (query.trim()) params.set('q', query.trim());

      const res = await fetch(
        `${getApiBase()}/api/v1/marketplace/search?${params.toString()}`,
        { headers: buildHeaders() },
      );

      if (!res.ok) throw new Error(`Search failed (${res.status})`);

      const data = (await res.json()) as { items: MarketplaceListing[]; total: number };
      setListings(data.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setIsLoading(false);
    }
  }, [query]);

  // Load featured on mount
  useEffect(() => {
    const loadFeatured = async () => {
      setIsLoading(true);
      try {
        const res = await fetch(`${getApiBase()}/api/v1/marketplace/featured`, {
          headers: buildHeaders(),
        });
        if (!res.ok) throw new Error(`Failed to load marketplace (${res.status})`);
        const data = (await res.json()) as { items: MarketplaceListing[] };
        setListings(data.items ?? []);
        setHasSearched(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load marketplace');
      } finally {
        setIsLoading(false);
      }
    };
    void loadFeatured();
  }, []);

  const install = async (listingId: string, name: string) => {
    setInstalling(listingId);
    try {
      const res = await fetch(
        `${getApiBase()}/api/v1/marketplace/install/${encodeURIComponent(listingId)}`,
        {
          method: 'POST',
          headers: buildHeaders(),
          body: JSON.stringify({}),
        },
      );

      if (!res.ok) {
        const body = await res.text();
        throw new Error(`Install failed (${res.status}): ${body}`);
      }

      setToast(`"${name}" installed successfully`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Install failed');
    } finally {
      setInstalling('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') void search();
  };

  return (
    <div style={styles.panel}>
      <h2 style={styles.panelTitle}>Marketplace Browser</h2>

      {/* Search bar */}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search workflows, templates…"
          style={{ ...styles.input, flex: 1 }}
        />
        <button
          onClick={() => void search()}
          disabled={isLoading}
          style={{
            ...styles.btn,
            opacity: isLoading ? 0.6 : 1,
            cursor: isLoading ? 'not-allowed' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {isLoading ? <Spinner /> : null}
          Search
        </button>
      </div>

      {error && <ErrorBanner message={error} />}

      {/* Results */}
      <div style={{ marginTop: 16 }}>
        {isLoading && (
          <div style={styles.subtle}>
            <Spinner /> Loading…
          </div>
        )}

        {!isLoading && hasSearched && listings.length === 0 && (
          <div style={styles.subtle}>No listings found.</div>
        )}

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 12,
          }}
        >
          {listings.map((item) => (
            <div key={item.id} style={styles.card}>
              <div style={{ marginBottom: 6 }}>
                <span style={styles.cardCategory}>{item.category}</span>
              </div>
              <div style={styles.cardName}>{item.name}</div>
              <div style={styles.cardDescription}>{item.description}</div>

              {/* Tags */}
              {item.tags && item.tags.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
                  {item.tags.map((tag) => (
                    <span key={tag} style={styles.tag}>
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
                <span style={styles.installCount}>
                  {item.install_count ?? 0} installs
                </span>
                <button
                  onClick={() => void install(item.id, item.name)}
                  disabled={installing === item.id}
                  style={{
                    ...styles.btnSmall,
                    opacity: installing === item.id ? 0.6 : 1,
                    cursor: installing === item.id ? 'not-allowed' : 'pointer',
                  }}
                >
                  {installing === item.id ? <Spinner /> : null}
                  Install
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {toast && <Toast message={toast} onDone={() => setToast('')} />}
    </div>
  );
};

// ── Main Page ────────────────────────────────────────────────────────────────

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'runner', label: 'Workflow Runner' },
  { id: 'stream', label: 'SSE Live Stream' },
  { id: 'marketplace', label: 'Marketplace Browser' },
];

const PlaygroundPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('runner');
  const [lastRunId, setLastRunId] = useState<string>('');

  const handleRunComplete = (runId: string) => {
    setLastRunId(runId);
  };

  return (
    <>
      <style>{`
        @keyframes pg-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
      <MainLayout
        title="API Playground"
        actions={
          <span style={{ color: '#6b7280', fontSize: 13 }}>
            Test workflows, stream events, explore the marketplace
          </span>
        }
      >
        {/* Tab bar */}
        <div
          style={{
            display: 'flex',
            gap: 4,
            marginBottom: 20,
            borderBottom: '1px solid #1f2937',
            paddingBottom: 0,
          }}
        >
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                background: 'none',
                border: 'none',
                padding: '10px 18px',
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: activeTab === tab.id ? 600 : 400,
                color: activeTab === tab.id ? '#60a5fa' : '#9ca3af',
                borderBottom: activeTab === tab.id ? '2px solid #60a5fa' : '2px solid transparent',
                marginBottom: -1,
                transition: 'color 0.15s',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab panels */}
        {activeTab === 'runner' && (
          <WorkflowRunner onRunComplete={handleRunComplete} />
        )}
        {activeTab === 'stream' && (
          <SseStream prefillRunId={lastRunId} />
        )}
        {activeTab === 'marketplace' && <MarketplaceBrowser />}
      </MainLayout>
    </>
  );
};

// ── Styles (inline, dark theme) ──────────────────────────────────────────────

const styles = {
  panel: {
    background: '#1f2937',
    border: '1px solid #374151',
    borderRadius: 10,
    padding: 24,
    maxWidth: 860,
  } as React.CSSProperties,

  panelTitle: {
    margin: '0 0 20px 0',
    fontSize: 18,
    fontWeight: 700,
    color: '#f9fafb',
  } as React.CSSProperties,

  field: {
    marginBottom: 16,
  } as React.CSSProperties,

  label: {
    display: 'block',
    marginBottom: 6,
    fontSize: 13,
    fontWeight: 600,
    color: '#9ca3af',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  } as React.CSSProperties,

  select: {
    width: '100%',
    padding: '8px 12px',
    background: '#111827',
    border: '1px solid #374151',
    borderRadius: 6,
    color: '#f3f4f6',
    fontSize: 14,
    cursor: 'pointer',
  } as React.CSSProperties,

  input: {
    width: '100%',
    padding: '8px 12px',
    background: '#111827',
    border: '1px solid #374151',
    borderRadius: 6,
    color: '#f3f4f6',
    fontSize: 14,
    boxSizing: 'border-box' as const,
  } as React.CSSProperties,

  textarea: {
    width: '100%',
    padding: '8px 12px',
    background: '#111827',
    border: '1px solid #374151',
    borderRadius: 6,
    color: '#f3f4f6',
    fontSize: 13,
    fontFamily: 'monospace',
    resize: 'vertical' as const,
    boxSizing: 'border-box' as const,
  } as React.CSSProperties,

  btn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '9px 20px',
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background 0.15s',
  } as React.CSSProperties,

  btnSmall: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '5px 12px',
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
  } as React.CSSProperties,

  resultBox: {
    marginTop: 16,
    padding: 14,
    background: '#111827',
    border: '1px solid #1f2937',
    borderRadius: 8,
  } as React.CSSProperties,

  resultRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginBottom: 6,
  } as React.CSSProperties,

  resultLabel: {
    fontSize: 12,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase' as const,
    width: 60,
    flexShrink: 0,
  } as React.CSSProperties,

  code: {
    fontFamily: 'monospace',
    fontSize: 13,
    color: '#34d399',
    wordBreak: 'break-all' as const,
  } as React.CSSProperties,

  subtle: {
    color: '#6b7280',
    fontSize: 13,
    display: 'flex',
    alignItems: 'center',
  } as React.CSSProperties,

  card: {
    background: '#111827',
    border: '1px solid #374151',
    borderRadius: 8,
    padding: 16,
    display: 'flex',
    flexDirection: 'column' as const,
  } as React.CSSProperties,

  cardCategory: {
    fontSize: 11,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
  } as React.CSSProperties,

  cardName: {
    fontSize: 15,
    fontWeight: 700,
    color: '#f9fafb',
    marginBottom: 4,
  } as React.CSSProperties,

  cardDescription: {
    fontSize: 13,
    color: '#9ca3af',
    lineHeight: 1.5,
  } as React.CSSProperties,

  tag: {
    fontSize: 11,
    padding: '2px 7px',
    background: '#1f2937',
    border: '1px solid #374151',
    borderRadius: 4,
    color: '#9ca3af',
  } as React.CSSProperties,

  installCount: {
    fontSize: 12,
    color: '#6b7280',
  } as React.CSSProperties,
};

export default PlaygroundPage;
