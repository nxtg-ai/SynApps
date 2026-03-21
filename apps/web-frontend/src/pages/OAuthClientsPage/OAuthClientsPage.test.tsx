/**
 * Unit tests for OAuthClientsPage (N-95).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import OAuthClientsPage from './OAuthClientsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CLIENTS_LIST = [
  {
    client_id: 'client-aaa',
    name: 'My App',
    allowed_scopes: ['read', 'write'],
    grant_types: ['authorization_code'],
  },
  {
    client_id: 'client-bbb',
    name: 'CLI Tool',
    allowed_scopes: ['read'],
    grant_types: ['client_credentials'],
  },
];

const NEW_CLIENT = {
  client_id: 'client-new-123',
  name: 'New App',
  client_secret: 'supersecret456',
  allowed_scopes: ['read', 'write'],
  grant_types: ['authorization_code'],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <OAuthClientsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('OAuthClientsPage', () => {
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

  it('shows client rows in table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => CLIENTS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('clients-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('client-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('My App')).toBeInTheDocument();
  });

  it('shows no-clients when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-clients')).toBeInTheDocument());
  });

  it('shows clients-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('clients-error')).toBeInTheDocument());
  });

  it('register btn disabled when name empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('register-form'));
    expect(screen.getByTestId('register-btn')).toBeDisabled();
  });

  it('registering shows client_id and client_secret in success panel', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => NEW_CLIENT } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('register-form'));
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'New App' } });
    fireEvent.submit(screen.getByTestId('register-form'));
    await waitFor(() => expect(screen.getByTestId('register-success')).toBeInTheDocument());
    expect(screen.getByTestId('new-client-id').textContent).toContain('client-new-123');
    expect(screen.getByTestId('new-client-secret').textContent).toContain('supersecret456');
  });

  it('new client appears in table after registration', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => NEW_CLIENT } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('register-form'));
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'New App' } });
    fireEvent.submit(screen.getByTestId('register-form'));
    await waitFor(() => screen.getByTestId('register-success'));
    expect(screen.getByTestId('clients-table')).toBeInTheDocument();
    expect(screen.getAllByTestId('client-row')).toHaveLength(1);
  });

  it('shows register-error on registration failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Invalid client name' }),
      } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('register-form'));
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'bad' } });
    fireEvent.submit(screen.getByTestId('register-form'));
    await waitFor(() => expect(screen.getByTestId('register-error')).toBeInTheDocument());
    expect(screen.getByTestId('register-error').textContent).toContain('Invalid client name');
  });

  it('revoking a client removes its row', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => CLIENTS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => null, status: 204 } as unknown as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('clients-table'));
    fireEvent.click(screen.getAllByTestId('revoke-btn')[0]);
    await waitFor(() => expect(screen.getAllByTestId('client-row')).toHaveLength(1));
  });

  it('shows revoke-error on revocation failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => CLIENTS_LIST } as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'OAuth2 client not found' }),
      } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('clients-table'));
    fireEvent.click(screen.getAllByTestId('revoke-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('revoke-error')).toBeInTheDocument());
    expect(screen.getByTestId('revoke-error').textContent).toContain('not found');
  });

  it('refresh-btn reloads client list', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => CLIENTS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => CLIENTS_LIST } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
