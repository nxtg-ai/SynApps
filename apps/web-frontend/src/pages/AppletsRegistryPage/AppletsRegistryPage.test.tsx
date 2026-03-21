/**
 * Unit tests for AppletsRegistryPage (N-94).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import AppletsRegistryPage from './AppletsRegistryPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const APPLETS_LIST = [
  {
    type: 'llm',
    name: 'LLM Node',
    description: 'Universal LLM node',
    version: '1.0.0',
    input_schema: { text: 'string' },
    output_schema: { result: 'string' },
  },
  {
    type: 'http_request',
    name: 'HTTP Request',
    description: 'Make HTTP API calls',
    version: '1.0.0',
  },
  {
    type: 'code',
    name: 'Code Node',
    description: 'Run sandboxed Python',
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <AppletsRegistryPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AppletsRegistryPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows applet items in list', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => APPLETS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('applets-list')).toBeInTheDocument());
    const items = screen.getAllByTestId('applet-item');
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain('llm');
  });

  it('shows no-applets when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-applets')).toBeInTheDocument());
  });

  it('shows applets-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('applets-error')).toBeInTheDocument());
  });

  it('shows no-applet-selected initially', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => APPLETS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('applets-list'));
    expect(screen.getByTestId('no-applet-selected')).toBeInTheDocument();
  });

  it('clicking applet shows detail panel', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => APPLETS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('applets-list'));
    fireEvent.click(screen.getAllByTestId('applet-item')[0]);
    expect(screen.getByTestId('applet-detail')).toBeInTheDocument();
    expect(screen.getByTestId('detail-type').textContent).toContain('llm');
    expect(screen.getByTestId('detail-description').textContent).toContain('Universal LLM node');
  });

  it('shows input and output schema sections', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => APPLETS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('applets-list'));
    fireEvent.click(screen.getAllByTestId('applet-item')[0]);
    expect(screen.getByTestId('input-schema-section')).toBeInTheDocument();
    expect(screen.getByTestId('output-schema-section')).toBeInTheDocument();
  });

  it('search filters applet list', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => APPLETS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('applets-list'));
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'http' } });
    const items = screen.getAllByTestId('applet-item');
    expect(items).toHaveLength(1);
    expect(items[0].textContent).toContain('http_request');
  });

  it('handles paginated response shape', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ items: APPLETS_LIST, total: 3, page: 1, page_size: 20 }),
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('applets-list')).toBeInTheDocument());
    expect(screen.getAllByTestId('applet-item')).toHaveLength(3);
  });

  it('refresh-btn reloads applets', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLETS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLETS_LIST } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
