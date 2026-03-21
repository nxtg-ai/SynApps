/**
 * Unit tests for FailedRequestsPage (N-88).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import FailedRequestsPage from './FailedRequestsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const REQUESTS_LIST = [
  {
    request_id: 'req-001',
    timestamp: '2024-01-10T09:00:00Z',
    method: 'POST',
    path: '/api/v1/flows',
    response_status: 500,
    duration_ms: 120,
    client_ip: '127.0.0.1',
  },
  {
    request_id: 'req-002',
    timestamp: '2024-01-10T09:05:00Z',
    method: 'GET',
    path: '/api/v1/runs/xyz',
    response_status: 404,
    duration_ms: 45,
    client_ip: '127.0.0.1',
  },
];

const DEBUG_DETAIL = {
  request_id: 'req-001',
  timestamp: '2024-01-10T09:00:00Z',
  method: 'POST',
  path: '/api/v1/flows',
  duration_ms: 120,
  client_ip: '127.0.0.1',
  request_headers: { 'content-type': 'application/json' },
  request_body: '{"name":"test"}',
  response_status: 500,
  response_headers: { 'content-type': 'application/json' },
  response_body: '{"detail":"Internal Server Error"}',
};

const REPLAY_RESULT = {
  original_request_id: 'req-001',
  replay_status: 201,
  replay_headers: { 'content-type': 'application/json' },
  replay_body: { id: 'flow-new-1' },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <FailedRequestsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('FailedRequestsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows request rows in table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => REQUESTS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('requests-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('request-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('/api/v1/flows')).toBeInTheDocument();
  });

  it('shows no-requests when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-requests')).toBeInTheDocument());
  });

  it('shows list-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('list-error')).toBeInTheDocument());
  });

  it('shows no-request-selected initially', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => REQUESTS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('requests-table'));
    expect(screen.getByTestId('no-request-selected')).toBeInTheDocument();
  });

  it('clicking a row loads debug detail', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => REQUESTS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => DEBUG_DETAIL } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('requests-table'));
    fireEvent.click(screen.getAllByTestId('request-row')[0]);
    await waitFor(() => expect(screen.getByTestId('debug-panel')).toBeInTheDocument());
    expect(screen.getByTestId('debug-path').textContent).toContain('/api/v1/flows');
    expect(screen.getByTestId('debug-status').textContent).toContain('500');
  });

  it('shows request headers section when present', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => REQUESTS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => DEBUG_DETAIL } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('requests-table'));
    fireEvent.click(screen.getAllByTestId('request-row')[0]);
    await waitFor(() => screen.getByTestId('debug-panel'));
    expect(screen.getByTestId('req-headers-section')).toBeInTheDocument();
    expect(screen.getByTestId('req-body-section')).toBeInTheDocument();
    expect(screen.getByTestId('resp-body-section')).toBeInTheDocument();
  });

  it('shows debug-error on debug fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => REQUESTS_LIST } as Response)
      .mockResolvedValueOnce({ ok: false, status: 404 } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('requests-table'));
    fireEvent.click(screen.getAllByTestId('request-row')[0]);
    await waitFor(() => expect(screen.getByTestId('debug-error')).toBeInTheDocument());
  });

  it('replay shows status and body on success', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => REQUESTS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => DEBUG_DETAIL } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => REPLAY_RESULT } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('requests-table'));
    fireEvent.click(screen.getAllByTestId('request-row')[0]);
    await waitFor(() => screen.getByTestId('debug-panel'));
    fireEvent.click(screen.getByTestId('replay-btn'));
    await waitFor(() => expect(screen.getByTestId('replay-result')).toBeInTheDocument());
    expect(screen.getByTestId('replay-status').textContent).toContain('201');
  });

  it('replay shows error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => REQUESTS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => DEBUG_DETAIL } as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: async () => ({ detail: 'Replay failed: connection refused' }),
      } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('requests-table'));
    fireEvent.click(screen.getAllByTestId('request-row')[0]);
    await waitFor(() => screen.getByTestId('debug-panel'));
    fireEvent.click(screen.getByTestId('replay-btn'));
    await waitFor(() => expect(screen.getByTestId('replay-error')).toBeInTheDocument());
    expect(screen.getByTestId('replay-error').textContent).toContain('connection refused');
  });

  it('refresh-btn reloads request list', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => REQUESTS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => REQUESTS_LIST } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
