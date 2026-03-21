/**
 * Tests for CollabLocksPage — N-114 Collaboration Locks & Bulk Cost Estimate.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import React from 'react';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import CollabLocksPage from './CollabLocksPage';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ACQUIRE_RESULT = { locked: true, node_id: 'node-1', user_id: 'user-123' };
const RELEASE_RESULT = { released: true, node_id: 'node-1' };
const LOCKS_DATA = {
  locks: {
    'node-1': { user_id: 'user-123', username: 'alice@example.com', locked_at: 1711000000 },
    'node-2': { user_id: 'user-456', username: 'bob@example.com', locked_at: 1711001000 },
  },
};
const LOCKS_EMPTY = { locks: {} };
const ESTIMATE_RESULT = {
  total_cost: 0.0045,
  currency: 'USD',
  breakdown: [
    { node_id: 'node-1', node_type: 'llm', cost: 0.003 },
    { node_id: 'node-2', node_type: 'image', cost: 0.0015 },
  ],
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
      <CollabLocksPage />
    </MemoryRouter>,
  );
}

function fillFlowId(value = 'flow-abc') {
  fireEvent.change(screen.getByTestId('lock-flow-id'), { target: { value } });
}

function fillNodeId(value = 'node-1') {
  fireEvent.change(screen.getByTestId('lock-node-id'), { target: { value } });
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok');
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CollabLocksPage', () => {
  it('renders page title and tabs', () => {
    renderPage();
    expect(screen.getByTestId('page-title').textContent).toContain('Collab Locks');
    expect(screen.getByTestId('tab-locks')).toBeTruthy();
    expect(screen.getByTestId('tab-cost')).toBeTruthy();
  });

  it('acquire lock success — shows acquire-result with locked=true', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeOk(ACQUIRE_RESULT));
    renderPage();
    fillFlowId();
    fillNodeId();
    fireEvent.click(screen.getByTestId('acquire-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('acquire-result')).toBeTruthy();
    });
    expect(screen.getByTestId('acquire-locked').textContent).toBe('true');
  });

  it('acquire lock 409 conflict — shows acquire-error with "already locked"', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      makeErr(409, 'already locked'),
    );
    renderPage();
    fillFlowId();
    fillNodeId();
    fireEvent.click(screen.getByTestId('acquire-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('acquire-error')).toBeTruthy();
    });
    expect(screen.getByTestId('acquire-error').textContent).toContain('already locked');
  });

  it('acquire lock API error — shows acquire-error', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeErr(500, 'internal error'));
    renderPage();
    fillFlowId();
    fillNodeId();
    fireEvent.click(screen.getByTestId('acquire-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('acquire-error')).toBeTruthy();
    });
    expect(screen.getByTestId('acquire-error').textContent).toContain('internal error');
  });

  it('release lock success — shows release-result with released=true', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeOk(RELEASE_RESULT));
    renderPage();
    fillFlowId();
    fillNodeId();
    fireEvent.click(screen.getByTestId('release-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('release-result')).toBeTruthy();
    });
    expect(screen.getByTestId('release-released').textContent).toBe('true');
  });

  it('release lock API error — shows release-error', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeErr(404, 'lock not found'));
    renderPage();
    fillFlowId();
    fillNodeId();
    fireEvent.click(screen.getByTestId('release-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('release-error')).toBeTruthy();
    });
    expect(screen.getByTestId('release-error').textContent).toContain('lock not found');
  });

  it('load locks success — shows lock items (2 locks)', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeOk(LOCKS_DATA));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-locks-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('locks-list')).toBeTruthy();
    });

    const items = screen.getAllByTestId('lock-item');
    expect(items.length).toBe(2);

    const nodeIds = screen.getAllByTestId('lock-item-node-id').map((el) => el.textContent);
    expect(nodeIds).toContain('node-1');
    expect(nodeIds).toContain('node-2');

    const users = screen.getAllByTestId('lock-item-user').map((el) => el.textContent);
    expect(users).toContain('alice@example.com');
    expect(users).toContain('bob@example.com');
  });

  it('load locks empty state — shows no-locks message', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeOk(LOCKS_EMPTY));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-locks-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('no-locks')).toBeTruthy();
    });
  });

  it('load locks error — shows locks-error', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeErr(403, 'forbidden'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-locks-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('locks-error')).toBeTruthy();
    });
    expect(screen.getByTestId('locks-error').textContent).toContain('forbidden');
  });

  it('bulk estimate success — shows total, currency, breakdown items', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeOk(ESTIMATE_RESULT));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-cost'));

    fireEvent.change(screen.getByTestId('nodes-json'), {
      target: { value: '[{"type":"llm"},{"type":"image"}]' },
    });
    fireEvent.change(screen.getByTestId('foreach-iterations'), { target: { value: '5' } });
    fireEvent.click(screen.getByTestId('estimate-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('estimate-result')).toBeTruthy();
    });

    expect(screen.getByTestId('estimate-total').textContent).toContain('0.0045');
    expect(screen.getByTestId('estimate-currency').textContent).toBe('USD');

    expect(screen.getByTestId('estimate-breakdown')).toBeTruthy();
    const items = screen.getAllByTestId('estimate-item');
    expect(items.length).toBe(2);

    const nodeLabels = screen.getAllByTestId('estimate-item-node').map((el) => el.textContent);
    expect(nodeLabels.some((t) => t?.includes('node-1'))).toBe(true);
    expect(nodeLabels.some((t) => t?.includes('node-2'))).toBe(true);

    const costs = screen.getAllByTestId('estimate-item-cost').map((el) => el.textContent);
    expect(costs.some((t) => t?.includes('0.003'))).toBe(true);
    expect(costs.some((t) => t?.includes('0.0015'))).toBe(true);
  });

  it('bulk estimate invalid JSON — shows estimate-error with "Invalid JSON"', async () => {
    renderPage();
    fireEvent.click(screen.getByTestId('tab-cost'));

    fireEvent.change(screen.getByTestId('nodes-json'), {
      target: { value: 'not valid json {{{' },
    });
    fireEvent.click(screen.getByTestId('estimate-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('estimate-error')).toBeTruthy();
    });
    expect(screen.getByTestId('estimate-error').textContent).toContain('Invalid JSON');
  });

  it('bulk estimate API error — shows estimate-error', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(makeErr(422, 'unprocessable'));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-cost'));

    fireEvent.change(screen.getByTestId('nodes-json'), {
      target: { value: '[]' },
    });
    fireEvent.click(screen.getByTestId('estimate-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('estimate-error')).toBeTruthy();
    });
    expect(screen.getByTestId('estimate-error').textContent).toContain('unprocessable');
  });

  it('tab switching works — cost panel visible after clicking tab-cost', () => {
    renderPage();
    // Locks panel is visible by default
    expect(screen.getByTestId('tab-panel-locks')).toBeTruthy();

    // Switch to cost tab
    fireEvent.click(screen.getByTestId('tab-cost'));
    expect(screen.getByTestId('tab-panel-cost')).toBeTruthy();
    expect(screen.queryByTestId('tab-panel-locks')).toBeNull();

    // Switch back to locks tab
    fireEvent.click(screen.getByTestId('tab-locks'));
    expect(screen.getByTestId('tab-panel-locks')).toBeTruthy();
    expect(screen.queryByTestId('tab-panel-cost')).toBeNull();
  });
});
