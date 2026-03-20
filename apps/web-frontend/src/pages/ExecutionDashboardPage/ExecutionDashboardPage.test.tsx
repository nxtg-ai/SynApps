/**
 * ExecutionDashboardPage unit tests
 *
 * Covers: loading state, stats cards, active/recent tables, kill/pause/resume
 * buttons, progress bar, auto-refresh, error state.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  global.fetch = mockFetch;
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function makeExecution(overrides: Partial<{
  run_id: string;
  flow_id: string;
  flow_name: string;
  user_id: string;
  status: string;
  started_at: number;
  updated_at: number;
  node_count: number;
  completed_nodes: number;
  progress_pct: number;
  input_size_bytes: number;
  output_size_bytes: number;
  paused: boolean;
  killed: boolean;
  duration_ms: number;
}> = {}) {
  return {
    run_id: overrides.run_id ?? 'run-1',
    flow_id: overrides.flow_id ?? 'flow-1',
    flow_name: overrides.flow_name ?? 'Test Flow',
    user_id: overrides.user_id ?? 'user-1',
    status: overrides.status ?? 'running',
    started_at: overrides.started_at ?? 1000,
    updated_at: overrides.updated_at ?? 1005,
    node_count: overrides.node_count ?? 10,
    completed_nodes: overrides.completed_nodes ?? 5,
    progress_pct: overrides.progress_pct ?? 50,
    input_size_bytes: overrides.input_size_bytes ?? 128,
    output_size_bytes: overrides.output_size_bytes ?? 256,
    paused: overrides.paused ?? false,
    killed: overrides.killed ?? false,
    duration_ms: overrides.duration_ms ?? 5000,
  };
}

function makeStats(overrides: Partial<{
  active_count: number;
  total_today: number;
  avg_duration_ms: number;
  kill_count: number;
}> = {}) {
  return {
    active_count: overrides.active_count ?? 2,
    total_today: overrides.total_today ?? 15,
    avg_duration_ms: overrides.avg_duration_ms ?? 3200,
    kill_count: overrides.kill_count ?? 1,
  };
}

function setupMountMocks(opts?: {
  stats?: ReturnType<typeof makeStats>;
  active?: ReturnType<typeof makeExecution>[];
  recent?: ReturnType<typeof makeExecution>[];
}) {
  const stats = opts?.stats ?? makeStats();
  const active = opts?.active ?? [makeExecution()];
  const recent = opts?.recent ?? [makeExecution(), makeExecution({ run_id: 'run-2', status: 'completed', progress_pct: 100 })];

  // The component calls 3 endpoints in Promise.all: stats, active, recent
  mockFetch
    .mockResolvedValueOnce({ ok: true, json: async () => stats })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ items: active }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ items: recent }) });
}

async function importPage() {
  const mod = await import('./ExecutionDashboardPage');
  return mod.default;
}

function renderPage(Page: React.ComponentType) {
  return render(
    <MemoryRouter>
      <Page />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ExecutionDashboardPage', () => {
  it('shows loading state', async () => {
    // Never resolve fetch so it stays loading
    mockFetch.mockReturnValue(new Promise(() => {}));
    const Page = await importPage();
    renderPage(Page);
    expect(screen.getByText('Loading execution data...')).toBeTruthy();
  });

  it('renders stats cards', async () => {
    setupMountMocks();
    const Page = await importPage();
    renderPage(Page);
    await waitFor(() => {
      expect(screen.getByTestId('stats-active-count')).toBeTruthy();
    });
    expect(screen.getByTestId('stats-active-count').textContent).toBe('2');
    expect(screen.getByTestId('stats-total-today').textContent).toBe('15');
  });

  it('shows active executions table', async () => {
    setupMountMocks();
    const Page = await importPage();
    renderPage(Page);
    await waitFor(() => {
      expect(screen.getByTestId('active-executions-table')).toBeTruthy();
    });
    expect(screen.getAllByText('Test Flow').length).toBeGreaterThan(0);
  });

  it('shows recent executions table', async () => {
    setupMountMocks();
    const Page = await importPage();
    renderPage(Page);
    await waitFor(() => {
      expect(screen.getByTestId('recent-executions-table')).toBeTruthy();
    });
  });

  it('kill button calls kill API', async () => {
    setupMountMocks();
    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByTestId('kill-button-run-1')).toBeTruthy();
    });

    // Mock window.confirm
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    // Mock the kill API call + subsequent refresh calls
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'killed' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => makeStats() })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });

    fireEvent.click(screen.getByTestId('kill-button-run-1'));

    await waitFor(() => {
      // The kill fetch should have been called
      const killCall = mockFetch.mock.calls.find(
        (call: [string, RequestInit?]) => typeof call[0] === 'string' && call[0].includes('/kill')
      );
      expect(killCall).toBeTruthy();
    });
  });

  it('pause button calls pause API', async () => {
    setupMountMocks();
    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByTestId('pause-button-run-1')).toBeTruthy();
    });

    // Mock the pause API call + subsequent refresh calls
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'paused' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => makeStats() })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });

    fireEvent.click(screen.getByTestId('pause-button-run-1'));

    await waitFor(() => {
      const pauseCall = mockFetch.mock.calls.find(
        (call: [string, RequestInit?]) => typeof call[0] === 'string' && call[0].includes('/pause')
      );
      expect(pauseCall).toBeTruthy();
    });
  });

  it('resume button shown for paused execution', async () => {
    const pausedExec = makeExecution({ run_id: 'run-paused', status: 'paused', paused: true });
    setupMountMocks({ active: [pausedExec] });
    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByTestId('resume-button-run-paused')).toBeTruthy();
    });
  });

  it('progress bar width reflects progress_pct', async () => {
    const exec = makeExecution({ run_id: 'run-prog', progress_pct: 75 });
    setupMountMocks({ active: [exec] });
    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      const bar = screen.getByTestId('progress-bar-run-prog');
      expect(bar).toBeTruthy();
      expect(bar.style.width).toBe('75%');
    });
  });

  it('auto-refresh triggers re-fetch', async () => {
    setupMountMocks();
    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByTestId('execution-dashboard')).toBeTruthy();
    });

    const callCountAfterMount = mockFetch.mock.calls.length;

    // Set up mocks for the auto-refresh cycle
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => makeStats() })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });

    // Advance past the 3-second refresh interval
    await act(async () => {
      vi.advanceTimersByTime(3100);
    });

    await waitFor(() => {
      expect(mockFetch.mock.calls.length).toBeGreaterThan(callCountAfterMount);
    });
  });

  it('shows error state', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network failure'));
    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeTruthy();
    });
    expect(screen.getByText('Network failure')).toBeTruthy();
  });
});
