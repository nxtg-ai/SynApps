/**
 * Unit tests for WorkflowPermissionsPage (N-82).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkflowPermissionsPage from './WorkflowPermissionsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PERMS_TWO_GRANTS = {
  flow_id: 'flow-abc',
  permissions: {
    owner: 'alice@example.com',
    grants: [
      { user_id: 'bob@example.com', role: 'editor' },
      { user_id: 'carol@example.com', role: 'viewer' },
    ],
  },
};

const PERMS_NO_GRANTS = {
  flow_id: 'flow-abc',
  permissions: {
    owner: 'alice@example.com',
    grants: [],
  },
};

const SHARE_RESPONSE = {
  flow_id: 'flow-abc',
  shared_with: 'dave@example.com',
  role: 'viewer',
  permissions: {
    owner: 'alice@example.com',
    grants: [{ user_id: 'dave@example.com', role: 'viewer' }],
  },
};

const REVOKE_RESPONSE = {
  flow_id: 'flow-abc',
  revoked: 'bob@example.com',
  permissions: {
    owner: 'alice@example.com',
    grants: [{ user_id: 'carol@example.com', role: 'viewer' }],
  },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowPermissionsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowPermissionsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and no-flow state', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('no-flow-state')).toBeInTheDocument();
  });

  it('load button disabled when input is empty', () => {
    renderPage();
    expect(screen.getByTestId('load-flow-btn')).toBeDisabled();
  });

  it('shows perms panel with owner and grants', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => PERMS_TWO_GRANTS } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-flow-btn'));
    await waitFor(() => expect(screen.getByTestId('perms-panel')).toBeInTheDocument());
    expect(screen.getByTestId('owner-row')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByTestId('grants-table')).toBeInTheDocument();
    expect(screen.getAllByTestId('grant-row')).toHaveLength(2);
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
    expect(screen.getByText('carol@example.com')).toBeInTheDocument();
  });

  it('shows no-grants message when grants is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => PERMS_NO_GRANTS } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-flow-btn'));
    await waitFor(() => expect(screen.getByTestId('no-grants')).toBeInTheDocument());
  });

  it('shows perms-error on load failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 404 } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'bad-id' } });
    fireEvent.click(screen.getByTestId('load-flow-btn'));
    await waitFor(() => expect(screen.getByTestId('perms-error')).toBeInTheDocument());
  });

  it('share button disabled when user input is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => PERMS_NO_GRANTS } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-flow-btn'));
    await waitFor(() => screen.getByTestId('share-btn'));
    expect(screen.getByTestId('share-btn')).toBeDisabled();
  });

  it('share success shows success message and updates grants', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PERMS_NO_GRANTS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => SHARE_RESPONSE } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-flow-btn'));
    await waitFor(() => screen.getByTestId('share-section'));
    fireEvent.change(screen.getByTestId('share-user-input'), { target: { value: 'dave@example.com' } });
    fireEvent.click(screen.getByTestId('share-btn'));
    await waitFor(() => expect(screen.getByTestId('share-success')).toBeInTheDocument());
    expect(screen.getByText('dave@example.com')).toBeInTheDocument();
  });

  it('share error shown on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PERMS_NO_GRANTS } as Response)
      .mockResolvedValueOnce({ ok: false, status: 403, json: async () => ({ detail: 'Only owner can share' }) } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-flow-btn'));
    await waitFor(() => screen.getByTestId('share-section'));
    fireEvent.change(screen.getByTestId('share-user-input'), { target: { value: 'dave@example.com' } });
    fireEvent.click(screen.getByTestId('share-btn'));
    await waitFor(() => expect(screen.getByTestId('share-error')).toBeInTheDocument());
    expect(screen.getByTestId('share-error').textContent).toContain('Only owner can share');
  });

  it('revoke removes grant from table', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PERMS_TWO_GRANTS } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => REVOKE_RESPONSE } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-flow-btn'));
    await waitFor(() => screen.getByTestId('grants-table'));
    expect(screen.getAllByTestId('grant-row')).toHaveLength(2);
    fireEvent.click(screen.getAllByTestId('revoke-btn')[0]);
    await waitFor(() => expect(screen.getAllByTestId('grant-row')).toHaveLength(1));
  });

  it('role badges display correct text', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => PERMS_TWO_GRANTS } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-flow-btn'));
    await waitFor(() => screen.getByTestId('grants-table'));
    const badges = screen.getAllByTestId('role-badge');
    expect(badges[0].textContent).toBe('editor');
    expect(badges[1].textContent).toBe('viewer');
  });
});
