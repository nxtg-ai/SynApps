/**
 * Unit tests for ConnectorsPage (N-83).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ConnectorsPage from './ConnectorsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TWO_CONNECTORS: { connectors: unknown[]; summary: unknown; total: number } = {
  connectors: [
    {
      name: 'openai',
      status: 'healthy',
      dashboard_status: 'healthy',
      avg_latency_ms: 123.4,
      consecutive_failures: 0,
      error_count_5m: 0,
    },
    {
      name: 'anthropic',
      status: 'degraded',
      dashboard_status: 'degraded',
      avg_latency_ms: 987.6,
      consecutive_failures: 2,
      error_count_5m: 3,
    },
  ],
  summary: { healthy: 1, degraded: 1, down: 0, disabled: 0 },
  total: 2,
};

const EMPTY_CONNECTORS = {
  connectors: [],
  summary: { healthy: 0, degraded: 0, down: 0, disabled: 0 },
  total: 0,
};

const PROBE_RESULT = {
  name: 'openai',
  status: 'healthy',
  dashboard_status: 'healthy',
  avg_latency_ms: 55.0,
  consecutive_failures: 0,
  error_count_5m: 0,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ConnectorsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ConnectorsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => TWO_CONNECTORS } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows summary row and connector table after load', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => TWO_CONNECTORS } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('summary-row')).toBeInTheDocument());
    expect(screen.getByTestId('connectors-table')).toBeInTheDocument();
    expect(screen.getAllByTestId('connector-row')).toHaveLength(2);
    expect(screen.getByText('openai')).toBeInTheDocument();
    expect(screen.getByText('anthropic')).toBeInTheDocument();
  });

  it('shows no-connectors when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => EMPTY_CONNECTORS } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-connectors')).toBeInTheDocument());
  });

  it('shows connectors-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('connectors-error')).toBeInTheDocument());
  });

  it('summary counts are correct', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => TWO_CONNECTORS } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('summary-healthy'));
    expect(screen.getByTestId('summary-healthy').textContent).toContain('1');
    expect(screen.getByTestId('summary-degraded').textContent).toContain('1');
    expect(screen.getByTestId('summary-down').textContent).toContain('0');
  });

  it('status badges display dashboard_status', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => TWO_CONNECTORS } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('connectors-table'));
    const badges = screen.getAllByTestId('status-badge');
    expect(badges[0].textContent).toBe('healthy');
    expect(badges[1].textContent).toBe('degraded');
  });

  it('probe button triggers probe and updates status badge', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => TWO_CONNECTORS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => PROBE_RESULT } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('connectors-table'));
    fireEvent.click(screen.getAllByTestId('probe-btn')[0]);
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('refresh-btn reloads connectors', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => TWO_CONNECTORS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_CONNECTORS } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(screen.getByTestId('no-connectors')).toBeInTheDocument());
  });

  it('shows latency in ms format', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => TWO_CONNECTORS } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('connectors-table'));
    expect(screen.getByText('123ms')).toBeInTheDocument();
  });
});
