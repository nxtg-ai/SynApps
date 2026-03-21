/**
 * Unit tests for WorkflowTestRunnerPage (N-112).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkflowTestRunnerPage from './WorkflowTestRunnerPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TEST_RESULT = {
  id: 'res-001',
  workflow_id: 'flow-abc',
  run_id: 'run-001',
  suite_name: 'smoke',
  passed: true,
  assertion_count: 2,
  pass_count: 2,
  fail_count: 0,
  assertion_results: [
    { assertion: 'status == success', passed: true },
    { assertion: 'output.text contains Hello', passed: true },
  ],
  run_status: 'success',
  timestamp: 1711000000,
};

const HISTORY_DATA = {
  workflow_id: 'flow-abc',
  total: 2,
  history: [
    { id: 'res-001', run_id: 'run-001', passed: true, suite_name: 'smoke' },
    { id: 'res-002', run_id: 'run-002', passed: false, suite_name: 'full' },
  ],
};

const SUITE_RECORD = { suite_id: 'suite-001', name: 'My Suite', workflow_id: 'flow-abc' };

const SUITES_DATA = {
  workflow_id: 'flow-abc',
  total: 2,
  suites: [
    { suite_id: 'suite-001', name: 'My Suite' },
    { suite_id: 'suite-002', name: 'Smoke Suite' },
  ],
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowTestRunnerPage />
    </MemoryRouter>,
  );
}

function fillFlowId(value = 'flow-abc') {
  fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value } });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowTestRunnerPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  // 1. Renders page title
  it('renders the page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Workflow Test Runner');
  });

  // 2. Tab navigation works
  it('clicking tab-history shows tab-panel-history and hides tab-panel-run', async () => {
    renderPage();
    expect(screen.getByTestId('tab-panel-run')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('tab-history'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-history')).toBeInTheDocument());
    expect(screen.queryByTestId('tab-panel-run')).not.toBeInTheDocument();
  });

  // 3. Run test success — shows result-passed and result-run-id
  it('run test success shows result-passed and result-run-id', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(TEST_RESULT));
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('run-test-btn'));

    await waitFor(() => expect(screen.getByTestId('run-test-result')).toBeInTheDocument());
    expect(screen.getByTestId('result-passed')).toHaveTextContent('PASSED');
    expect(screen.getByTestId('result-run-id')).toHaveTextContent('run-001');
  });

  // 4. Run test invalid input JSON error
  it('shows run-test-error when input JSON is invalid', async () => {
    renderPage();
    fillFlowId();

    fireEvent.change(screen.getByTestId('run-test-input-json'), {
      target: { value: 'not valid json' },
    });
    fireEvent.click(screen.getByTestId('run-test-btn'));

    await waitFor(() => expect(screen.getByTestId('run-test-error')).toBeInTheDocument());
    expect(screen.getByTestId('run-test-error')).toHaveTextContent('Invalid input JSON');
    expect(fetch).not.toHaveBeenCalled();
  });

  // 5. Run test API error
  it('shows run-test-error on API failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(500, 'Internal server error'));
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('run-test-btn'));

    await waitFor(() => expect(screen.getByTestId('run-test-error')).toBeInTheDocument());
    expect(screen.getByTestId('run-test-error')).toHaveTextContent('Internal server error');
  });

  // 6. Run test shows assertion rows
  it('run test result shows assertion rows with assertion-status', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(TEST_RESULT));
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('run-test-btn'));

    await waitFor(() => expect(screen.getByTestId('result-assertions')).toBeInTheDocument());

    const rows = screen.getAllByTestId('assertion-row');
    expect(rows).toHaveLength(2);

    const statuses = screen.getAllByTestId('assertion-status');
    expect(statuses).toHaveLength(2);
    expect(statuses[0]).toBeInTheDocument();
  });

  // 7. Load history success — shows history items
  it('load history success shows history items', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(HISTORY_DATA));
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('tab-history'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-history')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('load-history-btn'));

    await waitFor(() => expect(screen.getByTestId('history-list')).toBeInTheDocument());

    const items = screen.getAllByTestId('history-item');
    expect(items).toHaveLength(2);
    expect(items.length).toBeGreaterThanOrEqual(1); // Gate 2

    const runIds = screen.getAllByTestId('history-item-run-id');
    expect(runIds[0]).toHaveTextContent('run-001');

    const passedLabels = screen.getAllByTestId('history-item-passed');
    expect(passedLabels[0]).toHaveTextContent('PASSED');
    expect(passedLabels[1]).toHaveTextContent('FAILED');
  });

  // 8. Load history empty state
  it('shows no-history when history list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ workflow_id: 'flow-abc', total: 0, history: [] }),
    );
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('tab-history'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-history')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('load-history-btn'));

    await waitFor(() => expect(screen.getByTestId('no-history')).toBeInTheDocument());
    expect(screen.queryByTestId('history-list')).not.toBeInTheDocument();
  });

  // 9. Load history error
  it('shows history-error on API failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Workflow not found'));
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('tab-history'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-history')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('load-history-btn'));

    await waitFor(() => expect(screen.getByTestId('history-error')).toBeInTheDocument());
    expect(screen.getByTestId('history-error')).toHaveTextContent('Workflow not found');
  });

  // 10. Save suite success — shows saved-suite-id
  it('save suite success shows saved-suite-id', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(SUITE_RECORD));
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('tab-suites'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-suites')).toBeInTheDocument());

    fireEvent.change(screen.getByTestId('save-suite-name-input'), {
      target: { value: 'My Suite' },
    });
    fireEvent.click(screen.getByTestId('save-suite-btn'));

    await waitFor(() => expect(screen.getByTestId('save-suite-result')).toBeInTheDocument());
    expect(screen.getByTestId('saved-suite-id')).toHaveTextContent('suite-001');
  });

  // 11. Save suite invalid JSON error
  it('shows save-suite-error when suite JSON is invalid', async () => {
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('tab-suites'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-suites')).toBeInTheDocument());

    fireEvent.change(screen.getByTestId('save-suite-json'), {
      target: { value: 'bad json {{{' },
    });
    fireEvent.click(screen.getByTestId('save-suite-btn'));

    await waitFor(() => expect(screen.getByTestId('save-suite-error')).toBeInTheDocument());
    expect(screen.getByTestId('save-suite-error')).toHaveTextContent('Invalid JSON');
    expect(fetch).not.toHaveBeenCalled();
  });

  // 12. Load suites success — shows suite items
  it('load suites success shows suite items', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(SUITES_DATA));
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('tab-suites'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-suites')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('load-suites-btn'));

    await waitFor(() => expect(screen.getByTestId('suites-list')).toBeInTheDocument());

    const items = screen.getAllByTestId('suite-item');
    expect(items).toHaveLength(2);
    expect(items.length).toBeGreaterThanOrEqual(1); // Gate 2

    const names = screen.getAllByTestId('suite-item-name');
    expect(names[0]).toHaveTextContent('My Suite');
    expect(names[1]).toHaveTextContent('Smoke Suite');
  });

  // 13. Load suites empty state
  it('shows no-suites when suites list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ workflow_id: 'flow-abc', total: 0, suites: [] }),
    );
    renderPage();
    fillFlowId();

    fireEvent.click(screen.getByTestId('tab-suites'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-suites')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('load-suites-btn'));

    await waitFor(() => expect(screen.getByTestId('no-suites')).toBeInTheDocument());
    expect(screen.queryByTestId('suites-list')).not.toBeInTheDocument();
  });
});
