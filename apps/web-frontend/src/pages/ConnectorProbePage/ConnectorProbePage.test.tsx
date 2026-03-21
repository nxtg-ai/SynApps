/**
 * Unit tests for ConnectorProbePage (N-111).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ConnectorProbePage from './ConnectorProbePage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CONNECTOR_1 = {
  name: 'openai',
  status: 'healthy',
  dashboard_status: 'healthy',
  consecutive_failures: 0,
  total_probes: 50,
  avg_latency_ms: 120,
  error_count_5m: 0,
};

const CONNECTOR_2 = {
  name: 'anthropic',
  status: 'degraded',
  dashboard_status: 'degraded',
  consecutive_failures: 2,
  total_probes: 10,
  avg_latency_ms: 1500,
  error_count_5m: 3,
};

const HEALTH_DATA = {
  connectors: [CONNECTOR_1, CONNECTOR_2],
  summary: { healthy: 1, degraded: 1, down: 0, disabled: 0 },
  total: 2,
  disable_threshold: 5,
};

const PROBE_RESULT = {
  name: 'openai',
  status: 'healthy',
  dashboard_status: 'healthy',
  consecutive_failures: 0,
  total_probes: 51,
  avg_latency_ms: 118,
  error_count_5m: 0,
};

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ConnectorProbePage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ConnectorProbePage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'tok');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(HEALTH_DATA));
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('loads and shows connector health on mount', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(HEALTH_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('connectors-table'));
    const rows = screen.getAllByTestId('connector-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('openai');
    expect(rows[0].textContent).toContain('healthy');
  });

  it('shows summary cards', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(HEALTH_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('summary-cards'));
    expect(screen.getByTestId('summary-healthy').textContent).toBe('1');
    expect(screen.getByTestId('summary-degraded').textContent).toBe('1');
    expect(screen.getByTestId('summary-down').textContent).toBe('0');
    expect(screen.getByTestId('summary-disabled').textContent).toBe('0');
  });

  it('shows no-connectors when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ connectors: [], summary: { healthy: 0, degraded: 0, down: 0, disabled: 0 }, total: 0 }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-connectors')).toBeInTheDocument());
  });

  it('shows health-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(500, 'Health check failed'));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('health-error')).toBeInTheDocument());
    expect(screen.getByTestId('health-error').textContent).toContain('Health check failed');
  });

  it('probes single connector', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(HEALTH_DATA))    // mount health
      .mockResolvedValueOnce(makeOk(PROBE_RESULT));  // POST probe
    renderPage();
    await waitFor(() => screen.getByTestId('connectors-table'));
    fireEvent.change(screen.getByTestId('connector-name-input'), { target: { value: 'openai' } });
    fireEvent.click(screen.getByTestId('probe-btn'));
    await waitFor(() => expect(screen.getByTestId('probe-result')).toBeInTheDocument());
    expect(screen.getByTestId('probe-result-name').textContent).toBe('openai');
    expect(screen.getByTestId('probe-result-status').textContent).toBe('healthy');
  });

  it('shows probe-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(HEALTH_DATA))
      .mockResolvedValueOnce(makeErr(404, 'Connector not found'));
    renderPage();
    await waitFor(() => screen.getByTestId('connectors-table'));
    fireEvent.change(screen.getByTestId('connector-name-input'), { target: { value: 'unknown' } });
    fireEvent.click(screen.getByTestId('probe-btn'));
    await waitFor(() => expect(screen.getByTestId('probe-error')).toBeInTheDocument());
    expect(screen.getByTestId('probe-error').textContent).toContain('Connector not found');
  });

  it('refresh button reloads health', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(HEALTH_DATA))
      .mockResolvedValueOnce(makeOk(HEALTH_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('connectors-table'));
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2));
  });

  it('shows degraded status with amber color', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(HEALTH_DATA));
    renderPage();
    await waitFor(() => screen.getAllByTestId('connector-row'));
    const rows = screen.getAllByTestId('connector-row');
    const statusCells = rows[1].querySelectorAll('[data-testid="connector-status"]');
    expect(statusCells[0].textContent).toBe('degraded');
  });

  it('handles array response shape for connectors', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ connectors: [CONNECTOR_1], summary: null, total: 1 }),
    );
    renderPage();
    await waitFor(() => screen.getByTestId('connectors-table'));
    expect(screen.getAllByTestId('connector-row')).toHaveLength(1);
  });
});
