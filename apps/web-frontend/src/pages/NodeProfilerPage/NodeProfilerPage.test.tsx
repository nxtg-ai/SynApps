/**
 * Unit tests for NodeProfilerPage (N-70).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import NodeProfilerPage from './NodeProfilerPage';

// ---------------------------------------------------------------------------
// Mock MainLayout to avoid full layout rendering in unit tests
// ---------------------------------------------------------------------------
vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const WORKFLOW_PROFILE = {
  flow_id: 'flow-abc',
  profiled_at: 1700000000,
  total_node_types_profiled: 2,
  nodes: [
    { node_id: 'node-1', run_count: 5, avg_ms: 120, p50_ms: 115, p95_ms: 180, p99_ms: 200, min_ms: 80, max_ms: 210 },
    { node_id: 'node-2', run_count: 5, avg_ms: 45,  p50_ms: 40,  p95_ms: 70,  p99_ms: 80,  min_ms: 30, max_ms: 90 },
  ],
};

const EXECUTION_PROFILE = {
  execution_id: 'run-xyz',
  total_duration_ms: 320,
  bottleneck_node_id: 'node-1',
  nodes: [
    { node_id: 'node-1', duration_ms: 250, is_bottleneck: true },
    { node_id: 'node-2', duration_ms: 70,  is_bottleneck: false },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <NodeProfilerPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NodeProfilerPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and both panels', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('workflow-profile-panel')).toBeInTheDocument();
    expect(screen.getByTestId('execution-profile-panel')).toBeInTheDocument();
  });

  it('renders workflow ID input and Profile button', () => {
    renderPage();
    expect(screen.getByTestId('workflow-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('fetch-workflow-btn')).toBeInTheDocument();
  });

  it('renders execution ID input and Profile button', () => {
    renderPage();
    expect(screen.getByTestId('execution-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('fetch-execution-btn')).toBeInTheDocument();
  });

  it('fetch-workflow-btn is disabled when input is empty', () => {
    renderPage();
    expect(screen.getByTestId('fetch-workflow-btn')).toBeDisabled();
  });

  it('fetch-execution-btn is disabled when input is empty', () => {
    renderPage();
    expect(screen.getByTestId('fetch-execution-btn')).toBeDisabled();
  });

  it('fetches workflow profile and renders table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => WORKFLOW_PROFILE,
    } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('workflow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('fetch-workflow-btn'));

    await waitFor(() => expect(screen.getByTestId('workflow-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('workflow-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('node-1')).toBeInTheDocument();
    expect(screen.getByText('node-2')).toBeInTheDocument();
  });

  it('shows workflow error on non-ok response', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({}),
    } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('workflow-id-input'), { target: { value: 'bad-id' } });
    fireEvent.click(screen.getByTestId('fetch-workflow-btn'));

    await waitFor(() => expect(screen.getByTestId('workflow-error')).toBeInTheDocument());
  });

  it('fetches execution profile and renders timeline with bottleneck', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => EXECUTION_PROFILE,
    } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('execution-id-input'), { target: { value: 'run-xyz' } });
    fireEvent.click(screen.getByTestId('fetch-execution-btn'));

    await waitFor(() => expect(screen.getByTestId('execution-timeline')).toBeInTheDocument());
    expect(screen.getByTestId('bottleneck-node')).toBeInTheDocument();
    expect(screen.getAllByText(/bottleneck/).length).toBeGreaterThanOrEqual(1);
  });

  it('shows 404 message when execution not found', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({}),
    } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('execution-id-input'), { target: { value: 'missing' } });
    fireEvent.click(screen.getByTestId('fetch-execution-btn'));

    await waitFor(() => expect(screen.getByTestId('execution-error')).toBeInTheDocument());
    expect(screen.getByTestId('execution-error')).toHaveTextContent(/not found/i);
  });

  it('shows empty state when workflow has no node data', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...WORKFLOW_PROFILE, nodes: [], total_node_types_profiled: 0 }),
    } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('workflow-id-input'), { target: { value: 'flow-empty' } });
    fireEvent.click(screen.getByTestId('fetch-workflow-btn'));

    await waitFor(() => expect(screen.getByTestId('workflow-empty')).toBeInTheDocument());
  });

  it('shows empty state when execution has no node data', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...EXECUTION_PROFILE, nodes: [], bottleneck_node_id: null, total_duration_ms: 0 }),
    } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('execution-id-input'), { target: { value: 'run-empty' } });
    fireEvent.click(screen.getByTestId('fetch-execution-btn'));

    await waitFor(() => expect(screen.getByTestId('execution-empty')).toBeInTheDocument());
  });

  it('sends Authorization header with stored token', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => WORKFLOW_PROFILE,
    } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('workflow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('fetch-workflow-btn'));

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    const [, opts] = vi.mocked(fetch).mock.calls[0];
    expect((opts as RequestInit).headers).toMatchObject({ Authorization: 'Bearer test-token' });
  });
});
