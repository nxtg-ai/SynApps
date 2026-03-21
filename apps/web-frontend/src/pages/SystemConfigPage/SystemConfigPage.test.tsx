/**
 * Unit tests for SystemConfigPage (N-108).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import SystemConfigPage from './SystemConfigPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VERSION_DATA = {
  api_version: '2026-01-01',
  app_version: '1.0.0',
  supported_versions: ['2026-01-01', '2025-12-01'],
  deprecated_endpoints: [{ path: '/api/v1/old-endpoint', sunset: '2026-06-01' }],
  sunset_grace_days: 30,
};

const METRICS_DATA = {
  total_requests: 1234,
  error_rate: 0.02,
  avg_response_ms: 145,
};

const CONFIG_DATA = {
  database_url: '***REDACTED***',
  debug: false,
  max_connections: 100,
  _validation_errors: [],
  _env_file_loaded: '/app/.env.development',
};

const CONFIG_WITH_ERRORS = {
  ...CONFIG_DATA,
  _validation_errors: ['OPENAI_API_KEY is not set', 'DATABASE_URL missing'],
};

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function setupAllMocks() {
  vi.mocked(fetch)
    .mockResolvedValueOnce(makeOk(VERSION_DATA))   // /version
    .mockResolvedValueOnce(makeOk(METRICS_DATA))   // /metrics
    .mockResolvedValueOnce(makeOk(CONFIG_DATA));    // /config
}

function renderPage() {
  return render(
    <MemoryRouter>
      <SystemConfigPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SystemConfigPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'tok');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and tabs', async () => {
    setupAllMocks();
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('tab-version')).toBeInTheDocument();
    expect(screen.getByTestId('tab-metrics')).toBeInTheDocument();
    expect(screen.getByTestId('tab-config')).toBeInTheDocument();
  });

  it('loads and shows version data on mount', async () => {
    setupAllMocks();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('version-detail')).toBeInTheDocument());
    expect(screen.getByTestId('api-version').textContent).toBe('2026-01-01');
    expect(screen.getByTestId('app-version').textContent).toBe('1.0.0');
    expect(screen.getByTestId('sunset-days').textContent).toBe('30');
  });

  it('shows supported versions', async () => {
    setupAllMocks();
    renderPage();
    await waitFor(() => screen.getByTestId('supported-versions'));
    const items = screen.getAllByTestId('supported-version-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe('2026-01-01');
  });

  it('shows deprecated endpoints', async () => {
    setupAllMocks();
    renderPage();
    await waitFor(() => screen.getByTestId('deprecated-section'));
    const items = screen.getAllByTestId('deprecated-item');
    expect(items).toHaveLength(1);
    expect(items[0].textContent).toContain('/api/v1/old-endpoint');
    expect(items[0].textContent).toContain('2026-06-01');
  });

  it('shows version-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeErr(500, 'Server error'))
      .mockResolvedValueOnce(makeOk(METRICS_DATA))
      .mockResolvedValueOnce(makeOk(CONFIG_DATA));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('version-error')).toBeInTheDocument());
    expect(screen.getByTestId('version-error').textContent).toContain('Server error');
  });

  it('switches to metrics tab and shows data', async () => {
    setupAllMocks();
    renderPage();
    await waitFor(() => screen.getByTestId('tab-metrics'));
    fireEvent.click(screen.getByTestId('tab-metrics'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-metrics')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('metrics-json')).toBeInTheDocument());
    expect(screen.getByTestId('metrics-json').textContent).toContain('1234');
  });

  it('shows metrics-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeErr(401, 'Unauthorized'))
      .mockResolvedValueOnce(makeOk(CONFIG_DATA));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-metrics'));
    await waitFor(() => expect(screen.getByTestId('metrics-error')).toBeInTheDocument());
  });

  it('switches to config tab and shows data', async () => {
    setupAllMocks();
    renderPage();
    fireEvent.click(screen.getByTestId('tab-config'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-config')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('config-json')).toBeInTheDocument());
    expect(screen.getByTestId('config-json').textContent).toContain('REDACTED');
  });

  it('shows env file path in config', async () => {
    setupAllMocks();
    renderPage();
    fireEvent.click(screen.getByTestId('tab-config'));
    await waitFor(() => screen.getByTestId('env-file'));
    expect(screen.getByTestId('env-file').textContent).toContain('.env.development');
  });

  it('shows config validation errors', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(METRICS_DATA))
      .mockResolvedValueOnce(makeOk(CONFIG_WITH_ERRORS));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-config'));
    await waitFor(() => screen.getByTestId('validation-errors'));
    const items = screen.getAllByTestId('validation-error-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('OPENAI_API_KEY');
  });

  it('shows config-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(METRICS_DATA))
      .mockResolvedValueOnce(makeErr(403, 'Forbidden'));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-config'));
    await waitFor(() => expect(screen.getByTestId('config-error')).toBeInTheDocument());
  });

  it('refresh button re-fetches all', async () => {
    setupAllMocks();
    // Second round of fetches for refresh
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_DATA))
      .mockResolvedValueOnce(makeOk(METRICS_DATA))
      .mockResolvedValueOnce(makeOk(CONFIG_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('version-detail'));
    fireEvent.click(screen.getByTestId('refresh-btn'));
    // fetch should have been called 6 times total (3 mount + 3 refresh)
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(6));
  });
});
