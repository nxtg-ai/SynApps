/**
 * Unit tests for PortfolioDashboardPage (N-105).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import PortfolioDashboardPage from './PortfolioDashboardPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PORTFOLIO_DATA = {
  templates: [
    { name: '2brain', last_run: '2026-03-21T00:00:00' },
    { name: 'multi-agent', last_run: null },
  ],
  template_count: 2,
  providers: [
    { name: 'openai', configured: true, model_count: 4 },
    { name: 'anthropic', configured: false, model_count: 0, reason: 'No key' },
  ],
  provider_count: 2,
  health: { status: 'healthy', database: 'reachable', uptime_seconds: 3661, version: '1.0.0' },
};

const HEALTH_DATA = {
  status: 'healthy',
  database: 'reachable',
  uptime_seconds: 7200,
  providers: [
    { name: 'openai', configured: true },
    { name: 'anthropic', configured: false },
  ],
};

const PROFILE_DATA = {
  id: 'user-abc-123',
  email: 'alice@example.com',
  is_active: true,
  created_at: '2026-01-01T00:00:00',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <PortfolioDashboardPage />
    </MemoryRouter>,
  );
}

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function setupAllMocks() {
  vi.mocked(fetch)
    .mockResolvedValueOnce(makeOk(PORTFOLIO_DATA))  // portfolio
    .mockResolvedValueOnce(makeOk(HEALTH_DATA))      // health
    .mockResolvedValueOnce(makeOk(PROFILE_DATA));    // profile
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PortfolioDashboardPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and tabs', async () => {
    setupAllMocks();
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('tab-portfolio')).toBeInTheDocument();
    expect(screen.getByTestId('tab-health')).toBeInTheDocument();
    expect(screen.getByTestId('tab-profile')).toBeInTheDocument();
  });

  it('loads and shows portfolio data on mount', async () => {
    setupAllMocks();
    renderPage();
    await waitFor(() => expect(screen.getByTestId('tab-panel-portfolio')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('health-summary')).toBeInTheDocument());
    expect(screen.getByTestId('portfolio-status').textContent).toContain('healthy');
    expect(screen.getByTestId('portfolio-db').textContent).toContain('reachable');
    expect(screen.getByTestId('portfolio-template-count').textContent).toBe('2');
  });

  it('shows provider badges', async () => {
    setupAllMocks();
    renderPage();
    await waitFor(() => screen.getByTestId('providers-section'));
    const badges = screen.getAllByTestId('provider-badge');
    expect(badges).toHaveLength(2);
    expect(badges[0].textContent).toContain('openai');
  });

  it('shows templates table', async () => {
    setupAllMocks();
    renderPage();
    await waitFor(() => screen.getByTestId('templates-table'));
    const rows = screen.getAllByTestId('template-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('2brain');
  });

  it('shows portfolio-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeErr(500, 'Internal error'))
      .mockResolvedValueOnce(makeOk(HEALTH_DATA))
      .mockResolvedValueOnce(makeOk(PROFILE_DATA));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('portfolio-error')).toBeInTheDocument());
    expect(screen.getByTestId('portfolio-error').textContent).toContain('Internal error');
  });

  it('switches to health tab and shows health data', async () => {
    setupAllMocks();
    renderPage();
    await waitFor(() => screen.getByTestId('tab-health'));
    fireEvent.click(screen.getByTestId('tab-health'));
    await waitFor(() => expect(screen.getByTestId('tab-panel-health')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('health-detail')).toBeInTheDocument());
    expect(screen.getByTestId('health-status').textContent).toContain('healthy');
    expect(screen.getByTestId('health-uptime').textContent).toBe('2h 0m');
  });

  it('shows health-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(PORTFOLIO_DATA))
      .mockResolvedValueOnce(makeErr(503, 'Database unreachable'))
      .mockResolvedValueOnce(makeOk(PROFILE_DATA));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-health'));
    await waitFor(() => expect(screen.getByTestId('health-error')).toBeInTheDocument());
    expect(screen.getByTestId('health-error').textContent).toContain('Database unreachable');
  });

  it('shows health provider items', async () => {
    setupAllMocks();
    renderPage();
    fireEvent.click(screen.getByTestId('tab-health'));
    await waitFor(() => screen.getByTestId('health-providers'));
    const items = screen.getAllByTestId('health-provider-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe('openai');
  });

  it('switches to profile tab and shows profile data', async () => {
    setupAllMocks();
    renderPage();
    fireEvent.click(screen.getByTestId('tab-profile'));
    await waitFor(() => expect(screen.getByTestId('profile-card')).toBeInTheDocument());
    expect(screen.getByTestId('profile-email').textContent).toBe('alice@example.com');
    expect(screen.getByTestId('profile-id').textContent).toBe('user-abc-123');
    expect(screen.getByTestId('profile-active').textContent).toContain('Active');
  });

  it('shows profile-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(PORTFOLIO_DATA))
      .mockResolvedValueOnce(makeOk(HEALTH_DATA))
      .mockResolvedValueOnce(makeErr(401, 'Unauthorized'));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-profile'));
    await waitFor(() => expect(screen.getByTestId('profile-error')).toBeInTheDocument());
    expect(screen.getByTestId('profile-error').textContent).toContain('Unauthorized');
  });

  it('inactive user shows Inactive status', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(PORTFOLIO_DATA))
      .mockResolvedValueOnce(makeOk(HEALTH_DATA))
      .mockResolvedValueOnce(makeOk({ ...PROFILE_DATA, is_active: false }));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-profile'));
    await waitFor(() => screen.getByTestId('profile-active'));
    expect(screen.getByTestId('profile-active').textContent).toContain('Inactive');
  });

  it('no-templates shown when template list is empty', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ ...PORTFOLIO_DATA, templates: [], template_count: 0 }))
      .mockResolvedValueOnce(makeOk(HEALTH_DATA))
      .mockResolvedValueOnce(makeOk(PROFILE_DATA));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-templates')).toBeInTheDocument());
  });

  it('uptime formatted correctly for sub-minute durations', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        makeOk({ ...PORTFOLIO_DATA, health: { ...PORTFOLIO_DATA.health, uptime_seconds: 45 } }),
      )
      .mockResolvedValueOnce(makeOk(HEALTH_DATA))
      .mockResolvedValueOnce(makeOk(PROFILE_DATA));
    renderPage();
    await waitFor(() => screen.getByTestId('portfolio-uptime'));
    expect(screen.getByTestId('portfolio-uptime').textContent).toBe('45s');
  });
});
