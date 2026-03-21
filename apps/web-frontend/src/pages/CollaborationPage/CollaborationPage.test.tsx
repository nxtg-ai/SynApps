/**
 * Tests for CollaborationPage -- Multi-user workflow collaboration UI.
 */
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import CollaborationPage from './CollaborationPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let mockFetch: Mock;

function renderPage() {
  return render(
    <MemoryRouter>
      <CollaborationPage />
    </MemoryRouter>,
  );
}

function joinResponse() {
  return {
    ok: true,
    json: async () => ({
      user_id: 'u1',
      color: '#FF6B6B',
      collaborators: [
        { user_id: 'u1', username: 'alice', color: '#FF6B6B', last_seen: Date.now() / 1000 },
      ],
    }),
  };
}

function presenceResponse(collaborators: Array<{ user_id: string; username: string; color: string; last_seen: number }> = []) {
  return {
    ok: true,
    json: async () => ({
      collaborators: collaborators.length > 0
        ? collaborators
        : [{ user_id: 'u1', username: 'alice', color: '#FF6B6B', last_seen: Date.now() / 1000 }],
    }),
  };
}

function locksResponse(locks: Record<string, unknown> = {}) {
  return { ok: true, json: async () => ({ locks }) };
}

function activityResponse(activity: Array<{ user_id: string; username: string; action: string; detail: string; timestamp: number }> = []) {
  return {
    ok: true,
    json: async () => ({
      activity: activity.length > 0
        ? activity
        : [{ user_id: 'u1', username: 'alice', action: 'joined', detail: '', timestamp: Date.now() / 1000 }],
    }),
  };
}

/** Queue standard post-join poll responses (presence, locks, activity). */
function queuePollResponses(opts?: { emptyPresence?: boolean; emptyActivity?: boolean }) {
  if (opts?.emptyPresence) {
    mockFetch.mockResolvedValueOnce(presenceResponse([]));
  } else {
    mockFetch.mockResolvedValueOnce(presenceResponse());
  }
  mockFetch.mockResolvedValueOnce(locksResponse());
  if (opts?.emptyActivity) {
    mockFetch.mockResolvedValueOnce(activityResponse([]));
  } else {
    mockFetch.mockResolvedValueOnce(activityResponse());
  }
}

/** Simulate a full join flow: join response + initial poll responses. */
async function joinSession(opts?: { emptyPresence?: boolean; emptyActivity?: boolean }) {
  mockFetch.mockResolvedValueOnce(joinResponse());
  queuePollResponses(opts);

  await act(async () => {
    fireEvent.click(screen.getByText('Join Session'));
  });

  // Wait for state to settle
  await waitFor(() => {
    expect(mockFetch).toHaveBeenCalled();
  });
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.useFakeTimers();
  mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  global.fetch = mockFetch;
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CollaborationPage', () => {
  it('renders heading "Workflow Collaboration"', () => {
    renderPage();
    expect(screen.getByText('Workflow Collaboration')).toBeTruthy();
  });

  it('shows flow selector dropdown', () => {
    renderPage();
    const select = screen.getByLabelText('Select Workflow');
    expect(select).toBeTruthy();
    expect(select.tagName.toLowerCase()).toBe('select');
  });

  it('shows "Join Session" button initially', () => {
    renderPage();
    expect(screen.getByText('Join Session')).toBeTruthy();
  });

  it('calls join API when Join Session clicked', async () => {
    renderPage();
    await joinSession();

    const joinCall = mockFetch.mock.calls.find(
      (c: [string, RequestInit?]) => typeof c[0] === 'string' && c[0].includes('/collaboration/join'),
    );
    expect(joinCall).toBeTruthy();
    expect(joinCall![1]?.method).toBe('POST');
  });

  it('shows presence avatars after joining', async () => {
    renderPage();
    await joinSession();

    await waitFor(() => {
      expect(screen.getByTestId('avatar-u1')).toBeTruthy();
    });
  });

  it('shows collaborator username in presence list', async () => {
    renderPage();
    await joinSession();

    // "alice" appears in presence section as <span>alice</span>
    // and in activity as <strong>alice</strong>
    const matches = screen.getAllByText('alice');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('shows activity feed after joining', async () => {
    renderPage();
    await joinSession();

    await waitFor(() => {
      expect(screen.getByText('Activity Feed')).toBeTruthy();
    });
  });

  it('shows activity event text', async () => {
    renderPage();
    await joinSession();

    await waitFor(() => {
      expect(screen.getByText(/joined/)).toBeTruthy();
    });
  });

  it('shows "Leave Session" button after joining', async () => {
    renderPage();
    await joinSession();

    await waitFor(() => {
      expect(screen.getByText('Leave Session')).toBeTruthy();
    });
  });

  it('calls leave API when Leave Session clicked', async () => {
    renderPage();
    await joinSession();

    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    await act(async () => {
      fireEvent.click(screen.getByText('Leave Session'));
    });

    const leaveCall = mockFetch.mock.calls.find(
      (c: [string, RequestInit?]) => typeof c[0] === 'string' && c[0].includes('/collaboration/leave'),
    );
    expect(leaveCall).toBeTruthy();
    expect(leaveCall![1]?.method).toBe('DELETE');
  });

  it('shows "No active collaborators" when presence list is empty', async () => {
    renderPage();
    // Before joining, no collaborators
    expect(screen.getByText('No active collaborators')).toBeTruthy();
  });

  it('shows "No activity yet" when activity list is empty', async () => {
    renderPage();
    // Before joining, no activity
    expect(screen.getByText('No activity yet')).toBeTruthy();
  });
});
