/**
 * Tests for TestRunnerPage -- CI-compatible workflow test runner.
 *
 * Covers: loading state, test cases list, add form, submit, run suite,
 * pass/fail results, diff viewer, exit code banner, delete, error state.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, afterEach, beforeEach } from 'vitest';
import TestRunnerPage from './TestRunnerPage';

// ---------------------------------------------------------------------------
// Mock MainLayout so the page renders in isolation
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock ApiService
// ---------------------------------------------------------------------------

vi.mock('../../services/ApiService', () => ({
  apiService: {
    getFlowTests: vi.fn(),
    addFlowTest: vi.fn(),
    deleteFlowTest: vi.fn(),
    runFlowTests: vi.fn(),
    getFlowTestResults: vi.fn(),
    getFlowTestSummary: vi.fn(),
  },
}));

import { apiService } from '../../services/ApiService';

const mockGetFlowTests = vi.mocked(apiService.getFlowTests);
const mockAddFlowTest = vi.mocked(apiService.addFlowTest);
const mockDeleteFlowTest = vi.mocked(apiService.deleteFlowTest);
const mockRunFlowTests = vi.mocked(apiService.runFlowTests);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTestCase(overrides: Partial<any> = {}) {
  return {
    test_id: 'tc-1',
    flow_id: 'flow-1',
    name: 'Smoke Test',
    description: 'Basic check',
    input: { prompt: 'hi' },
    expected_output: { text: 'hello' },
    match_mode: 'contains' as const,
    created_at: Date.now() / 1000,
    created_by: 'user@test.com',
    ...overrides,
  };
}

function makeRunResponse(overrides: Partial<any> = {}) {
  return {
    results: [
      {
        result_id: 'r-1',
        test_id: 'tc-1',
        flow_id: 'flow-1',
        run_id: 'run-1',
        status: 'pass',
        actual_output: { text: 'hello' },
        expected_output: { text: 'hello' },
        diff: {},
        error_message: '',
        duration_ms: 123,
        ran_at: Date.now() / 1000,
      },
    ],
    summary: { total: 1, passed: 1, failed: 0, error: 0, pass_rate_pct: 100 },
    exit_code: 0,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/workflows/flow-1/tests']}>
      <Routes>
        <Route path="/workflows/:id/tests" element={<TestRunnerPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TestRunnerPage', () => {
  it('shows loading state', () => {
    mockGetFlowTests.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByLabelText('Loading test runner')).toBeInTheDocument();
  });

  it('renders test cases list', async () => {
    const tc = makeTestCase();
    mockGetFlowTests.mockResolvedValue({ tests: [tc], total: 1 });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Smoke Test')).toBeInTheDocument();
    });
  });

  it('shows add test form', async () => {
    mockGetFlowTests.mockResolvedValue({ tests: [], total: 0 });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('add-test-form')).toBeInTheDocument();
    });
  });

  it('submit adds test case', async () => {
    mockGetFlowTests.mockResolvedValue({ tests: [], total: 0 });
    mockAddFlowTest.mockResolvedValue(makeTestCase());
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('add-test-form')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('test-name-input'), {
      target: { value: 'New Test' },
    });
    fireEvent.click(screen.getByTestId('submit-test-button'));

    await waitFor(() => {
      expect(mockAddFlowTest).toHaveBeenCalledWith('flow-1', expect.objectContaining({ name: 'New Test' }));
    });
  });

  it('run suite button triggers API', async () => {
    const tc = makeTestCase();
    mockGetFlowTests.mockResolvedValue({ tests: [tc], total: 1 });
    mockRunFlowTests.mockResolvedValue(makeRunResponse());
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('run-suite-button')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('run-suite-button'));

    await waitFor(() => {
      expect(mockRunFlowTests).toHaveBeenCalledWith('flow-1');
    });
  });

  it('shows pass result', async () => {
    mockGetFlowTests.mockResolvedValue({ tests: [makeTestCase()], total: 1 });
    mockRunFlowTests.mockResolvedValue(makeRunResponse());
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('run-suite-button')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('run-suite-button'));

    await waitFor(() => {
      expect(screen.getByText('PASS')).toBeInTheDocument();
    });
  });

  it('shows fail result with diff', async () => {
    const failResponse = makeRunResponse({
      results: [
        {
          result_id: 'r-1',
          test_id: 'tc-1',
          flow_id: 'flow-1',
          run_id: 'run-1',
          status: 'fail',
          actual_output: { text: 'wrong' },
          expected_output: { text: 'hello' },
          diff: { text: { expected: 'hello', actual: 'wrong' } },
          error_message: '',
          duration_ms: 100,
          ran_at: Date.now() / 1000,
        },
      ],
      summary: { total: 1, passed: 0, failed: 1, error: 0, pass_rate_pct: 0 },
      exit_code: 1,
    });
    mockGetFlowTests.mockResolvedValue({ tests: [makeTestCase()], total: 1 });
    mockRunFlowTests.mockResolvedValue(failResponse);
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('run-suite-button')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('run-suite-button'));

    await waitFor(() => {
      expect(screen.getByText('FAIL')).toBeInTheDocument();
      expect(screen.getByTestId('diff-viewer')).toBeInTheDocument();
    });
  });

  it('shows exit code banner', async () => {
    mockGetFlowTests.mockResolvedValue({ tests: [makeTestCase()], total: 1 });
    mockRunFlowTests.mockResolvedValue(makeRunResponse());
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('run-suite-button')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('run-suite-button'));

    await waitFor(() => {
      expect(screen.getByTestId('exit-code-banner')).toHaveTextContent('All tests passed');
    });
  });

  it('delete test calls DELETE API', async () => {
    const tc = makeTestCase();
    mockGetFlowTests.mockResolvedValue({ tests: [tc], total: 1 });
    mockDeleteFlowTest.mockResolvedValue(undefined);
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId(`delete-test-${tc.test_id}`)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId(`delete-test-${tc.test_id}`));

    await waitFor(() => {
      expect(mockDeleteFlowTest).toHaveBeenCalledWith('flow-1', 'tc-1');
    });
  });

  it('shows error state', async () => {
    mockGetFlowTests.mockRejectedValue(new Error('Network error'));
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('error-banner')).toBeInTheDocument();
      expect(
        screen.getByText('Failed to load test cases. Please try again.'),
      ).toBeInTheDocument();
    });
  });
});
