/**
 * Unit tests for RunTracePage (N-86).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import RunTracePage from './RunTracePage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RUNS_TWO = {
  items: [
    { run_id: 'run-1', flow_id: 'flow-a', status: 'success', created_at: '2024-01-10T09:00:00Z' },
    { run_id: 'run-2', flow_id: 'flow-a', status: 'failed', created_at: '2024-01-10T10:00:00Z' },
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

const RUNS_EMPTY = { items: [], total: 0, page: 1, page_size: 20 };

const TRACE = {
  run_id: 'run-1',
  flow_id: 'flow-a',
  nodes: [
    { node_id: 'start-1', node_type: 'start', status: 'success', duration_ms: 5 },
    { node_id: 'llm-1', node_type: 'llm', status: 'success', duration_ms: 820 },
    { node_id: 'end-1', node_type: 'end', status: 'success', duration_ms: 2 },
  ],
};

const TRACE_EMPTY = { run_id: 'run-1', flow_id: 'flow-a', nodes: [] };

const DIFF_RESULT = {
  same_flow: true,
  nodes_added: [],
  nodes_removed: ['old-node'],
  nodes_changed: ['llm-1'],
};

const RERUN_RESULT = { run_id: 'run-new-123', source_run_id: 'run-1' };

function renderPage() {
  return render(
    <MemoryRouter>
      <RunTracePage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RunTracePage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and no-run-selected state', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => RUNS_TWO } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('no-run-selected')).toBeInTheDocument());
  });

  it('shows run rows in table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => RUNS_TWO } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('runs-table')).toBeInTheDocument());
    expect(screen.getAllByTestId('run-row')).toHaveLength(2);
    expect(screen.getByText('run-1')).toBeInTheDocument();
    expect(screen.getByText('run-2')).toBeInTheDocument();
  });

  it('shows no-runs when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => RUNS_EMPTY } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-runs')).toBeInTheDocument());
  });

  it('shows list-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('list-error')).toBeInTheDocument());
  });

  it('clicking a run loads its trace', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => RUNS_TWO } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => TRACE } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('runs-table'));
    fireEvent.click(screen.getAllByTestId('run-row')[0]);
    await waitFor(() => expect(screen.getByTestId('trace-panel')).toBeInTheDocument());
    expect(screen.getByTestId('trace-nodes')).toBeInTheDocument();
    expect(screen.getAllByTestId('trace-node')).toHaveLength(3);
  });

  it('shows no-trace-nodes when trace has no nodes', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => RUNS_TWO } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => TRACE_EMPTY } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('runs-table'));
    fireEvent.click(screen.getAllByTestId('run-row')[0]);
    await waitFor(() => expect(screen.getByTestId('no-trace-nodes')).toBeInTheDocument());
  });

  it('shows trace-error on trace fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => RUNS_TWO } as Response)
      .mockResolvedValueOnce({ ok: false, status: 404 } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('runs-table'));
    fireEvent.click(screen.getAllByTestId('run-row')[0]);
    await waitFor(() => expect(screen.getByTestId('trace-error')).toBeInTheDocument());
  });

  it('diff shows removed/changed node counts', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => RUNS_TWO } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => TRACE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => DIFF_RESULT } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('runs-table'));
    fireEvent.click(screen.getAllByTestId('run-row')[0]);
    await waitFor(() => screen.getByTestId('trace-panel'));
    fireEvent.change(screen.getByTestId('diff-run-input'), { target: { value: 'run-2' } });
    fireEvent.click(screen.getByTestId('diff-btn'));
    await waitFor(() => expect(screen.getByTestId('diff-result')).toBeInTheDocument());
  });

  it('rerun shows new run ID on success', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => RUNS_TWO } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => TRACE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => RERUN_RESULT } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('runs-table'));
    fireEvent.click(screen.getAllByTestId('run-row')[0]);
    await waitFor(() => screen.getByTestId('trace-panel'));
    fireEvent.click(screen.getByTestId('rerun-btn'));
    await waitFor(() => expect(screen.getByTestId('rerun-result')).toBeInTheDocument());
    expect(screen.getByTestId('rerun-result').textContent).toContain('run-new-123');
  });

  it('rerun shows error on invalid JSON input', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => RUNS_TWO } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => TRACE } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('runs-table'));
    fireEvent.click(screen.getAllByTestId('run-row')[0]);
    await waitFor(() => screen.getByTestId('trace-panel'));
    fireEvent.change(screen.getByTestId('rerun-input'), { target: { value: 'not-json' } });
    fireEvent.click(screen.getByTestId('rerun-btn'));
    await waitFor(() => expect(screen.getByTestId('rerun-error')).toBeInTheDocument());
    expect(screen.getByTestId('rerun-error').textContent).toContain('valid JSON');
  });
});
