/**
 * Tests for ExecutionHistoryPage
 * Covers: GET /api/v1/history, GET /api/v1/history/{run_id}
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

import ExecutionHistoryPage from './ExecutionHistoryPage';

const mockEntry = {
  run_id: 'run-abc-123-def-456',
  flow_id: 'flow-1',
  flow_name: 'My Workflow',
  status: 'success',
  start_time: 1700000000,
  end_time: 1700000005,
  duration_ms: 5000,
  step_count: 3,
  steps_succeeded: 3,
  steps_failed: 0,
  error: null,
  input_summary: { prompt: 'hello' },
  output_summary: { keys: ['node1'], total_keys: 1 },
};

const mockDetail = {
  ...mockEntry,
  input_data: { prompt: 'hello' },
  trace: {
    duration_ms: 5000,
    nodes: [
      { node_id: 'n1', node_type: 'LLMNode', status: 'success', duration_ms: 2500 },
      { node_id: 'n2', node_type: 'TransformNode', status: 'success', duration_ms: 500 },
    ],
  },
};

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.setItem('access_token', 'test-token');
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <ExecutionHistoryPage />
    </MemoryRouter>,
  );

describe('ExecutionHistoryPage', () => {
  it('renders page title', () => {
    renderPage();
    expect(screen.getByText('Execution History')).toBeTruthy();
  });

  it('renders Browse and Detail tabs', () => {
    renderPage();
    expect(screen.getByTestId('tab-browse')).toBeTruthy();
    expect(screen.getByTestId('tab-detail')).toBeTruthy();
  });

  it('shows browse tab by default', () => {
    renderPage();
    expect(screen.getByTestId('tab-browse-content')).toBeTruthy();
  });

  it('calls GET /api/v1/history on Search', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ history: [mockEntry], total: 1, page: 1, page_size: 20 }),
    });

    renderPage();
    fireEvent.click(screen.getByTestId('fetch-history-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/history'),
        expect.objectContaining({ headers: expect.objectContaining({ Authorization: expect.any(String) }) }),
      );
    });
  });

  it('applies status filter in query', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ history: [], total: 0, page: 1, page_size: 20 }),
    });

    renderPage();
    fireEvent.change(screen.getByTestId('status-filter'), { target: { value: 'error' } });
    fireEvent.click(screen.getByTestId('fetch-history-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('status=error'),
        expect.any(Object),
      );
    });
  });

  it('applies template filter in query', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ history: [], total: 0, page: 1, page_size: 20 }),
    });

    renderPage();
    fireEvent.change(screen.getByTestId('template-filter'), { target: { value: 'My Flow' } });
    fireEvent.click(screen.getByTestId('fetch-history-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('template=My+Flow'),
        expect.any(Object),
      );
    });
  });

  it('renders history rows with total count', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ history: [mockEntry], total: 1, page: 1, page_size: 20 }),
    });

    renderPage();
    fireEvent.click(screen.getByTestId('fetch-history-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('total-count')).toBeTruthy();
      expect(screen.getAllByTestId('history-row').length).toBe(1);
    });
  });

  it('shows no-history message for empty results', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ history: [], total: 0, page: 1, page_size: 20 }),
    });

    renderPage();
    fireEvent.click(screen.getByTestId('fetch-history-btn'));

    await waitFor(() => expect(screen.getByTestId('no-history')).toBeTruthy());
  });

  it('shows error message on browse fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });

    renderPage();
    fireEvent.click(screen.getByTestId('fetch-history-btn'));

    await waitFor(() => expect(screen.getByTestId('browse-error')).toBeTruthy());
  });

  it('clicking a history row switches to detail tab and fetches detail', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ history: [mockEntry], total: 1, page: 1, page_size: 20 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      });

    renderPage();
    fireEvent.click(screen.getByTestId('fetch-history-btn'));

    await waitFor(() => screen.getAllByTestId('history-row').length > 0);
    fireEvent.click(screen.getAllByTestId('history-row')[0]);

    await waitFor(() => {
      expect(screen.getByTestId('tab-detail-content')).toBeTruthy();
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/history/${mockEntry.run_id}`),
        expect.any(Object),
      );
    });
  });

  it('fetch detail button disabled without run ID', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('tab-detail'));
    const btn = screen.getByTestId('fetch-detail-btn') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('calls GET /api/v1/history/{run_id} on Fetch Detail', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockDetail });

    renderPage();
    fireEvent.click(screen.getByTestId('tab-detail'));
    fireEvent.change(screen.getByTestId('run-id-input'), {
      target: { value: 'run-abc-123' },
    });
    fireEvent.click(screen.getByTestId('fetch-detail-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/history/run-abc-123'),
        expect.any(Object),
      );
    });
  });

  it('renders detail panel with run metadata', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockDetail });

    renderPage();
    fireEvent.click(screen.getByTestId('tab-detail'));
    fireEvent.change(screen.getByTestId('run-id-input'), { target: { value: mockEntry.run_id } });
    fireEvent.click(screen.getByTestId('fetch-detail-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('detail-panel')).toBeTruthy();
      expect(screen.getByTestId('detail-run-id').textContent).toContain('run-abc-123');
      expect(screen.getByTestId('detail-steps').textContent).toContain('3/3');
    });
  });

  it('renders trace nodes table', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockDetail });

    renderPage();
    fireEvent.click(screen.getByTestId('tab-detail'));
    fireEvent.change(screen.getByTestId('run-id-input'), { target: { value: mockEntry.run_id } });
    fireEvent.click(screen.getByTestId('fetch-detail-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('trace-table')).toBeTruthy();
      expect(screen.getAllByTestId('trace-node').length).toBe(2);
    });
  });

  it('shows detail error on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404 });

    renderPage();
    fireEvent.click(screen.getByTestId('tab-detail'));
    fireEvent.change(screen.getByTestId('run-id-input'), { target: { value: 'bad-id' } });
    fireEvent.click(screen.getByTestId('fetch-detail-btn'));

    await waitFor(() => expect(screen.getByTestId('detail-error')).toBeTruthy());
  });

  it('displays status badges for each row', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ history: [mockEntry], total: 1, page: 1, page_size: 20 }),
    });

    renderPage();
    fireEvent.click(screen.getByTestId('fetch-history-btn'));

    await waitFor(() => {
      const badges = screen.getAllByTestId('status-badge');
      expect(badges.length).toBeGreaterThan(0);
      expect(badges[0].textContent).toBe('success');
    });
  });
});
