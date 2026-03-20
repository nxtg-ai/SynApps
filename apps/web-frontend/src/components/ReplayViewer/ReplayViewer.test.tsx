/**
 * ReplayViewer tests
 *
 * Strategy:
 *   - Mock apiService at the module level so no real network calls are made
 *   - Use @testing-library/react for rendering and user interaction
 *   - Cover: render, heading, replay button, replay history, step navigation,
 *     error states, and step display content
 */
import React from 'react';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ReplayViewer from './ReplayViewer';

// ── Mock apiService ──────────────────────────────────────────────────────────

vi.mock('../../services/ApiService', () => ({
  default: {
    replayExecution: vi.fn(),
    getReplayHistory: vi.fn(),
  },
}));

import apiService from '../../services/ApiService';

// Cast for easy per-test configuration
const mockReplayExecution = vi.mocked(apiService.replayExecution);
const mockGetReplayHistory = vi.mocked(apiService.getReplayHistory);

// ── Shared fixtures ──────────────────────────────────────────────────────────

const EXECUTION_ID = 'exec-abc-123';

const SAMPLE_RESULTS: Record<string, unknown> = {
  'node-start': { output: { text: 'hello' } },
  'node-llm': { output: { text: 'world' }, timing: 1.2 },
  'node-end': { output: { final: true } },
};

const SAMPLE_HISTORY = {
  execution_id: EXECUTION_ID,
  chain: ['orig-abc', 'replay-def', 'replay-ghi'],
  length: 3,
};

const SAMPLE_REPLAY_RESULT = {
  replay_run_id: 'replay-xyz-999',
  original_run_id: EXECUTION_ID,
  flow_id: 'flow-001',
  status: 'running',
};

// ── Default mock setup shared across most tests ──────────────────────────────

function setupDefaultMocks() {
  mockGetReplayHistory.mockResolvedValue(SAMPLE_HISTORY);
  mockReplayExecution.mockResolvedValue(SAMPLE_REPLAY_RESULT);
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('ReplayViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // Test 1 — renders without crashing with empty results
  it('renders without crashing when flowResults is empty', async () => {
    mockGetReplayHistory.mockResolvedValue({ execution_id: EXECUTION_ID, chain: [], length: 0 });

    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={{}} />);
    });

    // Component is in the DOM
    expect(screen.getByText('Step-through Replay')).toBeInTheDocument();
  });

  // Test 2 — heading is visible
  it('shows the "Step-through Replay" heading', async () => {
    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    expect(screen.getByText('Step-through Replay')).toBeInTheDocument();
  });

  // Test 3 — replay button calls replayExecution with the correct execution ID
  it('replay button calls replayExecution with the execution ID', async () => {
    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    const replayButton = screen.getByRole('button', { name: /replay this execution/i });
    expect(replayButton).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(replayButton);
    });

    expect(mockReplayExecution).toHaveBeenCalledTimes(1);
    expect(mockReplayExecution).toHaveBeenCalledWith(EXECUTION_ID);
  });

  // Test 4 — replay success banner appears with run ID after replay
  it('shows a success banner with replay_run_id after a successful replay', async () => {
    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /replay this execution/i }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('replay-success-banner')).toBeInTheDocument();
    });

    expect(screen.getByTestId('replay-success-banner')).toHaveTextContent(
      SAMPLE_REPLAY_RESULT.replay_run_id
    );
  });

  // Test 5 — replay history is loaded on mount
  it('loads replay history on mount and renders the chain', async () => {
    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    await waitFor(() => {
      expect(mockGetReplayHistory).toHaveBeenCalledWith(EXECUTION_ID);
    });

    // All run IDs in the chain should appear
    expect(await screen.findByText('orig-abc')).toBeInTheDocument();
    expect(screen.getByText('replay-def')).toBeInTheDocument();
    expect(screen.getByText('replay-ghi')).toBeInTheDocument();
  });

  // Test 6 — first item in history chain is labelled "(original)"
  it('marks the first chain entry as (original)', async () => {
    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    await waitFor(() => {
      expect(screen.getByTestId('replay-history-list')).toBeInTheDocument();
    });

    expect(screen.getByText('(original)')).toBeInTheDocument();
  });

  // Test 7 — step counter reflects correct total when results are provided
  it('shows the correct step count for provided flow results', async () => {
    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    const totalSteps = Object.keys(SAMPLE_RESULTS).length;

    // "Step 1 / 3" format
    expect(screen.getByText(`Step 1 / ${totalSteps}`)).toBeInTheDocument();
  });

  // Test 8 — Next button advances the step counter
  it('advances to the next step when the Next button is clicked', async () => {
    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    const totalSteps = Object.keys(SAMPLE_RESULTS).length;

    // Initial state
    expect(screen.getByText(`Step 1 / ${totalSteps}`)).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /next step/i }));
    });

    expect(screen.getByText(`Step 2 / ${totalSteps}`)).toBeInTheDocument();
  });

  // Test 9 — Prev button is disabled at the first step
  it('disables the Prev button when on the first step', async () => {
    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    expect(screen.getByRole('button', { name: /previous step/i })).toBeDisabled();
  });

  // Test 10 — error banner shown when replayExecution rejects
  it('shows an error banner when replayExecution rejects', async () => {
    mockReplayExecution.mockRejectedValueOnce(new Error('Backend unavailable'));

    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /replay this execution/i }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('replay-error-banner')).toBeInTheDocument();
    });

    expect(screen.getByTestId('replay-error-banner')).toHaveTextContent('Backend unavailable');
  });

  // Test 11 — history error is surfaced when getReplayHistory rejects
  it('shows a history error message when getReplayHistory rejects', async () => {
    mockGetReplayHistory.mockRejectedValueOnce(new Error('History unavailable'));

    await act(async () => {
      render(<ReplayViewer executionId={EXECUTION_ID} flowResults={SAMPLE_RESULTS} />);
    });

    await waitFor(() => {
      expect(screen.getByText('History unavailable')).toBeInTheDocument();
    });
  });
});
