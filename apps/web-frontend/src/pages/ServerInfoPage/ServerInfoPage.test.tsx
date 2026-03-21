/**
 * Unit tests for ServerInfoPage (N-98).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ServerInfoPage from './ServerInfoPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VERSION_DATA = {
  api_version: '2026-03-20',
  app_version: '1.0.0',
  supported_versions: ['2026-03-20', '2026-02-01'],
  deprecated_endpoints: [{ path: '/old/endpoint', sunset_date: '2027-01-01' }],
  sunset_grace_days: 90,
};

const CONFIG_DATA = {
  debug: false,
  max_nodes: 100,
  secret_key: '[REDACTED]',
  _validation_errors: [],
  _env_file_loaded: '/app/.env.development',
};

const METRICS_DATA = {
  total_requests: 4200,
  error_rate: 0.02,
  avg_response_ms: 55.3,
  provider_usage: { openai: 1200, anthropic: 800 },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ServerInfoPage />
    </MemoryRouter>,
  );
}

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ServerInfoPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and tabs', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(VERSION_DATA));
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('info-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('tab-version')).toBeInTheDocument();
    expect(screen.getByTestId('tab-config')).toBeInTheDocument();
    expect(screen.getByTestId('tab-metrics')).toBeInTheDocument();
  });

  it('version tab loads and shows api_version and app_version', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(VERSION_DATA));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('version-panel')).toBeInTheDocument());
    expect(screen.getByTestId('api-version').textContent).toBe('2026-03-20');
    expect(screen.getByTestId('app-version').textContent).toBe('1.0.0');
  });

  it('version tab shows supported versions', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(VERSION_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('supported-versions'));
    expect(screen.getByTestId('supported-versions').textContent).toContain('2026-03-20');
    expect(screen.getByTestId('supported-versions').textContent).toContain('2026-02-01');
  });

  it('version tab shows deprecated endpoints', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(VERSION_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('deprecated-list'));
    const items = screen.getAllByTestId('deprecated-item');
    expect(items).toHaveLength(1);
    expect(items[0].textContent).toContain('/old/endpoint');
  });

  it('version tab shows info-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(500, 'Server error'));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('info-error')).toBeInTheDocument());
    expect(screen.getByTestId('info-error').textContent).toContain('Server error');
  });

  it('config tab loads and shows config JSON', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(CONFIG_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('version-panel'));
    fireEvent.click(screen.getByTestId('tab-config'));
    await waitFor(() => expect(screen.getByTestId('config-panel')).toBeInTheDocument());
    expect(screen.getByTestId('config-json')).toBeInTheDocument();
    expect(screen.getByTestId('config-json').textContent).toContain('REDACTED');
  });

  it('config tab shows env-file-loaded', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(CONFIG_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('version-panel'));
    fireEvent.click(screen.getByTestId('tab-config'));
    await waitFor(() => screen.getByTestId('env-file-loaded'));
    expect(screen.getByTestId('env-file-loaded').textContent).toContain('.env.development');
  });

  it('config tab shows validation errors when present', async () => {
    const configWithErrors = {
      ...CONFIG_DATA,
      _validation_errors: ['Missing API key', 'Invalid port'],
    };
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(configWithErrors));
    renderPage();
    await waitFor(() => screen.getByTestId('version-panel'));
    fireEvent.click(screen.getByTestId('tab-config'));
    await waitFor(() => screen.getAllByTestId('config-validation-error'));
    const errors = screen.getAllByTestId('config-validation-error');
    expect(errors).toHaveLength(2);
    expect(errors[0].textContent).toContain('Missing API key');
  });

  it('metrics tab loads and shows metric cards', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(METRICS_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('version-panel'));
    fireEvent.click(screen.getByTestId('tab-metrics'));
    await waitFor(() => expect(screen.getByTestId('metrics-panel')).toBeInTheDocument());
    const cards = screen.getAllByTestId('metric-card');
    expect(cards.length).toBeGreaterThanOrEqual(3);
  });

  it('metrics tab shows individual metric values', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(METRICS_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('version-panel'));
    fireEvent.click(screen.getByTestId('tab-metrics'));
    await waitFor(() => screen.getByTestId('metrics-panel'));
    const values = screen.getAllByTestId('metric-value');
    const allText = values.map((v) => v.textContent).join(' ');
    expect(allText).toContain('4200');
  });

  it('metrics tab shows info-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeErr(403, 'Forbidden'));
    renderPage();
    await waitFor(() => screen.getByTestId('version-panel'));
    fireEvent.click(screen.getByTestId('tab-metrics'));
    await waitFor(() => expect(screen.getByTestId('info-error')).toBeInTheDocument());
  });

  it('refresh-btn re-fetches active tab', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(VERSION_DATA));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
