/**
 * Unit tests for FlowTestingPage (N-106).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import FlowTestingPage from './FlowTestingPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TEST_CASE = {
  test_id: 'tc-001',
  name: 'Basic pass',
  match_mode: 'exact',
  input: { text: 'hello' },
  expected_output: { result: 'ok' },
  created_by: 'alice@example.com',
};

const TEST_LIST = {
  tests: [TEST_CASE, { test_id: 'tc-002', name: 'Edge case', match_mode: 'contains', input: {}, expected_output: {} }],
  total: 2,
};

const SUMMARY = { total: 2, passed: 1, failed: 1, errors: 0 };

const RUN_RESULT = {
  results: [
    { result_id: 'r-001', test_id: 'tc-001', status: 'pass', actual_output: {}, expected_output: {} },
    { result_id: 'r-002', test_id: 'tc-002', status: 'fail', actual_output: {}, expected_output: {} },
  ],
  summary: SUMMARY,
  exit_code: 1,
};

const RESULTS_LIST = {
  results: [
    { result_id: 'r-001', test_id: 'tc-001', status: 'pass', actual_output: {}, expected_output: {} },
  ],
  total: 1,
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}
function makeNoContent() {
  return { ok: true, status: 204, json: async () => ({}) } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <FlowTestingPage />
    </MemoryRouter>,
  );
}

function fillFlowId(value = 'flow-123') {
  fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value } });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('FlowTestingPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'tok');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('page-title').textContent).toContain('Flow Testing');
  });

  it('loads test cases on Load Tests click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(TEST_LIST));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-tests-btn'));
    await waitFor(() => screen.getByTestId('tests-table'));
    const rows = screen.getAllByTestId('test-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('Basic pass');
  });

  it('shows no-tests when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ tests: [], total: 0 }));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-tests-btn'));
    await waitFor(() => expect(screen.getByTestId('no-tests')).toBeInTheDocument());
  });

  it('shows list-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(500, 'Internal error'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-tests-btn'));
    await waitFor(() => expect(screen.getByTestId('list-error')).toBeInTheDocument());
    expect(screen.getByTestId('list-error').textContent).toContain('Internal error');
  });

  it('adds a test case and shows result', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(TEST_CASE)) // POST /tests
      .mockResolvedValueOnce(makeOk(TEST_LIST)); // GET /tests (refresh)
    renderPage();
    fillFlowId();
    fireEvent.change(screen.getByTestId('add-name-input'), { target: { value: 'Basic pass' } });
    fireEvent.click(screen.getByTestId('add-btn'));
    await waitFor(() => expect(screen.getByTestId('add-result')).toBeInTheDocument());
    expect(screen.getByTestId('new-test-id').textContent).toBe('tc-001');
  });

  it('shows add-error on invalid input JSON', async () => {
    renderPage();
    fillFlowId();
    fireEvent.change(screen.getByTestId('add-name-input'), { target: { value: 'Bad' } });
    fireEvent.change(screen.getByTestId('add-input-json'), { target: { value: 'not-json' } });
    fireEvent.click(screen.getByTestId('add-btn'));
    await waitFor(() => expect(screen.getByTestId('add-error')).toBeInTheDocument());
    expect(screen.getByTestId('add-error').textContent).toContain('Invalid JSON in Input');
  });

  it('shows add-error on invalid expected JSON', async () => {
    renderPage();
    fillFlowId();
    fireEvent.change(screen.getByTestId('add-name-input'), { target: { value: 'Bad' } });
    fireEvent.change(screen.getByTestId('add-expected-json'), { target: { value: 'not-json' } });
    fireEvent.click(screen.getByTestId('add-btn'));
    await waitFor(() => expect(screen.getByTestId('add-error')).toBeInTheDocument());
    expect(screen.getByTestId('add-error').textContent).toContain('Invalid JSON in Expected');
  });

  it('deletes a test case', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(TEST_LIST)) // initial load
      .mockResolvedValueOnce(makeNoContent());   // DELETE
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-tests-btn'));
    await waitFor(() => screen.getAllByTestId('test-row'));
    const deleteBtn = screen.getAllByTestId('delete-btn')[0];
    fireEvent.click(deleteBtn);
    await waitFor(() => expect(screen.getAllByTestId('test-row')).toHaveLength(1));
  });

  it('loads summary', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(SUMMARY));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-summary-btn'));
    await waitFor(() => screen.getByTestId('summary-cards'));
    expect(screen.getByTestId('summary-total').textContent).toBe('2');
    expect(screen.getByTestId('summary-passed').textContent).toBe('1');
    expect(screen.getByTestId('summary-failed').textContent).toBe('1');
  });

  it('shows summary-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(500, 'No summary'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-summary-btn'));
    await waitFor(() => expect(screen.getByTestId('summary-error')).toBeInTheDocument());
  });

  it('runs test suite and shows results', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(RUN_RESULT));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('run-btn'));
    await waitFor(() => screen.getByTestId('run-results'));
    expect(screen.getByTestId('exit-code').textContent).toBe('1');
    const items = screen.getAllByTestId('run-result-item');
    expect(items).toHaveLength(2);
  });

  it('shows run-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(500, 'Runner down'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('run-btn'));
    await waitFor(() => expect(screen.getByTestId('run-error')).toBeInTheDocument());
    expect(screen.getByTestId('run-error').textContent).toContain('Runner down');
  });

  it('loads results history', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(RESULTS_LIST));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-results-btn'));
    await waitFor(() => screen.getByTestId('results-list'));
    expect(screen.getAllByTestId('result-item')).toHaveLength(1);
    expect(screen.getByTestId('result-status').textContent).toBe('pass');
  });

  it('shows no-results when history is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ results: [], total: 0 }));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-results-btn'));
    await waitFor(() => expect(screen.getByTestId('no-results')).toBeInTheDocument());
  });

  it('shows results-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Flow not found'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-results-btn'));
    await waitFor(() => expect(screen.getByTestId('results-error')).toBeInTheDocument());
  });

  it('handles array response shape for test list', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk([TEST_CASE]));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-tests-btn'));
    await waitFor(() => screen.getByTestId('tests-table'));
    expect(screen.getAllByTestId('test-row')).toHaveLength(1);
  });
});
