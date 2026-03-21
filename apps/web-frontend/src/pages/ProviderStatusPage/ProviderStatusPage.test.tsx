/**
 * Unit tests for ProviderStatusPage (N-91).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ProviderStatusPage from './ProviderStatusPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const DISCOVERED = {
  providers: [
    { name: 'openai', status: 'available', capabilities: ['chat', 'embeddings'] },
    { name: 'anthropic', status: 'available', capabilities: ['chat'] },
  ],
  total: 2,
  discovery: 'filesystem',
};

const LLM_PROVIDERS = {
  items: [
    { name: 'openai', models: ['gpt-4o', 'gpt-3.5-turbo'] },
    { name: 'anthropic', models: ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001'] },
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

const IMAGE_PROVIDERS = {
  items: [{ name: 'stability', models: ['sdxl', 'sd3'] }],
  total: 1,
  page: 1,
  page_size: 20,
};

const HEALTH_RESULT = {
  name: 'openai',
  status: 'healthy',
  latency_ms: 42,
};

function mockAllEndpoints() {
  vi.mocked(fetch)
    .mockResolvedValueOnce({ ok: true, json: async () => DISCOVERED } as Response)
    .mockResolvedValueOnce({ ok: true, json: async () => LLM_PROVIDERS } as Response)
    .mockResolvedValueOnce({ ok: true, json: async () => IMAGE_PROVIDERS } as Response);
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProviderStatusPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ProviderStatusPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    mockAllEndpoints();
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows discovered provider rows', async () => {
    mockAllEndpoints();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('discovered-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('discovered-row');
    expect(rows).toHaveLength(2);
    // Check text within the discovered table rows specifically
    expect(rows[0].textContent).toContain('openai');
    expect(rows[1].textContent).toContain('anthropic');
  });

  it('shows status badges on discovered rows', async () => {
    mockAllEndpoints();
    renderPage();
    await waitFor(() => screen.getByTestId('discovered-table'));
    const badges = screen.getAllByTestId('provider-status-badge');
    expect(badges).toHaveLength(2);
    expect(badges[0].textContent).toContain('available');
  });

  it('shows no-discovered when empty', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ providers: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => LLM_PROVIDERS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => IMAGE_PROVIDERS } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-discovered')).toBeInTheDocument());
  });

  it('shows providers-error on discovery failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: false, status: 500 } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => LLM_PROVIDERS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => IMAGE_PROVIDERS } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('providers-error')).toBeInTheDocument());
  });

  it('shows LLM provider rows with model counts', async () => {
    mockAllEndpoints();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('llm-list')).toBeInTheDocument());
    const rows = screen.getAllByTestId('llm-row');
    expect(rows).toHaveLength(2);
    // Both openai and anthropic have 2 models each — check first row
    expect(rows[0].textContent).toContain('2 models');
  });

  it('shows image provider rows', async () => {
    mockAllEndpoints();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('image-list')).toBeInTheDocument());
    expect(screen.getAllByTestId('image-row')).toHaveLength(1);
    expect(screen.getByText('stability')).toBeInTheDocument();
  });

  it('health check btn triggers health fetch and shows badge', async () => {
    mockAllEndpoints();
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => HEALTH_RESULT,
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('discovered-table'));
    fireEvent.click(screen.getAllByTestId('health-check-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('health-badge')).toBeInTheDocument());
    expect(screen.getByTestId('health-badge').textContent).toContain('healthy');
    expect(screen.getByTestId('health-badge').textContent).toContain('42ms');
  });

  it('shows health-error on health check failure', async () => {
    mockAllEndpoints();
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Provider 'openai' not found" }),
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('discovered-table'));
    fireEvent.click(screen.getAllByTestId('health-check-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('health-error')).toBeInTheDocument());
    expect(screen.getByTestId('health-error').textContent).toContain('not found');
  });

  it('refresh-btn reloads all providers', async () => {
    mockAllEndpoints();
    mockAllEndpoints();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(6));
  });

  it('capabilities shown as comma-separated string', async () => {
    mockAllEndpoints();
    renderPage();
    await waitFor(() => screen.getByTestId('discovered-table'));
    expect(screen.getByText('chat, embeddings')).toBeInTheDocument();
  });
});
