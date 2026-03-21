/**
 * Unit tests for OAuthInspectorPage (N-113).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import OAuthInspectorPage from './OAuthInspectorPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const INTROSPECT_ACTIVE = {
  active: true,
  sub: 'user-123',
  client_id: 'app-client',
  scope: 'read write',
  exp: 1900000000,
};

const INTROSPECT_INACTIVE = { active: false };

const AUTHORIZE_RESULT = { code: 'authcode-abc', state: 'xyz' };

const TOKEN_RESULT = {
  access_token: 'tok-xyz',
  token_type: 'bearer',
  expires_in: 3600,
  scope: 'read',
};

const MONITORING_RESULT = {
  workflow: {
    flow_id: 'flow-abc',
    status: 'healthy',
    total_runs: 42,
    success_rate: 0.95,
    avg_duration_ms: 1200,
  },
  window_hours: 24,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OAuthInspectorPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('OAuthInspectorPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'tok');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  // 1. Renders page title and all tabs
  it('renders page title and four tabs', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('page-title').textContent).toBe('OAuth Inspector');
    expect(screen.getByTestId('tab-introspect')).toBeInTheDocument();
    expect(screen.getByTestId('tab-authorize')).toBeInTheDocument();
    expect(screen.getByTestId('tab-token')).toBeInTheDocument();
    expect(screen.getByTestId('tab-monitoring')).toBeInTheDocument();
  });

  // 2. Introspect active token — shows active/sub/client_id/scope
  it('introspects an active token and shows claims', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(INTROSPECT_ACTIVE));
    renderPage();

    fireEvent.change(screen.getByTestId('token-input'), {
      target: { value: 'my-active-token' },
    });
    fireEvent.click(screen.getByTestId('introspect-btn'));

    await waitFor(() => expect(screen.getByTestId('introspect-result')).toBeInTheDocument());

    expect(screen.getByTestId('introspect-active').textContent).toBe('active');
    expect(screen.getByTestId('introspect-sub').textContent).toBe('user-123');
    expect(screen.getByTestId('introspect-client-id').textContent).toBe('app-client');
    expect(screen.getByTestId('introspect-scope').textContent).toBe('read write');
    expect(screen.getByTestId('introspect-json').textContent).toContain('"active": true');
  });

  // 3. Introspect inactive token — shows "inactive"
  it('introspects an inactive token and shows inactive status', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(INTROSPECT_INACTIVE));
    renderPage();

    fireEvent.change(screen.getByTestId('token-input'), {
      target: { value: 'expired-token' },
    });
    fireEvent.click(screen.getByTestId('introspect-btn'));

    await waitFor(() => expect(screen.getByTestId('introspect-result')).toBeInTheDocument());

    expect(screen.getByTestId('introspect-active').textContent).toBe('inactive');
    expect(screen.queryByTestId('introspect-sub')).not.toBeInTheDocument();
    expect(screen.queryByTestId('introspect-client-id')).not.toBeInTheDocument();
    expect(screen.queryByTestId('introspect-scope')).not.toBeInTheDocument();
  });

  // 4. Introspect API error
  it('shows introspect-error when API returns an error', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(401, 'Unauthorized'));
    renderPage();

    fireEvent.change(screen.getByTestId('token-input'), {
      target: { value: 'bad-token' },
    });
    fireEvent.click(screen.getByTestId('introspect-btn'));

    await waitFor(() => expect(screen.getByTestId('introspect-error')).toBeInTheDocument());
    expect(screen.getByTestId('introspect-error').textContent).toContain('Unauthorized');
  });

  // 5. Authorize — shows auth code
  it('authorize flow returns and displays auth code', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(AUTHORIZE_RESULT));
    renderPage();

    fireEvent.click(screen.getByTestId('tab-authorize'));
    fireEvent.change(screen.getByTestId('auth-client-id'), {
      target: { value: 'my-client' },
    });
    fireEvent.click(screen.getByTestId('authorize-btn'));

    await waitFor(() => expect(screen.getByTestId('authorize-result')).toBeInTheDocument());
    expect(screen.getByTestId('auth-code').textContent).toBe('authcode-abc');
  });

  // 6. Authorize API error
  it('shows authorize-error when API returns an error', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(400, 'Invalid client_id'));
    renderPage();

    fireEvent.click(screen.getByTestId('tab-authorize'));
    fireEvent.click(screen.getByTestId('authorize-btn'));

    await waitFor(() => expect(screen.getByTestId('authorize-error')).toBeInTheDocument());
    expect(screen.getByTestId('authorize-error').textContent).toContain('Invalid client_id');
  });

  // 7. Token exchange — shows access token
  it('token exchange returns and displays token details', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(TOKEN_RESULT));
    renderPage();

    fireEvent.click(screen.getByTestId('tab-token'));
    fireEvent.change(screen.getByTestId('token-client-id'), {
      target: { value: 'my-client' },
    });
    fireEvent.change(screen.getByTestId('token-client-secret'), {
      target: { value: 'secret' },
    });
    // authorization_code is default, so code and redirect-uri fields are visible
    fireEvent.change(screen.getByTestId('token-code'), {
      target: { value: 'authcode-abc' },
    });
    fireEvent.click(screen.getByTestId('get-token-btn'));

    await waitFor(() => expect(screen.getByTestId('token-result')).toBeInTheDocument());

    expect(screen.getByTestId('token-access-token').textContent).toBe('tok-xyz');
    expect(screen.getByTestId('token-type').textContent).toBe('bearer');
    expect(screen.getByTestId('token-expires-in').textContent).toBe('3600');
    expect(screen.getByTestId('token-scope-result').textContent).toBe('read');
  });

  // 8. Token API error
  it('shows token-error when API returns an error', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(400, 'Invalid grant'));
    renderPage();

    fireEvent.click(screen.getByTestId('tab-token'));
    fireEvent.click(screen.getByTestId('get-token-btn'));

    await waitFor(() => expect(screen.getByTestId('token-error')).toBeInTheDocument());
    expect(screen.getByTestId('token-error').textContent).toContain('Invalid grant');
  });

  // 9. Monitoring detail — shows flow health
  it('monitoring loads and displays workflow health detail', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(MONITORING_RESULT));
    renderPage();

    fireEvent.click(screen.getByTestId('tab-monitoring'));
    fireEvent.change(screen.getByTestId('monitoring-flow-id'), {
      target: { value: 'flow-abc' },
    });
    fireEvent.click(screen.getByTestId('load-monitoring-btn'));

    await waitFor(() => expect(screen.getByTestId('monitoring-result')).toBeInTheDocument());

    expect(screen.getByTestId('monitoring-flow-id-result').textContent).toBe('flow-abc');
    expect(screen.getByTestId('monitoring-status').textContent).toBe('healthy');
    expect(screen.getByTestId('monitoring-total-runs').textContent).toBe('42');
    expect(screen.getByTestId('monitoring-success-rate').textContent).toBe('0.95');
    expect(screen.getByTestId('monitoring-json').textContent).toContain('"flow_id": "flow-abc"');
  });

  // 10. Monitoring not-found (404) error
  it('monitoring shows error on 404 not found', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Workflow not found'));
    renderPage();

    fireEvent.click(screen.getByTestId('tab-monitoring'));
    fireEvent.change(screen.getByTestId('monitoring-flow-id'), {
      target: { value: 'nonexistent-flow' },
    });
    fireEvent.click(screen.getByTestId('load-monitoring-btn'));

    await waitFor(() => expect(screen.getByTestId('monitoring-error')).toBeInTheDocument());
    expect(screen.getByTestId('monitoring-error').textContent).toContain('not found');
  });

  // 11. Tab switching works
  it('switching tabs shows the correct panel', () => {
    renderPage();

    // Default: introspect panel visible
    expect(screen.getByTestId('tab-panel-introspect')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-panel-authorize')).not.toBeInTheDocument();

    // Switch to authorize
    fireEvent.click(screen.getByTestId('tab-authorize'));
    expect(screen.getByTestId('tab-panel-authorize')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-panel-introspect')).not.toBeInTheDocument();

    // Switch to token
    fireEvent.click(screen.getByTestId('tab-token'));
    expect(screen.getByTestId('tab-panel-token')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-panel-authorize')).not.toBeInTheDocument();

    // Switch to monitoring
    fireEvent.click(screen.getByTestId('tab-monitoring'));
    expect(screen.getByTestId('tab-panel-monitoring')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-panel-token')).not.toBeInTheDocument();
  });

  // 12. Monitoring loading state
  it('shows monitoring-loading indicator while fetching', async () => {
    let resolvePromise!: (value: Response) => void;
    const pendingPromise = new Promise<Response>((res) => {
      resolvePromise = res;
    });
    vi.mocked(fetch).mockReturnValueOnce(pendingPromise);
    renderPage();

    fireEvent.click(screen.getByTestId('tab-monitoring'));
    fireEvent.change(screen.getByTestId('monitoring-flow-id'), {
      target: { value: 'flow-abc' },
    });
    fireEvent.click(screen.getByTestId('load-monitoring-btn'));

    expect(screen.getByTestId('monitoring-loading')).toBeInTheDocument();

    // Resolve to avoid act() warnings
    resolvePromise(makeOk(MONITORING_RESULT));
    await waitFor(() => expect(screen.queryByTestId('monitoring-loading')).not.toBeInTheDocument());
  });
});
