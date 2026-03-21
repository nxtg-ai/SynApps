import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import UsageDetailPage from './UsageDetailPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <span data-testid="layout-title">{title}</span>
      {children}
    </div>
  ),
}));

const SAMPLE_USAGE: Record<string, unknown> = {
  key_id: 'key-abc',
  requests_today: 42,
  requests_week: 310,
  requests_month: 1200,
  errors_month: 15,
  bandwidth_bytes: 2048000,
  error_rate_pct: 1.25,
  quota: 5000,
  by_endpoint: { '/api/v1/flows': 400, '/api/v1/runs': 200 },
  by_hour: { '2026-03-21T10': 50, '2026-03-21T11': 80 },
  last_request_at: '2026-03-21T11:59:00Z',
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <UsageDetailPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok-test');
});

describe('UsageDetailPage', () => {
  // 1. Page title
  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Usage Detail');
  });

  // 2. Empty state on load
  it('shows empty state initially', () => {
    renderPage();
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
  });

  // 3. Fetch button disabled when input empty
  it('fetch button disabled with empty input', () => {
    renderPage();
    expect(screen.getByTestId('fetch-btn')).toBeDisabled();
  });

  // 4. Fetch button enabled with key ID
  it('enables fetch button when key ID entered', () => {
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    expect(screen.getByTestId('fetch-btn')).not.toBeDisabled();
  });

  // 5. Calls correct endpoint
  it('calls GET /usage/{key_id}', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(SAMPLE_USAGE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/usage/key-abc'),
        expect.any(Object),
      ),
    );
  });

  // 6. Today request count shown
  it('displays requests_today', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_USAGE)));
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('requests-today')).toHaveTextContent('42'),
    );
  });

  // 7. Month request count shown
  it('displays requests_month', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_USAGE)));
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('requests-month')).toHaveTextContent('1200'),
    );
  });

  // 8. Error rate shown
  it('displays error_rate_pct', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_USAGE)));
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('error-rate')).toHaveTextContent('1.25%'),
    );
  });

  // 9. Bandwidth formatted
  it('displays formatted bandwidth', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_USAGE)));
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('bandwidth')).toHaveTextContent('MB'),
    );
  });

  // 10. By-endpoint rows shown
  it('renders by-endpoint rows', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_USAGE)));
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() => {
      const rows = screen.getAllByTestId('endpoint-row');
      expect(rows.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 11. Endpoint paths shown
  it('displays endpoint paths in table', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_USAGE)));
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByText('/api/v1/flows')).toBeInTheDocument(),
    );
  });

  // 12. By-hour buckets shown
  it('renders by-hour buckets', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_USAGE)));
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'key-abc' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() => {
      const buckets = screen.getAllByTestId('hour-bucket');
      expect(buckets.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 13. 404 error shown
  it('shows error on 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(404, 'No usage data for this key')));
    renderPage();
    fireEvent.change(screen.getByTestId('key-id-input'), { target: { value: 'unknown' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('fetch-error')).toHaveTextContent('No usage data for this key'),
    );
  });
});
