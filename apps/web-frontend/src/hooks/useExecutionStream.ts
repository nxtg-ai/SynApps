/**
 * useExecutionStream — N-32 Real-Time SSE Execution Streaming
 *
 * React hook that subscribes to the GET /api/v1/executions/:id/stream
 * Server-Sent Events endpoint and surfaces node-by-node execution progress.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SSEEventType =
  | 'node_started'
  | 'node_completed'
  | 'node_failed'
  | 'execution_complete';

export interface ExecutionEvent {
  type: SSEEventType;
  run_id?: string;
  node_id?: string;
  node_type?: string;
  timestamp?: number;
  attempt?: number;
  error?: string | null;
  duration_ms?: number | null;
  /** Only present on execution_complete */
  status?: 'success' | 'error';
}

export type StreamStatus = 'idle' | 'connecting' | 'streaming' | 'complete' | 'error';

export interface UseExecutionStreamResult {
  /** All events received so far (oldest first). */
  events: ExecutionEvent[];
  /** Current lifecycle status of the stream. */
  status: StreamStatus;
  /** True once an execution_complete event has been received. */
  isComplete: boolean;
  /** Final execution status ('success' | 'error'), available after isComplete. */
  finalStatus: 'success' | 'error' | null;
  /** Manually (re-)connect.  Called automatically when runId changes. */
  connect: () => void;
  /** Close the EventSource and reset state. */
  disconnect: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Subscribe to real-time SSE execution events for *runId*.
 *
 * @param runId   The workflow run ID to stream events for.  Pass `null` to
 *                start in disconnected state.
 * @param baseUrl Base URL for the API (defaults to `/api/v1`).
 */
export function useExecutionStream(
  runId: string | null,
  baseUrl = '/api/v1',
): UseExecutionStreamResult {
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [finalStatus, setFinalStatus] = useState<'success' | 'error' | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const runIdRef = useRef<string | null>(null);

  const disconnect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setStatus('idle');
  }, []);

  const connect = useCallback(() => {
    if (!runId) return;
    // Close any existing stream
    if (esRef.current) {
      esRef.current.close();
    }
    runIdRef.current = runId;
    setEvents([]);
    setFinalStatus(null);
    setStatus('connecting');

    const url = `${baseUrl}/executions/${encodeURIComponent(runId)}/stream`;
    const es = new EventSource(url);
    esRef.current = es;

    const addEvent = (type: SSEEventType, raw: string) => {
      try {
        const data = JSON.parse(raw) as Omit<ExecutionEvent, 'type'>;
        setEvents((prev) => [...prev, { type, ...data }]);
      } catch {
        // ignore unparseable data
      }
    };

    es.onopen = () => {
      setStatus('streaming');
    };

    es.addEventListener('node_started', (e) => {
      addEvent('node_started', (e as MessageEvent).data);
    });

    es.addEventListener('node_completed', (e) => {
      addEvent('node_completed', (e as MessageEvent).data);
    });

    es.addEventListener('node_failed', (e) => {
      addEvent('node_failed', (e as MessageEvent).data);
    });

    es.addEventListener('execution_complete', (e) => {
      addEvent('execution_complete', (e as MessageEvent).data);
      try {
        const payload = JSON.parse((e as MessageEvent).data);
        setFinalStatus(payload.status ?? null);
      } catch {
        // ignore
      }
      setStatus('complete');
      es.close();
      esRef.current = null;
    });

    es.onerror = () => {
      // EventSource auto-reconnects on transient errors; only mark error on
      // CLOSED state (browser gave up).
      if (es.readyState === EventSource.CLOSED) {
        setStatus('error');
        esRef.current = null;
      }
    };
  }, [runId, baseUrl]);

  // Auto-connect when runId changes
  useEffect(() => {
    if (runId) {
      connect();
    } else {
      disconnect();
    }
    return disconnect;
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    events,
    status,
    isComplete: status === 'complete',
    finalStatus,
    connect,
    disconnect,
  };
}
