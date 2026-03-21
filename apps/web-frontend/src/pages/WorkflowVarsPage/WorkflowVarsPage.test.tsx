/**
 * Unit tests for WorkflowVarsPage (N-74).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkflowVarsPage from './WorkflowVarsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VARS_RESPONSE = {
  flow_id: 'flow-abc',
  variables: { env: 'production', retries: '3' },
  count: 2,
};

const VARS_EMPTY = {
  flow_id: 'flow-abc',
  variables: {},
  count: 0,
};

const SECRETS_RESPONSE = {
  flow_id: 'flow-abc',
  secrets: { API_KEY: '***', DB_PASS: '***' },
  count: 2,
};

const SECRETS_SAVED = {
  flow_id: 'flow-abc',
  secrets: { API_KEY: '***', DB_PASS: '***' },
  count: 2,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowVarsPage />
    </MemoryRouter>,
  );
}

function loadFlow() {
  fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
  fireEvent.submit(screen.getByTestId('flow-selector-form'));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowVarsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and flow selector form', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('flow-selector-form')).toBeInTheDocument();
    expect(screen.getByTestId('flow-id-input')).toBeInTheDocument();
  });

  it('load-flow-btn is disabled when flow ID is empty', () => {
    renderPage();
    expect(screen.getByTestId('load-flow-btn')).toBeDisabled();
  });

  it('shows no-flow-state before any flow is loaded', () => {
    renderPage();
    expect(screen.getByTestId('no-flow-state')).toBeInTheDocument();
  });

  it('shows panels-container after flow ID submitted', async () => {
    renderPage();
    loadFlow();
    expect(screen.getByTestId('panels-container')).toBeInTheDocument();
    expect(screen.getByTestId('variables-panel')).toBeInTheDocument();
    expect(screen.getByTestId('secrets-panel')).toBeInTheDocument();
  });

  it('loads variables and shows table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => VARS_RESPONSE,
    } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('vars-table')).toBeInTheDocument());
    expect(screen.getAllByTestId('var-row')).toHaveLength(2);
    expect(screen.getByText('env')).toBeInTheDocument();
    expect(screen.getByText('production')).toBeInTheDocument();
  });

  it('shows vars-no-entries when variables is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => VARS_EMPTY,
    } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('vars-no-entries')).toBeInTheDocument());
  });

  it('shows vars-error on load failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 404 } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('vars-error')).toBeInTheDocument());
  });

  it('opens vars editor on edit click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => VARS_RESPONSE } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('edit-vars-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-vars-btn'));
    expect(screen.getByTestId('vars-editor')).toBeInTheDocument();
    expect(screen.getByTestId('vars-json-input')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-vars-btn')).toBeInTheDocument();
  });

  it('saves variables successfully', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => VARS_RESPONSE } as Response) // load
      .mockResolvedValueOnce({ ok: true, json: async () => VARS_RESPONSE } as Response); // save

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('edit-vars-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-vars-btn'));
    fireEvent.click(screen.getByTestId('save-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('vars-success')).toBeInTheDocument());
  });

  it('shows vars-error on save failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => VARS_RESPONSE } as Response) // load
      .mockResolvedValueOnce({ ok: false, status: 422 } as Response); // save

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('edit-vars-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-vars-btn'));
    fireEvent.click(screen.getByTestId('save-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('vars-error')).toBeInTheDocument());
  });

  it('loads secrets and shows masked table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => SECRETS_RESPONSE,
    } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-secrets-btn'));

    await waitFor(() => expect(screen.getByTestId('secrets-table')).toBeInTheDocument());
    expect(screen.getAllByTestId('secret-row')).toHaveLength(2);
    expect(screen.getByText('API_KEY')).toBeInTheDocument();
  });

  it('shows secrets-error on load failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 404 } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-secrets-btn'));

    await waitFor(() => expect(screen.getByTestId('secrets-error')).toBeInTheDocument());
  });

  it('opens secrets editor on set-secrets click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SECRETS_RESPONSE } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-secrets-btn'));

    await waitFor(() => expect(screen.getByTestId('edit-secrets-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-secrets-btn'));
    expect(screen.getByTestId('secrets-editor')).toBeInTheDocument();
    expect(screen.getByTestId('secrets-json-input')).toBeInTheDocument();
  });

  it('saves secrets successfully', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => SECRETS_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => SECRETS_SAVED } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-secrets-btn'));

    await waitFor(() => expect(screen.getByTestId('edit-secrets-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-secrets-btn'));
    fireEvent.click(screen.getByTestId('save-secrets-btn'));

    await waitFor(() => expect(screen.getByTestId('secrets-success')).toBeInTheDocument());
  });

  it('cancel-vars-btn hides editor', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => VARS_RESPONSE } as Response);

    renderPage();
    loadFlow();
    fireEvent.click(screen.getByTestId('load-vars-btn'));

    await waitFor(() => expect(screen.getByTestId('edit-vars-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-vars-btn'));
    expect(screen.getByTestId('vars-editor')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('cancel-vars-btn'));
    expect(screen.queryByTestId('vars-editor')).not.toBeInTheDocument();
  });
});
