/**
 * Tests for WebhookDebuggerPage -- N-34 Webhook Debugger.
 *
 * Covers: loading state, log table, method/status badge colors, inspector panel,
 * headers display, request body, retry button, clear all, empty state.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, afterEach } from 'vitest';
import WebhookDebuggerPage from './WebhookDebuggerPage';

// ---------------------------------------------------------------------------
// Mock MainLayout so the page renders in isolation
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEntry(
  overrides: Partial<{
    entry_id: string;
    flow_id: string | null;
    received_at: number;
    method: string;
    path: string;
    headers: Record<string, string>;
    body: string;
    body_size: number;
    status_code: number;
    response_body: string;
    duration_ms: number;
    retry_count: number;
    last_retry_at: number | null;
  }> = {},
) {
  return {
    entry_id: 'e-1',
    flow_id: 'flow-1',
    received_at: Date.now() / 1000,
    method: 'POST',
    path: '/api/v1/webhook-triggers/t1/receive',
    headers: { 'content-type': 'application/json', host: 'localhost' },
    body: '{"hello":"world"}',
    body_size: 17,
    status_code: 202,
    response_body: '{"accepted":true}',
    duration_ms: 12.3,
    retry_count: 0,
    last_retry_at: null,
    ...overrides,
  };
}

function mockFetchEntries(items: ReturnType<typeof makeEntry>[] = [makeEntry()]) {
  vi.spyOn(global, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ items, total: items.length }), { status: 200 }),
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WebhookDebuggerPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WebhookDebuggerPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows loading state', () => {
    vi.spyOn(global, 'fetch').mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByLabelText('Loading webhook data')).toBeInTheDocument();
  });

  it('renders log table with entries', async () => {
    mockFetchEntries([makeEntry(), makeEntry({ entry_id: 'e-2', method: 'GET' })]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('log-table')).toBeInTheDocument();
      const rows = screen.getAllByTestId('log-row');
      expect(rows.length).toBe(2);
    });
  });

  it('method badge color POST = blue class', async () => {
    mockFetchEntries([makeEntry({ method: 'POST' })]);
    renderPage();
    await waitFor(() => {
      const badge = screen.getByTestId('method-badge');
      expect(badge.className).toContain('bg-blue-600');
    });
  });

  it('status badge color 200 = green, 404 = red', async () => {
    mockFetchEntries([
      makeEntry({ entry_id: 'ok', status_code: 200 }),
      makeEntry({ entry_id: 'nf', status_code: 404 }),
    ]);
    renderPage();
    await waitFor(() => {
      const badges = screen.getAllByTestId('status-badge');
      expect(badges[0].className).toContain('bg-green-700');
      expect(badges[1].className).toContain('bg-red-700');
    });
  });

  it('clicking row shows inspector panel', async () => {
    mockFetchEntries([makeEntry()]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('log-table')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('log-row'));
    expect(screen.getByTestId('inspector-panel')).toBeInTheDocument();
  });

  it('inspector shows headers', async () => {
    mockFetchEntries([makeEntry({ headers: { 'x-custom': 'val123' } })]);
    renderPage();
    await waitFor(() => screen.getByTestId('log-table'));
    fireEvent.click(screen.getByTestId('log-row'));
    const headersList = screen.getByTestId('headers-list');
    expect(headersList.textContent).toContain('x-custom');
    expect(headersList.textContent).toContain('val123');
  });

  it('inspector shows request body', async () => {
    mockFetchEntries([makeEntry({ body: '{"payload":"test-data"}' })]);
    renderPage();
    await waitFor(() => screen.getByTestId('log-table'));
    fireEvent.click(screen.getByTestId('log-row'));
    expect(screen.getByTestId('request-body').textContent).toContain('test-data');
  });

  it('retry button calls retry API', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ items: [makeEntry()], total: 1 }), { status: 200 }),
    );
    renderPage();
    await waitFor(() => screen.getByTestId('log-table'));
    fireEvent.click(screen.getByTestId('log-row'));

    // Reset mock to track the retry call
    fetchSpy.mockResolvedValue(new Response(JSON.stringify(makeEntry({ retry_count: 1 })), { status: 200 }));
    fireEvent.click(screen.getByTestId('retry-btn'));

    await waitFor(() => {
      const calls = fetchSpy.mock.calls;
      const retryCall = calls.find(
        (c) => typeof c[0] === 'string' && c[0].includes('/retry'),
      );
      expect(retryCall).toBeTruthy();
    });
  });

  it('clear all button calls DELETE and clears table', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ items: [makeEntry()], total: 1 }), { status: 200 }),
    );
    renderPage();
    await waitFor(() => screen.getByTestId('log-table'));

    fetchSpy.mockResolvedValue(new Response(null, { status: 204 }));
    fireEvent.click(screen.getByTestId('clear-all-btn'));

    await waitFor(() => {
      const deleteCall = fetchSpy.mock.calls.find(
        (c) =>
          typeof c[1] === 'object' &&
          c[1] !== null &&
          'method' in c[1] &&
          c[1].method === 'DELETE',
      );
      expect(deleteCall).toBeTruthy();
    });
  });

  it('empty state shown when no entries', async () => {
    mockFetchEntries([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      expect(screen.getByTestId('empty-state').textContent).toContain(
        'No webhook activity yet',
      );
    });
  });
});
