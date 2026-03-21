/**
 * Unit tests for UsagePage (N-80).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import UsagePage from './UsagePage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const QUOTA = {
  user: 'alice@example.com',
  executions_this_hour: 5,
  hourly_limit: 20,
  hourly_remaining: 15,
  hourly_reset_in_seconds: 1800,
  executions_this_month: 150,
  monthly_limit: 500,
  monthly_remaining: 350,
  month: '2024-01',
};

const USAGE_TWO = [
  {
    key_id: 'consumer-alice',
    requests_today: 42,
    requests_week: 210,
    requests_month: 850,
    errors_month: 3,
    bandwidth_bytes: 1024 * 512,
    error_rate_pct: 0.35,
  },
  {
    key_id: 'consumer-bob',
    requests_today: 8,
    requests_week: 40,
    requests_month: 200,
    errors_month: 0,
    bandwidth_bytes: 1024,
    error_rate_pct: 0,
  },
];

const USAGE_EMPTY: unknown[] = [];

function renderPage() {
  return render(
    <MemoryRouter>
      <UsagePage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('UsagePage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_TWO } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows quota panel with user and bars', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_EMPTY } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('quota-panel')).toBeInTheDocument());
    expect(screen.getByTestId('hourly-bar')).toBeInTheDocument();
    expect(screen.getByTestId('monthly-bar')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  it('shows quota-error on quota fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: false, status: 401 } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_EMPTY } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('quota-error')).toBeInTheDocument());
  });

  it('shows usage-table with rows when consumers exist', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_TWO } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('usage-table')).toBeInTheDocument());
    expect(screen.getAllByTestId('usage-row')).toHaveLength(2);
    expect(screen.getByText('consumer-alice')).toBeInTheDocument();
    expect(screen.getByText('consumer-bob')).toBeInTheDocument();
  });

  it('shows no-usage when consumer list is empty', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_EMPTY } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-usage')).toBeInTheDocument());
  });

  it('shows all-usage-error on usage fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('all-usage-error')).toBeInTheDocument());
  });

  it('refresh-btn triggers reload', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_EMPTY } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_EMPTY } as Response);

    renderPage();
    // Wait for initial load to finish (button enabled = not loading)
    await waitFor(() =>
      expect(screen.getByTestId('refresh-btn')).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByTestId('refresh-btn'));
    // 4 total calls: 2 on mount + 2 on refresh
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(4));
  });

  it('shows hourly reset time in human-readable form', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_EMPTY } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quota-panel'));
    // 1800s = 30m 0s
    expect(screen.getByText('30m 0s')).toBeInTheDocument();
  });

  it('shows bandwidth in human-readable form', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTA } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => USAGE_TWO } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('usage-table'));
    // 1024*512 bytes = 512 KB
    expect(screen.getByText('512.0 KB')).toBeInTheDocument();
  });
});
