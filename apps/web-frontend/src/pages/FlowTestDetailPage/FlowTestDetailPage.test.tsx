import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import FlowTestDetailPage from './FlowTestDetailPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <span data-testid="layout-title">{title}</span>
      {children}
    </div>
  ),
}));

const SAMPLE_TEST = {
  test_id: 'tst-abc123',
  name: 'Happy path test',
  description: 'Ensures the default case passes',
  input: { key: 'value' },
  expected_output: { result: 'ok' },
  match_mode: 'exact',
  created_by: 'user-1',
  created_at: '2026-03-21T10:00:00Z',
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <FlowTestDetailPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok-test');
});

describe('FlowTestDetailPage', () => {
  // 1. Page title
  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Flow Test Detail');
  });

  // 2. Empty state on load
  it('shows empty state initially', () => {
    renderPage();
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
  });

  // 3. Fetch button disabled without IDs
  it('fetch button is disabled when inputs empty', () => {
    renderPage();
    expect(screen.getByTestId('fetch-btn')).toBeDisabled();
  });

  // 4. Fetch button enabled with both IDs
  it('enables fetch button when both IDs provided', () => {
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-abc123' } });
    expect(screen.getByTestId('fetch-btn')).not.toBeDisabled();
  });

  // 5. Calls correct endpoint
  it('calls GET /flows/{flow_id}/tests/{test_id}', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(SAMPLE_TEST));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-abc123' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/flows/flow-1/tests/tst-abc123'),
        expect.any(Object),
      ),
    );
  });

  // 6. Test name displayed
  it('displays test case name', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_TEST)));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-abc123' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('test-name')).toHaveTextContent('Happy path test'),
    );
  });

  // 7. Test description displayed
  it('displays test case description', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_TEST)));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-abc123' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('test-description')).toHaveTextContent('Ensures the default case passes'),
    );
  });

  // 8. Match mode badge shown
  it('shows match mode badge', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_TEST)));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-abc123' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('test-match-mode')).toHaveTextContent('exact'),
    );
  });

  // 9. Test ID in meta section
  it('shows test ID in meta', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_TEST)));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-abc123' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('meta-test-id')).toHaveTextContent('tst-abc123'),
    );
  });

  // 10. Input JSON rendered
  it('displays input JSON in pre block', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_TEST)));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-abc123' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('test-input-json')).toHaveTextContent('value'),
    );
  });

  // 11. Expected output JSON rendered
  it('displays expected output JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAMPLE_TEST)));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-abc123' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('test-expected-json')).toHaveTextContent('ok'),
    );
  });

  // 12. 404 error displayed
  it('shows error on 404 response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(404, 'Test not found')));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'missing' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('fetch-error')).toHaveTextContent('Test not found'),
    );
  });

  // 13. Network error displayed
  it('shows network error on fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network down')));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('test-id-input'), { target: { value: 'tst-1' } });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('fetch-error')).toHaveTextContent('Network error'),
    );
  });
});
