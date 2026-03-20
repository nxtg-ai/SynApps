/**
 * Tests for RollbackPage -- workflow versioned rollback system.
 *
 * Covers: loading state, version list, rollback buttons, confirmation modal,
 * reason textarea, API call on confirm, success banner, audit log table,
 * empty audit state, error state.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, afterEach, beforeEach } from 'vitest';
import RollbackPage from './RollbackPage';

// ---------------------------------------------------------------------------
// Mock MainLayout so the page renders in isolation
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock ApiService
// ---------------------------------------------------------------------------

vi.mock('../../services/ApiService', () => ({
  apiService: {
    getFlowVersions: vi.fn(),
    rollbackFlow: vi.fn(),
    getRollbackHistory: vi.fn(),
  },
}));

import { apiService } from '../../services/ApiService';

const mockGetFlowVersions = vi.mocked(apiService.getFlowVersions);
const mockRollbackFlow = vi.mocked(apiService.rollbackFlow);
const mockGetRollbackHistory = vi.mocked(apiService.getRollbackHistory);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeVersions(count: number = 2) {
  return Array.from({ length: count }, (_, i) => ({
    version_id: `ver-${i + 1}`,
    flow_id: 'flow-1',
    version: i + 1,
    snapshotted_at: new Date(2026, 2, 20 - count + i + 1).toISOString(),
  }));
}

function makeAuditEntries(count: number = 1) {
  return Array.from({ length: count }, (_, i) => ({
    audit_id: `audit-${i + 1}`,
    flow_id: 'flow-1',
    from_version_id: `from-ver-${i + 1}`,
    to_version_id: `to-ver-${i + 1}`,
    performed_by: `user-${i + 1}`,
    reason: `reason ${i + 1}`,
    rolled_back_at: Date.now() / 1000 - i * 60,
  }));
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/workflows/flow-1/rollback']}>
      <Routes>
        <Route path="/workflows/:id/rollback" element={<RollbackPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RollbackPage', () => {
  it('shows loading state', () => {
    mockGetFlowVersions.mockReturnValue(new Promise(() => {}));
    mockGetRollbackHistory.mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.getByLabelText('Loading rollback data')).toBeInTheDocument();
  });

  it('renders version list', async () => {
    const versions = makeVersions(3);
    mockGetFlowVersions.mockResolvedValue({ items: versions });
    mockGetRollbackHistory.mockResolvedValue({ items: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('version-row-ver-1')).toBeInTheDocument();
      expect(screen.getByTestId('version-row-ver-2')).toBeInTheDocument();
      expect(screen.getByTestId('version-row-ver-3')).toBeInTheDocument();
    });
  });

  it('shows rollback button per version', async () => {
    const versions = makeVersions(2);
    mockGetFlowVersions.mockResolvedValue({ items: versions });
    mockGetRollbackHistory.mockResolvedValue({ items: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('rollback-button-ver-1')).toBeInTheDocument();
      expect(screen.getByTestId('rollback-button-ver-2')).toBeInTheDocument();
    });
  });

  it('clicking rollback button opens confirmation modal', async () => {
    const versions = makeVersions(1);
    mockGetFlowVersions.mockResolvedValue({ items: versions });
    mockGetRollbackHistory.mockResolvedValue({ items: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('rollback-button-ver-1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('rollback-button-ver-1'));

    expect(screen.getByTestId('confirm-rollback-modal')).toBeInTheDocument();
  });

  it('modal has reason textarea', async () => {
    const versions = makeVersions(1);
    mockGetFlowVersions.mockResolvedValue({ items: versions });
    mockGetRollbackHistory.mockResolvedValue({ items: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('rollback-button-ver-1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('rollback-button-ver-1'));

    expect(screen.getByTestId('rollback-reason-textarea')).toBeInTheDocument();
  });

  it('confirm triggers API call with reason', async () => {
    const versions = makeVersions(1);
    mockGetFlowVersions.mockResolvedValue({ items: versions });
    mockGetRollbackHistory.mockResolvedValue({ items: [] });
    mockRollbackFlow.mockResolvedValue({
      flow: { id: 'flow-1', name: 'Test', nodes: [], edges: [] } as any,
      rolled_back_to: 'ver-1',
      audit_entry: makeAuditEntries(1)[0],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('rollback-button-ver-1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('rollback-button-ver-1'));

    const textarea = screen.getByTestId('rollback-reason-textarea');
    fireEvent.change(textarea, { target: { value: 'bad deploy' } });

    fireEvent.click(screen.getByTestId('confirm-rollback-button'));

    await waitFor(() => {
      expect(mockRollbackFlow).toHaveBeenCalledWith('flow-1', 'ver-1', 'bad deploy');
    });
  });

  it('shows success banner after rollback', async () => {
    const versions = makeVersions(1);
    mockGetFlowVersions.mockResolvedValue({ items: versions });
    mockGetRollbackHistory.mockResolvedValue({ items: [] });
    mockRollbackFlow.mockResolvedValue({
      flow: { id: 'flow-1', name: 'Test', nodes: [], edges: [] } as any,
      rolled_back_to: 'ver-1',
      audit_entry: makeAuditEntries(1)[0],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('rollback-button-ver-1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('rollback-button-ver-1'));
    fireEvent.click(screen.getByTestId('confirm-rollback-button'));

    await waitFor(() => {
      expect(screen.getByTestId('success-banner')).toHaveTextContent('Rolled back to v1!');
    });
  });

  it('renders audit log table', async () => {
    const versions = makeVersions(1);
    const entries = makeAuditEntries(2);
    mockGetFlowVersions.mockResolvedValue({ items: versions });
    mockGetRollbackHistory.mockResolvedValue({ items: entries });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('audit-log-table')).toBeInTheDocument();
    });
  });

  it('shows empty audit log state', async () => {
    const versions = makeVersions(1);
    mockGetFlowVersions.mockResolvedValue({ items: versions });
    mockGetRollbackHistory.mockResolvedValue({ items: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('empty-audit-log')).toBeInTheDocument();
      expect(screen.getByText('No rollbacks recorded yet.')).toBeInTheDocument();
    });
  });

  it('shows error state if API fails', async () => {
    mockGetFlowVersions.mockRejectedValue(new Error('Network error'));
    mockGetRollbackHistory.mockRejectedValue(new Error('Network error'));

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('error-banner')).toBeInTheDocument();
      expect(screen.getByText('Failed to load rollback data. Please try again.')).toBeInTheDocument();
    });
  });
});
