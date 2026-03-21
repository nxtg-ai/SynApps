/**
 * Unit tests for MonitoringAlertsPage (N-109).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import MonitoringAlertsPage from './MonitoringAlertsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RULE_1 = {
  rule_id: 'rule-001',
  metric: 'error_rate',
  operator: '>',
  threshold: 0.1,
  action_type: 'log',
  enabled: true,
  workflow_id: '*',
};

const RULE_2 = {
  rule_id: 'rule-002',
  metric: 'avg_duration_ms',
  operator: '>',
  threshold: 5000,
  action_type: 'webhook',
  enabled: false,
};

const RULES_LIST = { rules: [RULE_1, RULE_2], total: 2 };
const HEALTH_LIST = {
  workflows: [
    { flow_id: 'flow-abc', success_rate: 0.95, total_runs: 100, avg_duration_ms: 250 },
    { flow_id: 'flow-xyz', success_rate: 0.5, total_runs: 20, avg_duration_ms: 800 },
  ],
  total: 2,
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}
function makeNoContent() {
  return { ok: true, status: 204, json: async () => ({}) } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function setupMountMocks() {
  vi.mocked(fetch)
    .mockResolvedValueOnce(makeOk(RULES_LIST))
    .mockResolvedValueOnce(makeOk(HEALTH_LIST));
}

function renderPage() {
  return render(
    <MemoryRouter>
      <MonitoringAlertsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MonitoringAlertsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'tok');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', () => {
    vi.mocked(fetch).mockResolvedValue(makeOk({ rules: [], workflows: [] }));
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('loads and shows alert rules on mount', async () => {
    setupMountMocks();
    renderPage();
    await waitFor(() => screen.getByTestId('rules-table'));
    const rows = screen.getAllByTestId('rule-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('error_rate');
  });

  it('shows no-rules when list is empty', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ rules: [], total: 0 }))
      .mockResolvedValueOnce(makeOk(HEALTH_LIST));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-rules')).toBeInTheDocument());
  });

  it('shows list-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeErr(500, 'DB error'))
      .mockResolvedValueOnce(makeOk(HEALTH_LIST));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('list-error')).toBeInTheDocument());
    expect(screen.getByTestId('list-error').textContent).toContain('DB error');
  });

  it('creates a new alert rule', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ rules: [], total: 0 })) // initial list
      .mockResolvedValueOnce(makeOk(HEALTH_LIST))              // initial health
      .mockResolvedValueOnce(makeOk({ rule: RULE_1 }))         // POST create
      .mockResolvedValueOnce(makeOk(RULES_LIST));              // reload list
    renderPage();
    await waitFor(() => screen.getByTestId('no-rules'));
    fireEvent.click(screen.getByTestId('create-btn'));
    await waitFor(() => expect(screen.getByTestId('create-result')).toBeInTheDocument());
    expect(screen.getByTestId('new-rule-id').textContent).toBe('rule-001');
  });

  it('shows create-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ rules: [], total: 0 }))
      .mockResolvedValueOnce(makeOk(HEALTH_LIST))
      .mockResolvedValueOnce(makeErr(422, 'Invalid metric'));
    renderPage();
    await waitFor(() => screen.getByTestId('no-rules'));
    fireEvent.click(screen.getByTestId('create-btn'));
    await waitFor(() => expect(screen.getByTestId('create-error')).toBeInTheDocument());
    expect(screen.getByTestId('create-error').textContent).toContain('Invalid metric');
  });

  it('updates an alert rule', async () => {
    setupMountMocks();
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ rule: { ...RULE_1, threshold: 0.2 } })) // PUT
      .mockResolvedValueOnce(makeOk(RULES_LIST));                              // reload
    renderPage();
    await waitFor(() => screen.getByTestId('rules-table'));
    fireEvent.change(screen.getByTestId('update-rule-id'), { target: { value: 'rule-001' } });
    fireEvent.change(screen.getByTestId('update-threshold'), { target: { value: '0.2' } });
    fireEvent.click(screen.getByTestId('update-btn'));
    await waitFor(() => expect(screen.getByTestId('update-result')).toBeInTheDocument());
    expect(screen.getByTestId('updated-threshold').textContent).toBe('0.2');
  });

  it('shows update-error on fetch failure', async () => {
    setupMountMocks();
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Rule not found'));
    renderPage();
    await waitFor(() => screen.getByTestId('rules-table'));
    fireEvent.change(screen.getByTestId('update-rule-id'), { target: { value: 'bad-id' } });
    fireEvent.click(screen.getByTestId('update-btn'));
    await waitFor(() => expect(screen.getByTestId('update-error')).toBeInTheDocument());
  });

  it('deletes an alert rule', async () => {
    setupMountMocks();
    vi.mocked(fetch).mockResolvedValueOnce(makeNoContent());
    renderPage();
    await waitFor(() => screen.getAllByTestId('rule-row'));
    fireEvent.click(screen.getAllByTestId('delete-rule-btn')[0]);
    await waitFor(() => expect(screen.getAllByTestId('rule-row')).toHaveLength(1));
  });

  it('shows delete-error on fetch failure', async () => {
    setupMountMocks();
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Not found'));
    renderPage();
    await waitFor(() => screen.getAllByTestId('delete-rule-btn'));
    fireEvent.click(screen.getAllByTestId('delete-rule-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('delete-error')).toBeInTheDocument());
  });

  it('loads and shows workflow health on mount', async () => {
    setupMountMocks();
    renderPage();
    await waitFor(() => screen.getByTestId('health-table'));
    const rows = screen.getAllByTestId('health-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('flow-abc');
    expect(rows[0].textContent).toContain('95.0%');
  });

  it('shows no-health when list is empty', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(RULES_LIST))
      .mockResolvedValueOnce(makeOk({ workflows: [], total: 0 }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-health')).toBeInTheDocument());
  });

  it('shows health-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(RULES_LIST))
      .mockResolvedValueOnce(makeErr(500, 'Health unavailable'));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('health-error')).toBeInTheDocument());
  });

  it('handles array response shape for rules', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk([RULE_1, RULE_2]))  // direct array
      .mockResolvedValueOnce(makeOk(HEALTH_LIST));
    renderPage();
    await waitFor(() => screen.getByTestId('rules-table'));
    expect(screen.getAllByTestId('rule-row')).toHaveLength(2);
  });

  it('shows disabled rule status', async () => {
    setupMountMocks();
    renderPage();
    await waitFor(() => screen.getAllByTestId('rule-row'));
    // RULE_2 has enabled: false
    const rows = screen.getAllByTestId('rule-row');
    expect(rows[1].textContent).toContain('no');
  });
});
