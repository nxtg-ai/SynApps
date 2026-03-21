/**
 * Unit tests for MonitoringPage (N-71).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import MonitoringPage from './MonitoringPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const HEALTH_RESPONSE = {
  workflows: [
    {
      flow_id: 'flow-1', run_count: 10, success_count: 9, error_count: 1,
      success_rate: 0.9, error_rate: 0.1, avg_duration_seconds: 2.5,
      p95_duration_seconds: 6.0, last_run_at: 1704067200, health_status: 'healthy',
    },
    {
      flow_id: 'flow-2', run_count: 5, success_count: 2, error_count: 3,
      success_rate: 0.4, error_rate: 0.6, avg_duration_seconds: 8.1,
      p95_duration_seconds: 15.0, last_run_at: 1704153600, health_status: 'critical',
    },
  ],
  total: 2,
  window_hours: 24,
};

const ALERTS_RESPONSE = {
  rules: [
    {
      id: 'rule-1', workflow_id: '*', metric: 'error_rate', operator: '>',
      threshold: 0.3, window_minutes: 60, action_type: 'log',
      action_config: {}, enabled: true, created_at: 1704067200, last_triggered_at: null,
    },
  ],
  total: 1,
};

const EMPTY_ALERTS = { rules: [], total: 0 };

function renderPage() {
  return render(
    <MemoryRouter>
      <MonitoringPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MonitoringPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and both panels', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => HEALTH_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_ALERTS } as Response);

    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('health-panel')).toBeInTheDocument();
    expect(screen.getByTestId('alerts-panel')).toBeInTheDocument();
  });

  it('shows loading state initially for health panel', () => {
    vi.mocked(fetch).mockImplementation(() => new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByTestId('health-loading')).toBeInTheDocument();
  });

  it('renders health table with workflow rows', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => HEALTH_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_ALERTS } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('health-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('health-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('flow-1')).toBeInTheDocument();
    expect(screen.getByText('flow-2')).toBeInTheDocument();
  });

  it('shows healthy and critical status badges', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => HEALTH_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_ALERTS } as Response);

    renderPage();
    await waitFor(() => expect(screen.getAllByTestId('health-status-badge')).toHaveLength(2));
    const badges = screen.getAllByTestId('health-status-badge');
    expect(badges[0]).toHaveTextContent('healthy');
    expect(badges[1]).toHaveTextContent('critical');
  });

  it('shows empty state when no workflows ran', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ workflows: [], total: 0, window_hours: 24 }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_ALERTS } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('health-empty')).toBeInTheDocument());
  });

  it('renders window-hours select and refresh button', async () => {
    vi.mocked(fetch)
      .mockResolvedValue({ ok: true, json: async () => HEALTH_RESPONSE } as Response);

    renderPage();
    expect(screen.getByTestId('window-select')).toBeInTheDocument();
    expect(screen.getByTestId('refresh-health-btn')).toBeInTheDocument();
  });

  it('renders alert rules table with existing rule', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => HEALTH_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ALERTS_RESPONSE } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('alerts-table')).toBeInTheDocument());
    expect(screen.getByTestId('alert-row')).toBeInTheDocument();
    // metric cell in the table row (not the select option)
    expect(screen.getByTestId('alert-row').textContent).toContain('error_rate');
  });

  it('shows empty alerts state when no rules', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => HEALTH_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_ALERTS } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('alerts-empty')).toBeInTheDocument());
  });

  it('renders create rule form with selects and input', async () => {
    vi.mocked(fetch)
      .mockResolvedValue({ ok: true, json: async () => EMPTY_ALERTS } as Response);

    renderPage();
    expect(screen.getByTestId('create-rule-form')).toBeInTheDocument();
    expect(screen.getByTestId('rule-metric-select')).toBeInTheDocument();
    expect(screen.getByTestId('rule-operator-select')).toBeInTheDocument();
    expect(screen.getByTestId('rule-threshold-input')).toBeInTheDocument();
    expect(screen.getByTestId('rule-action-select')).toBeInTheDocument();
    expect(screen.getByTestId('create-rule-btn')).toBeInTheDocument();
  });

  it('creates a new alert rule on form submit', async () => {
    const newRule = {
      id: 'rule-new', workflow_id: '*', metric: 'error_rate', operator: '>',
      threshold: 0.3, window_minutes: 60, action_type: 'log',
      action_config: {}, enabled: true, created_at: 1704067200, last_triggered_at: null,
    };
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ workflows: [], total: 0, window_hours: 24 }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_ALERTS } as Response)
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ rule: newRule }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ rules: [newRule], total: 1 }) } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('create-rule-btn')).toBeInTheDocument());
    fireEvent.submit(screen.getByTestId('create-rule-form'));

    await waitFor(() => expect(screen.getByTestId('alerts-table')).toBeInTheDocument());
  });

  it('confirm-delete flow shows Yes/No buttons', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ workflows: [], total: 0, window_hours: 24 }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ALERTS_RESPONSE } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('delete-rule-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('delete-rule-btn'));
    expect(screen.getByTestId('confirm-delete-rule-btn')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-delete-rule-btn')).toBeInTheDocument();
  });

  it('cancels delete on No', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ workflows: [], total: 0, window_hours: 24 }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ALERTS_RESPONSE } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('delete-rule-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('delete-rule-btn'));
    fireEvent.click(screen.getByTestId('cancel-delete-rule-btn'));
    expect(screen.getByTestId('delete-rule-btn')).toBeInTheDocument();
  });

  it('shows health error on API failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_ALERTS } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('health-error')).toBeInTheDocument());
  });
});
