/**
 * Unit tests for WorkflowDebugPage (N-73).
 */
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkflowDebugPage from './WorkflowDebugPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SESSION_RUNNING = {
  session: {
    session_id: 'sess-abc-123',
    run_id: 'run-001',
    flow_id: 'flow-abc',
    status: 'running',
    breakpoints: ['node-2'],
    current_node_id: null,
    current_node_input: {},
    current_node_output: {},
    execution_history: [],
    created_at: 1704067200,
    paused_at: null,
  },
};

const SESSION_PAUSED = {
  session: {
    ...SESSION_RUNNING.session,
    status: 'paused',
    current_node_id: 'node-2',
    current_node_input: { prompt: 'hello' },
    current_node_output: { text: 'world' },
    execution_history: [
      { node_id: 'node-1', input: {}, output: {}, skipped: false, timestamp: 1704067201 },
    ],
    paused_at: 1704067202,
  },
};

const SESSION_COMPLETED = {
  session: {
    ...SESSION_RUNNING.session,
    status: 'completed',
    execution_history: [
      { node_id: 'node-1', input: {}, output: {}, skipped: false, timestamp: 1704067201 },
      { node_id: 'node-2', input: {}, output: {}, skipped: true,  timestamp: 1704067202 },
    ],
    paused_at: null,
  },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowDebugPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowDebugPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.useFakeTimers();
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and start form', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('start-form')).toBeInTheDocument();
    expect(screen.getByTestId('flow-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('breakpoint-input')).toBeInTheDocument();
  });

  it('start-debug-btn is disabled when flow ID is empty', () => {
    renderPage();
    expect(screen.getByTestId('start-debug-btn')).toBeDisabled();
  });

  it('starts session and shows session panel', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => SESSION_RUNNING,
    } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('session-panel')).toBeInTheDocument());
    expect(screen.getByTestId('session-status')).toHaveTextContent('running');
  });

  it('shows session controls when not terminal', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SESSION_RUNNING } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('session-controls')).toBeInTheDocument());
    expect(screen.getByTestId('continue-btn')).toBeInTheDocument();
    expect(screen.getByTestId('skip-btn')).toBeInTheDocument();
    expect(screen.getByTestId('abort-btn')).toBeInTheDocument();
  });

  it('continue and skip buttons are disabled when not paused', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SESSION_RUNNING } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('continue-btn')).toBeDisabled());
    expect(screen.getByTestId('skip-btn')).toBeDisabled();
  });

  it('shows node I/O when session is paused', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SESSION_PAUSED } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('node-io')).toBeInTheDocument());
    expect(screen.getByTestId('node-input')).toHaveTextContent('hello');
    expect(screen.getByTestId('node-output')).toHaveTextContent('world');
  });

  it('renders execution history entries', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SESSION_PAUSED } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getAllByTestId('history-entry')).toHaveLength(1));
    expect(screen.getByText('node-1')).toBeInTheDocument();
  });

  it('shows skipped-badge for skipped history entries', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SESSION_COMPLETED } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('skipped-badge')).toBeInTheDocument());
  });

  it('shows new-session-btn for completed session', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SESSION_COMPLETED } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('new-session-btn')).toBeInTheDocument());
  });

  it('clicking new-session-btn returns to start form', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SESSION_COMPLETED } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('new-session-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('new-session-btn'));
    expect(screen.getByTestId('start-form')).toBeInTheDocument();
  });

  it('opens breakpoints editor on edit click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SESSION_RUNNING } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('edit-breakpoints-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-breakpoints-btn'));
    expect(screen.getByTestId('breakpoints-editor')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-breakpoints-btn')).toBeInTheDocument();
  });

  it('shows error on start failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 404, text: async () => '' } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'bad-flow' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('debug-error')).toBeInTheDocument());
  });

  it('polls session status via interval', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => SESSION_RUNNING } as Response)  // start
      .mockResolvedValueOnce({ ok: true, json: async () => SESSION_PAUSED } as Response);  // poll

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('start-form'));

    await waitFor(() => expect(screen.getByTestId('session-panel')).toBeInTheDocument());

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    await waitFor(() => expect(screen.getByTestId('session-status')).toHaveTextContent('paused'));
  });
});
