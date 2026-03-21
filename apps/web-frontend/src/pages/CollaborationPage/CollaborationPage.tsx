/**
 * CollaborationPage -- Multi-user workflow collaboration.
 *
 * Shows:
 *   - Flow selector dropdown (demo workflow IDs)
 *   - Join / Leave session controls
 *   - Presence section with avatar circles
 *   - Node lock panel
 *   - Activity feed with relative timestamps
 *   - Auto-heartbeat every 15s and polling every 5s when joined
 *
 * Route: /collaboration (ProtectedRoute)
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Collaborator {
  user_id: string;
  username: string;
  color: string;
  last_seen: number;
}

interface NodeLock {
  user_id: string;
  username: string;
  locked_at: number;
}

interface ActivityEvent {
  user_id: string;
  username: string;
  action: string;
  detail: string;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEMO_FLOWS = [
  { id: 'flow-001', name: 'Customer Support Pipeline' },
  { id: 'flow-002', name: 'Data Processing Workflow' },
  { id: 'flow-003', name: 'Content Generation Chain' },
];

const HEARTBEAT_INTERVAL_MS = 15_000;
const POLL_INTERVAL_MS = 5_000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem('access_token') || '';
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function relativeTime(epochSeconds: number): string {
  const now = Date.now() / 1000;
  const delta = Math.max(0, Math.floor(now - epochSeconds));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

function userInitials(username: string): string {
  return username
    .split(/[\s_-]+/)
    .map((w) => w.charAt(0).toUpperCase())
    .slice(0, 2)
    .join('');
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CollaborationPage: React.FC = () => {
  const [selectedFlowId, setSelectedFlowId] = useState(DEMO_FLOWS[0].id);
  const [joined, setJoined] = useState(false);
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [locks, setLocks] = useState<Record<string, NodeLock>>({});
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // -----------------------------------------------------------------------
  // API helpers
  // -----------------------------------------------------------------------

  const fetchPresence = useCallback(async (flowId: string) => {
    const res = await fetch(`/api/v1/flows/${flowId}/collaboration/presence`, {
      headers: getAuthHeaders(),
    });
    if (res.ok) {
      const data = await res.json();
      setCollaborators(data.collaborators ?? []);
    }
  }, []);

  const fetchLocks = useCallback(async (flowId: string) => {
    const res = await fetch(`/api/v1/flows/${flowId}/collaboration/locks`, {
      headers: getAuthHeaders(),
    });
    if (res.ok) {
      const data = await res.json();
      setLocks(data.locks ?? {});
    }
  }, []);

  const fetchActivity = useCallback(async (flowId: string) => {
    const res = await fetch(`/api/v1/flows/${flowId}/collaboration/activity`, {
      headers: getAuthHeaders(),
    });
    if (res.ok) {
      const data = await res.json();
      setActivity(data.activity ?? []);
    }
  }, []);

  const sendHeartbeat = useCallback(async (flowId: string) => {
    await fetch(`/api/v1/flows/${flowId}/collaboration/heartbeat`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
  }, []);

  // -----------------------------------------------------------------------
  // Join / Leave
  // -----------------------------------------------------------------------

  const handleJoin = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch(`/api/v1/flows/${selectedFlowId}/collaboration/join`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        setError('Failed to join session');
        return;
      }
      const data = await res.json();
      setCollaborators(data.collaborators ?? []);
      setJoined(true);

      // Kick off initial polls
      await fetchPresence(selectedFlowId);
      await fetchLocks(selectedFlowId);
      await fetchActivity(selectedFlowId);
    } catch {
      setError('Network error joining session');
    }
  }, [selectedFlowId, fetchPresence, fetchLocks, fetchActivity]);

  const handleLeave = useCallback(async () => {
    setError(null);
    try {
      await fetch(`/api/v1/flows/${selectedFlowId}/collaboration/leave`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
    } catch {
      // Best-effort leave -- proceed with cleanup regardless
    }
    setJoined(false);
    setCollaborators([]);
    setLocks({});
    setActivity([]);
  }, [selectedFlowId]);

  // -----------------------------------------------------------------------
  // Heartbeat + Polling
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!joined) return;

    heartbeatRef.current = setInterval(() => {
      sendHeartbeat(selectedFlowId);
    }, HEARTBEAT_INTERVAL_MS);

    pollRef.current = setInterval(() => {
      fetchPresence(selectedFlowId);
      fetchLocks(selectedFlowId);
      fetchActivity(selectedFlowId);
    }, POLL_INTERVAL_MS);

    return () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [joined, selectedFlowId, sendHeartbeat, fetchPresence, fetchLocks, fetchActivity]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  const lockEntries = Object.entries(locks);

  return (
    <MainLayout title="Workflow Collaboration">
      <div style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
        <h2>Workflow Collaboration</h2>

        {error && (
          <div style={{ color: '#ef4444', marginBottom: 16 }} role="alert">
            {error}
          </div>
        )}

        {/* Flow Selector */}
        <div style={{ marginBottom: 24 }}>
          <label htmlFor="flow-selector" style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
            Select Workflow
          </label>
          <select
            id="flow-selector"
            value={selectedFlowId}
            onChange={(e) => setSelectedFlowId(e.target.value)}
            disabled={joined}
            style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #475569', background: '#1e293b', color: '#e2e8f0', width: '100%' }}
          >
            {DEMO_FLOWS.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} ({f.id})
              </option>
            ))}
          </select>
        </div>

        {/* Join / Leave */}
        <div style={{ marginBottom: 32 }}>
          {!joined ? (
            <button
              onClick={handleJoin}
              style={{ padding: '10px 24px', borderRadius: 6, background: '#6366f1', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600 }}
            >
              Join Session
            </button>
          ) : (
            <button
              onClick={handleLeave}
              style={{ padding: '10px 24px', borderRadius: 6, background: '#ef4444', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600 }}
            >
              Leave Session
            </button>
          )}
        </div>

        {/* Presence */}
        <section style={{ marginBottom: 32 }}>
          <h3 style={{ marginBottom: 12 }}>Active Collaborators</h3>
          {collaborators.length === 0 ? (
            <p style={{ color: '#94a3b8' }}>No active collaborators</p>
          ) : (
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              {collaborators.map((c) => (
                <div key={c.user_id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: '50%',
                      background: c.color,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#fff',
                      fontWeight: 700,
                      fontSize: 14,
                    }}
                    title={c.username}
                    data-testid={`avatar-${c.user_id}`}
                  >
                    {userInitials(c.username)}
                  </div>
                  <span>{c.username}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Node Locks */}
        <section style={{ marginBottom: 32 }}>
          <h3 style={{ marginBottom: 12 }}>Node Locks</h3>
          {lockEntries.length === 0 ? (
            <p style={{ color: '#94a3b8' }}>No locked nodes</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {lockEntries.map(([nodeId, lock]) => (
                <li key={nodeId} style={{ padding: '6px 0', borderBottom: '1px solid #334155' }}>
                  <strong>{nodeId}</strong> -- locked by {lock.username} ({relativeTime(lock.locked_at)})
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Activity Feed */}
        <section>
          <h3 style={{ marginBottom: 12 }}>Activity Feed</h3>
          {activity.length === 0 ? (
            <p style={{ color: '#94a3b8' }}>No activity yet</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {activity.map((evt, i) => (
                <li key={`${evt.user_id}-${evt.timestamp}-${i}`} style={{ padding: '6px 0', borderBottom: '1px solid #334155' }}>
                  <strong>{evt.username}</strong> {evt.action}
                  {evt.detail ? ` -- ${evt.detail}` : ''} ({relativeTime(evt.timestamp)})
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default CollaborationPage;
