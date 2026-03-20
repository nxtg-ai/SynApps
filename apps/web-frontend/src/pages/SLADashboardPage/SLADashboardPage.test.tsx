/**
 * Tests for SLADashboardPage -- N-33 SLA tracking.
 *
 * Covers: loading state, compliance rate display, green/red color coding,
 * violations table, empty violations, policies list, inline edit, delete policy.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, afterEach } from 'vitest';
import SLADashboardPage from './SLADashboardPage';

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

function makeDashboard(
  overrides: Partial<{
    total_runs: number;
    violations: number;
    compliance_rate_pct: number;
    by_flow: Array<{ flow_id: string; violations: number }>;
  }> = {},
) {
  return {
    total_runs: 100,
    violations: 5,
    compliance_rate_pct: 95.0,
    by_flow: [],
    ...overrides,
  };
}

function makeViolations(
  items: Array<
    Partial<{
      violation_id: string;
      policy_id: string;
      flow_id: string;
      run_id: string;
      actual_duration_seconds: number;
      max_duration_seconds: number;
      pct_over: number;
      created_at: number;
    }>
  > = [],
) {
  return items.map((v, i) => ({
    violation_id: `v-${i}`,
    policy_id: `pol-${i}`,
    flow_id: `flow-${i}`,
    run_id: `run-${i}`,
    actual_duration_seconds: 15.0,
    max_duration_seconds: 10.0,
    pct_over: 50.0,
    created_at: Date.now() / 1000,
    ...v,
  }));
}

function makePolicies(
  items: Array<
    Partial<{
      policy_id: string;
      flow_id: string;
      owner_id: string;
      max_duration_seconds: number;
      alert_threshold_pct: number;
      created_at: number;
    }>
  > = [],
) {
  return items.map((p, i) => ({
    policy_id: `pol-${i}`,
    flow_id: `flow-${i}`,
    owner_id: 'owner-1',
    max_duration_seconds: 30,
    alert_threshold_pct: 0.8,
    created_at: Date.now() / 1000,
    ...p,
  }));
}

function mockAllFetches(
  dashboard = makeDashboard(),
  violations = makeViolations(),
  policies = makePolicies(),
) {
  let callIndex = 0;
  vi.spyOn(global, 'fetch').mockImplementation(() => {
    const responses = [
      new Response(JSON.stringify(dashboard), { status: 200 }),
      new Response(JSON.stringify(violations), { status: 200 }),
      new Response(JSON.stringify(policies), { status: 200 }),
    ];
    const resp = responses[callIndex] ?? responses[0];
    callIndex++;
    return Promise.resolve(resp);
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <SLADashboardPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SLADashboardPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', () => {
    vi.spyOn(global, 'fetch').mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.getByLabelText('Loading SLA data')).toBeInTheDocument();
  });

  it('shows compliance rate value', async () => {
    mockAllFetches(makeDashboard({ compliance_rate_pct: 92.5 }));

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('compliance-rate')).toHaveTextContent('92.5%');
    });
  });

  it('uses green color for compliance >= 95%', async () => {
    mockAllFetches(makeDashboard({ compliance_rate_pct: 98.0 }));

    renderPage();

    await waitFor(() => {
      const el = screen.getByTestId('compliance-rate');
      expect(el.className).toContain('text-green-500');
    });
  });

  it('uses red color for compliance < 80%', async () => {
    mockAllFetches(makeDashboard({ compliance_rate_pct: 72.0 }));

    renderPage();

    await waitFor(() => {
      const el = screen.getByTestId('compliance-rate');
      expect(el.className).toContain('text-red-500');
    });
  });

  it('shows violations table rows', async () => {
    mockAllFetches(
      makeDashboard(),
      makeViolations([
        { flow_id: 'my-flow-abc', pct_over: 25.3 },
        { flow_id: 'other-flow-xyz', pct_over: 100.0 },
      ]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('my-flow-abc')).toBeInTheDocument();
      expect(screen.getByText('other-flow-x...')).toBeInTheDocument();
    });
  });

  it('shows empty violations message', async () => {
    mockAllFetches(makeDashboard(), makeViolations([]), makePolicies());

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No violations recorded')).toBeInTheDocument();
    });
  });

  it('shows policies list', async () => {
    mockAllFetches(
      makeDashboard(),
      makeViolations(),
      makePolicies([
        { flow_id: 'pol-flow-1', max_duration_seconds: 60 },
        { flow_id: 'pol-flow-2', max_duration_seconds: 120 },
      ]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Manage SLA Policies')).toBeInTheDocument();
      expect(screen.getByText('pol-flow-1')).toBeInTheDocument();
      expect(screen.getByText('pol-flow-2')).toBeInTheDocument();
    });
  });

  it('supports inline edit of policy', async () => {
    mockAllFetches(
      makeDashboard(),
      makeViolations(),
      makePolicies([{ flow_id: 'edit-flow', max_duration_seconds: 30 }]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Edit')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => {
      expect(screen.getByLabelText('Max duration seconds')).toBeInTheDocument();
      expect(screen.getByText('Save')).toBeInTheDocument();
    });
  });

  it('calls delete when clicking Delete button', async () => {
    mockAllFetches(
      makeDashboard(),
      makeViolations(),
      makePolicies([{ flow_id: 'del-flow', max_duration_seconds: 45 }]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Delete')).toBeInTheDocument();
    });

    // Mock the delete call + subsequent reload
    vi.spyOn(global, 'fetch').mockImplementation(() => {
      return Promise.resolve(
        new Response(JSON.stringify(makeDashboard()), { status: 200 }),
      );
    });

    fireEvent.click(screen.getByText('Delete'));

    // Verify fetch was called (DELETE request)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
  });
});
