/**
 * Unit tests for CostTrackerPage (N-81).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import CostTrackerPage from './CostTrackerPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EXEC_COST = {
  execution_id: 'exec-abc',
  flow_id: 'flow-xyz',
  node_costs: [
    { node_id: 'node-1', node_type: 'llm', tokens: 1500, cost_usd: 0.003 },
    { node_id: 'node-2', node_type: 'code', tokens: 0, cost_usd: 0.0 },
  ],
  total_usd: 0.003,
  total_tokens: 1500,
  created_at: '2024-01-15T10:00:00Z',
};

const EXEC_COST_NO_NODES = {
  ...EXEC_COST,
  node_costs: [],
};

const WORKFLOW_SUMMARY = {
  flow_id: 'flow-xyz',
  run_count: 3,
  total_usd: 0.009,
  avg_usd_per_run: 0.003,
  total_tokens: 4500,
  avg_tokens_per_run: 1500,
  records: [
    { execution_id: 'exec-1', flow_id: 'flow-xyz', node_costs: [], total_usd: 0.003, total_tokens: 1500, created_at: '2024-01-15T10:00:00Z' },
    { execution_id: 'exec-2', flow_id: 'flow-xyz', node_costs: [], total_usd: 0.003, total_tokens: 1500, created_at: '2024-01-14T10:00:00Z' },
    { execution_id: 'exec-3', flow_id: 'flow-xyz', node_costs: [], total_usd: 0.003, total_tokens: 1500, created_at: '2024-01-13T10:00:00Z' },
  ],
};

const WORKFLOW_SUMMARY_EMPTY = {
  flow_id: 'flow-new',
  run_count: 0,
  total_usd: 0,
  avg_usd_per_run: 0,
  total_tokens: 0,
  avg_tokens_per_run: 0,
  records: [],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <CostTrackerPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CostTrackerPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and both sections', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('exec-cost-section')).toBeInTheDocument();
    expect(screen.getByTestId('workflow-cost-section')).toBeInTheDocument();
  });

  it('exec lookup button disabled when input is empty', () => {
    renderPage();
    expect(screen.getByTestId('exec-cost-btn')).toBeDisabled();
  });

  it('workflow lookup button disabled when input is empty', () => {
    renderPage();
    expect(screen.getByTestId('workflow-cost-btn')).toBeDisabled();
  });

  it('shows exec cost result with node table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => EXEC_COST } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('exec-id-input'), { target: { value: 'exec-abc' } });
    fireEvent.click(screen.getByTestId('exec-cost-btn'));
    await waitFor(() => expect(screen.getByTestId('exec-cost-result')).toBeInTheDocument());
    expect(screen.getByTestId('exec-total-usd')).toBeInTheDocument();
    expect(screen.getByTestId('exec-total-tokens')).toBeInTheDocument();
    expect(screen.getByTestId('node-cost-table')).toBeInTheDocument();
    expect(screen.getAllByTestId('node-cost-row')).toHaveLength(2);
  });

  it('shows no-node-costs when node_costs is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => EXEC_COST_NO_NODES } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('exec-id-input'), { target: { value: 'exec-abc' } });
    fireEvent.click(screen.getByTestId('exec-cost-btn'));
    await waitFor(() => expect(screen.getByTestId('no-node-costs')).toBeInTheDocument());
  });

  it('shows exec-cost-error on 404', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 404 } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('exec-id-input'), { target: { value: 'bad-id' } });
    fireEvent.click(screen.getByTestId('exec-cost-btn'));
    await waitFor(() => expect(screen.getByTestId('exec-cost-error')).toBeInTheDocument());
    expect(screen.getByTestId('exec-cost-error').textContent).toContain('No cost record');
  });

  it('shows exec-cost-error on 500', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('exec-id-input'), { target: { value: 'exec-abc' } });
    fireEvent.click(screen.getByTestId('exec-cost-btn'));
    await waitFor(() => expect(screen.getByTestId('exec-cost-error')).toBeInTheDocument());
  });

  it('shows workflow cost summary with stats and run history', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => WORKFLOW_SUMMARY } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-xyz' } });
    fireEvent.click(screen.getByTestId('workflow-cost-btn'));
    await waitFor(() => expect(screen.getByTestId('workflow-cost-result')).toBeInTheDocument());
    expect(screen.getByTestId('stat-runs')).toBeInTheDocument();
    expect(screen.getByTestId('stat-total-usd')).toBeInTheDocument();
    expect(screen.getByTestId('run-history-table')).toBeInTheDocument();
    expect(screen.getAllByTestId('run-history-row')).toHaveLength(3);
  });

  it('shows no-runs when workflow has zero cost records', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => WORKFLOW_SUMMARY_EMPTY } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-new' } });
    fireEvent.click(screen.getByTestId('workflow-cost-btn'));
    await waitFor(() => expect(screen.getByTestId('no-runs')).toBeInTheDocument());
  });

  it('shows workflow-cost-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 403 } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-xyz' } });
    fireEvent.click(screen.getByTestId('workflow-cost-btn'));
    await waitFor(() => expect(screen.getByTestId('workflow-cost-error')).toBeInTheDocument());
  });

  it('formats large token counts with K suffix', async () => {
    const bigSummary = { ...WORKFLOW_SUMMARY, total_tokens: 1_500_000, avg_tokens_per_run: 500_000 };
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => bigSummary } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-xyz' } });
    fireEvent.click(screen.getByTestId('workflow-cost-btn'));
    await waitFor(() => screen.getByTestId('stat-total-tokens'));
    expect(screen.getByTestId('stat-total-tokens').textContent).toContain('1.50M');
  });
});
