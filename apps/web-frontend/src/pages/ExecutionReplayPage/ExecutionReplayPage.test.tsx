/**
 * Unit tests for ExecutionReplayPage (N-90).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ExecutionReplayPage from './ExecutionReplayPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const REPLAY_RESULT = {
  replay_run_id: 'replay-abc-123',
  original_run_id: 'exec-original-1',
  flow_id: 'flow-xyz',
  status: 'started',
};

const HISTORY_WITH_CHAIN = {
  execution_id: 'exec-original-1',
  chain: ['exec-original-1', 'replay-abc-123', 'replay-def-456'],
  length: 3,
};

const HISTORY_EMPTY = {
  execution_id: 'exec-new',
  chain: [],
  length: 0,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ExecutionReplayPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ExecutionReplayPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('replay btn disabled when exec-id empty', () => {
    renderPage();
    expect(screen.getByTestId('replay-btn')).toBeDisabled();
  });

  it('history btn disabled when history-id empty', () => {
    renderPage();
    expect(screen.getByTestId('history-btn')).toBeDisabled();
  });

  it('successful replay shows replay-result with run id', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => REPLAY_RESULT,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('exec-id-input'), {
      target: { value: 'exec-original-1' },
    });
    fireEvent.submit(screen.getByTestId('replay-form'));
    await waitFor(() => expect(screen.getByTestId('replay-result')).toBeInTheDocument());
    expect(screen.getByTestId('replay-run-id').textContent).toContain('replay-abc-123');
  });

  it('shows replay-error on 404', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Execution not found' }),
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('exec-id-input'), {
      target: { value: 'bad-id' },
    });
    fireEvent.submit(screen.getByTestId('replay-form'));
    await waitFor(() => expect(screen.getByTestId('replay-error')).toBeInTheDocument());
    expect(screen.getByTestId('replay-error').textContent).toContain('Execution not found');
  });

  it('loads replay history with chain items', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => HISTORY_WITH_CHAIN,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('history-id-input'), {
      target: { value: 'exec-original-1' },
    });
    fireEvent.submit(screen.getByTestId('history-form'));
    await waitFor(() => expect(screen.getByTestId('history-result')).toBeInTheDocument());
    expect(screen.getAllByTestId('chain-item')).toHaveLength(3);
    // First item should have "original" badge
    expect(screen.getByText('original')).toBeInTheDocument();
    expect(screen.getByText('exec-original-1')).toBeInTheDocument();
  });

  it('shows no-chain when chain is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => HISTORY_EMPTY,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('history-id-input'), {
      target: { value: 'exec-new' },
    });
    fireEvent.submit(screen.getByTestId('history-form'));
    await waitFor(() => expect(screen.getByTestId('no-chain')).toBeInTheDocument());
  });

  it('shows history-error on history fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Not found' }),
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('history-id-input'), {
      target: { value: 'missing' },
    });
    fireEvent.submit(screen.getByTestId('history-form'));
    await waitFor(() => expect(screen.getByTestId('history-error')).toBeInTheDocument());
  });

  it('chain-item count matches history length', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => HISTORY_WITH_CHAIN,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('history-id-input'), {
      target: { value: 'exec-original-1' },
    });
    fireEvent.submit(screen.getByTestId('history-form'));
    await waitFor(() => screen.getByTestId('history-result'));
    expect(screen.getAllByTestId('chain-item')).toHaveLength(HISTORY_WITH_CHAIN.length);
  });
});
