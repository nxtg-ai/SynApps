/**
 * ReplayViewer — Step-through replay UI for a completed workflow execution.
 *
 * Responsibilities:
 *   - Animate through each node's execution step with play/pause/prev/next controls
 *   - Trigger a new replay via the backend and surface the resulting run ID
 *   - Display the full replay chain (original + all replays) for the execution
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import apiService from '../../services/ApiService';

// ── Types ────────────────────────────────────────────────────────────────────

interface ReplayStep {
  nodeId: string;
  output: unknown;
  /** Unix timestamp seconds, present when the result includes timing data */
  timing?: number;
}

interface ReplayResult {
  replay_run_id: string;
  original_run_id: string;
  flow_id: string;
  status: string;
}

interface ReplayHistory {
  execution_id: string;
  chain: string[];
  length: number;
}

type StepState = 'completed' | 'active' | 'pending';

// ── Helper: derive an ordered step list from the raw results map ─────────────

function buildSteps(flowResults: Record<string, unknown>): ReplayStep[] {
  return Object.entries(flowResults).map(([nodeId, value]) => {
    const entry = value as Record<string, unknown>;
    return {
      nodeId,
      output: entry?.output ?? entry,
      timing: typeof entry?.timing === 'number' ? entry.timing : undefined,
    };
  });
}

// ── Component ────────────────────────────────────────────────────────────────

interface ReplayViewerProps {
  executionId: string;
  flowResults: Record<string, unknown>;
}

const PLAY_INTERVAL_MS = 800;

const ReplayViewer: React.FC<ReplayViewerProps> = ({ executionId, flowResults }) => {
  const steps = buildSteps(flowResults);
  const totalSteps = steps.length;

  // Playback state
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  // Replay trigger state
  const [replayResult, setReplayResult] = useState<ReplayResult | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [isReplaying, setIsReplaying] = useState<boolean>(false);

  // Replay history state
  const [history, setHistory] = useState<ReplayHistory | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Playback controls ────────────────────────────────────────────────────

  const stopPlayback = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  const startPlayback = useCallback(() => {
    if (totalSteps === 0) return;
    setIsPlaying(true);
    intervalRef.current = setInterval(() => {
      setCurrentIndex((prev) => {
        const next = prev + 1;
        if (next >= totalSteps) {
          stopPlayback();
          return prev;
        }
        return next;
      });
    }, PLAY_INTERVAL_MS);
  }, [totalSteps, stopPlayback]);

  const handlePlayPause = useCallback(() => {
    if (isPlaying) {
      stopPlayback();
    } else {
      // If already at the last step, restart from 0
      if (currentIndex >= totalSteps - 1) {
        setCurrentIndex(0);
      }
      startPlayback();
    }
  }, [isPlaying, currentIndex, totalSteps, startPlayback, stopPlayback]);

  const handlePrev = useCallback(() => {
    stopPlayback();
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  }, [stopPlayback]);

  const handleNext = useCallback(() => {
    stopPlayback();
    setCurrentIndex((prev) => Math.min(totalSteps - 1, prev + 1));
  }, [stopPlayback, totalSteps]);

  // Cleanup interval on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  // ── Replay trigger ───────────────────────────────────────────────────────

  const handleReplay = useCallback(async () => {
    setIsReplaying(true);
    setReplayResult(null);
    setReplayError(null);
    try {
      const result = await apiService.replayExecution(executionId);
      setReplayResult(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Replay request failed';
      setReplayError(message);
    } finally {
      setIsReplaying(false);
    }
  }, [executionId]);

  // ── Replay history ───────────────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    apiService
      .getReplayHistory(executionId)
      .then((data) => {
        if (!cancelled) setHistory(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Failed to load replay history';
          setHistoryError(message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [executionId]);

  // ── Step state helper ────────────────────────────────────────────────────

  const getStepState = (index: number): StepState => {
    if (index < currentIndex) return 'completed';
    if (index === currentIndex) return 'active';
    return 'pending';
  };

  // ── Render ───────────────────────────────────────────────────────────────

  const hasSteps = totalSteps > 0;
  const atEnd = currentIndex >= totalSteps - 1;

  return (
    <div className="flex flex-col gap-4 bg-gray-900 text-gray-100 rounded-lg p-4">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <h3 className="text-base font-semibold text-blue-400 flex items-center gap-2">
        Step-through Replay
      </h3>

      {/* ── Playback controls ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <button
          onClick={handlePrev}
          disabled={!hasSteps || currentIndex === 0}
          className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors"
          aria-label="Previous step"
        >
          Prev
        </button>

        <button
          onClick={handlePlayPause}
          disabled={!hasSteps}
          className="px-4 py-1 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? 'Pause' : atEnd && hasSteps ? 'Restart' : 'Play'}
        </button>

        <button
          onClick={handleNext}
          disabled={!hasSteps || atEnd}
          className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors"
          aria-label="Next step"
        >
          Next
        </button>

        {hasSteps && (
          <span className="ml-auto text-sm text-gray-400">
            Step {currentIndex + 1} / {totalSteps}
          </span>
        )}
      </div>

      {/* ── Step list ─────────────────────────────────────────────────────── */}
      {hasSteps ? (
        <div className="flex flex-col gap-2 max-h-80 overflow-y-auto pr-1">
          {steps.map((step, index) => {
            const state = getStepState(index);
            return (
              <div
                key={step.nodeId}
                data-testid={`replay-step-${index}`}
                onClick={() => {
                  stopPlayback();
                  setCurrentIndex(index);
                }}
                className={[
                  'rounded p-3 border cursor-pointer transition-all',
                  state === 'active'
                    ? 'border-blue-500 bg-gray-800 shadow-md shadow-blue-900/30'
                    : state === 'completed'
                      ? 'border-gray-600 bg-gray-800/60 opacity-80'
                      : 'border-gray-700 bg-gray-800/30 opacity-50',
                ].join(' ')}
              >
                <div className="flex items-center gap-2 mb-1">
                  {/* State indicator */}
                  {state === 'completed' && (
                    <span className="text-green-400 text-xs select-none" aria-label="completed">
                      ✓
                    </span>
                  )}
                  {state === 'active' && (
                    <span className="text-blue-400 text-xs select-none" aria-label="active">
                      →
                    </span>
                  )}
                  {state === 'pending' && (
                    <span className="text-gray-500 text-xs select-none" aria-label="pending">
                      ○
                    </span>
                  )}

                  <span className="text-xs text-gray-400">Step {index + 1}</span>

                  <span
                    className={[
                      'text-sm font-mono',
                      state === 'active' ? 'text-blue-300' : 'text-gray-300',
                    ].join(' ')}
                  >
                    {step.nodeId}
                  </span>

                  {state === 'active' && (
                    <span className="ml-auto text-xs text-blue-400">(current)</span>
                  )}

                  {step.timing !== undefined && (
                    <span className="ml-auto text-xs text-gray-500">{step.timing}s</span>
                  )}
                </div>

                {/* Output — only render for active or completed steps */}
                {state !== 'pending' && (
                  <div className="mt-1 text-xs text-gray-400">
                    <span className="text-gray-500">Output: </span>
                    <pre className="inline whitespace-pre-wrap break-all text-gray-300">
                      {JSON.stringify(step.output, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-gray-500 italic">No execution steps available.</p>
      )}

      {/* ── Divider ───────────────────────────────────────────────────────── */}
      <div className="border-t border-gray-700" />

      {/* ── Replay trigger ────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2">
        <button
          onClick={handleReplay}
          disabled={isReplaying}
          className="w-full py-2 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
          aria-label="Replay this execution"
        >
          {isReplaying ? 'Starting replay...' : 'Replay This Execution'}
        </button>

        {replayResult && (
          <div
            data-testid="replay-success-banner"
            className="rounded bg-green-900/40 border border-green-700 px-3 py-2 text-xs text-green-300"
          >
            Replay started — run ID:{' '}
            <span className="font-mono text-green-200">{replayResult.replay_run_id}</span>
          </div>
        )}

        {replayError && (
          <div
            data-testid="replay-error-banner"
            className="rounded bg-red-900/40 border border-red-700 px-3 py-2 text-xs text-red-300"
          >
            {replayError}
          </div>
        )}
      </div>

      {/* ── Replay history ────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium text-gray-300">
          Replay History
          {history && (
            <span className="ml-2 text-gray-500 font-normal">{history.length} total</span>
          )}
        </h4>

        {historyError && (
          <p className="text-xs text-red-400">{historyError}</p>
        )}

        {history && history.chain.length > 0 ? (
          <ul className="flex flex-col gap-1" data-testid="replay-history-list">
            {history.chain.map((runId, index) => (
              <li
                key={runId}
                className="flex items-center gap-2 text-xs font-mono text-gray-300"
              >
                <span className="text-gray-500 w-3">{index === 0 ? '•' : '↳'}</span>
                <span>{runId}</span>
                {index === 0 && (
                  <span className="text-gray-500 ml-1">(original)</span>
                )}
                {runId === replayResult?.replay_run_id && (
                  <span className="text-blue-400 ml-1">(just started)</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          !historyError && (
            <p className="text-xs text-gray-500">
              {history ? 'No replay history yet.' : 'Loading history...'}
            </p>
          )
        )}
      </div>
    </div>
  );
};

export default ReplayViewer;
