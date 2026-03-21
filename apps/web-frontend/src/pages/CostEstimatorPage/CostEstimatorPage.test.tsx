/**
 * Unit tests for CostEstimatorPage (N-93).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import CostEstimatorPage from './CostEstimatorPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ESTIMATE_RESULT = {
  estimated_usd: 0.000825,
  total_token_input: 100,
  total_token_output: 200,
  breakdown: [
    {
      node_id: 'llm-1',
      node_type: 'llm',
      model: 'gpt-4o',
      token_input: 100,
      token_output: 200,
      estimated_usd: 0.000825,
    },
    {
      node_id: 'http-1',
      node_type: 'http_request',
      estimated_usd: 0,
    },
  ],
};

const ESTIMATE_EMPTY_BREAKDOWN = {
  estimated_usd: 0,
  total_token_input: 0,
  total_token_output: 0,
  breakdown: [],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <CostEstimatorPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CostEstimatorPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('estimate btn disabled when flow-id empty', () => {
    renderPage();
    expect(screen.getByTestId('estimate-btn')).toBeDisabled();
  });

  it('shows estimate-result with total usd and breakdown', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ESTIMATE_RESULT,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), {
      target: { value: 'flow-abc' },
    });
    fireEvent.submit(screen.getByTestId('estimate-form'));
    await waitFor(() => expect(screen.getByTestId('estimate-result')).toBeInTheDocument());
    expect(screen.getByTestId('total-usd').textContent).toContain('$0.000825');
    expect(screen.getByTestId('total-token-input').textContent).toContain('100');
    expect(screen.getByTestId('total-token-output').textContent).toContain('200');
  });

  it('shows breakdown rows', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ESTIMATE_RESULT,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('estimate-form'));
    await waitFor(() => screen.getByTestId('breakdown-table'));
    expect(screen.getAllByTestId('breakdown-row')).toHaveLength(2);
  });

  it('shows no-breakdown when breakdown is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ESTIMATE_EMPTY_BREAKDOWN,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-empty' } });
    fireEvent.submit(screen.getByTestId('estimate-form'));
    await waitFor(() => expect(screen.getByTestId('no-breakdown')).toBeInTheDocument());
  });

  it('shows estimate-error on 404', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Flow not found' }),
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'bad-id' } });
    fireEvent.submit(screen.getByTestId('estimate-form'));
    await waitFor(() => expect(screen.getByTestId('estimate-error')).toBeInTheDocument());
    expect(screen.getByTestId('estimate-error').textContent).toContain('Flow not found');
  });

  it('formats usd to 6 decimal places', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ESTIMATE_RESULT,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('estimate-form'));
    await waitFor(() => screen.getByTestId('estimate-result'));
    expect(screen.getByTestId('total-usd').textContent).toMatch(/\$\d+\.\d{6}/);
  });

  it('sends input_text in request body', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ESTIMATE_RESULT,
    } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('input-text'), {
      target: { value: 'sample input text' },
    });
    fireEvent.submit(screen.getByTestId('estimate-form'));
    await waitFor(() => screen.getByTestId('estimate-result'));
    const call = vi.mocked(fetch).mock.calls[0];
    const body = JSON.parse(call[1]?.body as string);
    expect(body.input_text).toBe('sample input text');
  });
});
