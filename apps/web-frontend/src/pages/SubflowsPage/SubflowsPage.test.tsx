/**
 * Unit tests for SubflowsPage (N-84).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import SubflowsPage from './SubflowsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TWO_SUBFLOWS = {
  flows: [
    { id: 'flow-1', name: 'Writer Pipeline', is_subflow_compatible: true, created_at: '2024-01-10T00:00:00Z' },
    { id: 'flow-2', name: 'Data Processor', is_subflow_compatible: true, created_at: '2024-01-12T00:00:00Z' },
  ],
  total: 2,
};

const EMPTY_SUBFLOWS = { flows: [], total: 0 };

const VALIDATE_OK = { valid: true, error: null };
const VALIDATE_CYCLE = { valid: false, error: "Workflow 'flow-1' cannot reference itself as a subflow" };

function renderPage() {
  return render(
    <MemoryRouter>
      <SubflowsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SubflowsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and validate section', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => TWO_SUBFLOWS } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('validate-section')).toBeInTheDocument();
  });

  it('shows subflow table with rows', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => TWO_SUBFLOWS } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('subflows-table')).toBeInTheDocument());
    expect(screen.getAllByTestId('subflow-row')).toHaveLength(2);
    expect(screen.getByText('Writer Pipeline')).toBeInTheDocument();
    expect(screen.getByText('Data Processor')).toBeInTheDocument();
  });

  it('shows no-subflows when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => EMPTY_SUBFLOWS } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-subflows')).toBeInTheDocument());
  });

  it('shows subflows-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('subflows-error')).toBeInTheDocument());
  });

  it('validate btn disabled when inputs empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => EMPTY_SUBFLOWS } as Response);
    renderPage();
    expect(screen.getByTestId('validate-btn')).toBeDisabled();
  });

  it('validate-ok shown on successful validation', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_SUBFLOWS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_OK } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('parent-id-input'), { target: { value: 'flow-a' } });
    fireEvent.change(screen.getByTestId('subflow-id-input'), { target: { value: 'flow-b' } });
    fireEvent.click(screen.getByTestId('validate-btn'));
    await waitFor(() => expect(screen.getByTestId('validate-ok')).toBeInTheDocument());
  });

  it('validate-error shown on cycle detection', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_SUBFLOWS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_CYCLE } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('parent-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('subflow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.click(screen.getByTestId('validate-btn'));
    await waitFor(() => expect(screen.getByTestId('validate-error')).toBeInTheDocument());
    expect(screen.getByTestId('validate-error').textContent).toContain('cannot reference itself');
  });

  it('shows plural "workflows" for count > 1', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => TWO_SUBFLOWS } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('subflows-panel'));
    expect(screen.getByTestId('subflows-panel').textContent).toContain('2 workflows');
  });

  it('refresh-btn reloads subflows', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => TWO_SUBFLOWS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_SUBFLOWS } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(screen.getByTestId('no-subflows')).toBeInTheDocument());
  });
});
