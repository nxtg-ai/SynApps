/**
 * WorkflowActivityPage — Workflow Comments & Activity Feed (N-85).
 *
 * Wraps:
 *   GET /api/v1/workflows/{flow_id}/comments  → all comments across nodes
 *   GET /api/v1/workflows/{flow_id}/activity  → edit/run/comment event feed
 *
 * Route: /workflow-activity (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Comment {
  id: string;
  node_id: string;
  author: string;
  content: string;
  parent_id?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

interface CommentsResponse {
  flow_id: string;
  count: number;
  comments: Comment[];
}

interface ActivityEvent {
  id?: string;
  actor: string;
  action: string;
  detail?: string;
  timestamp?: string;
  [key: string]: unknown;
}

interface ActivityResponse {
  flow_id: string;
  count: number;
  events: ActivityEvent[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ||
    'http://localhost:8000'
  );
}

function authHeaders(): Record<string, string> {
  const token =
    typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function actionColor(action: string): string {
  if (action.includes('run') || action.includes('exec')) return 'bg-emerald-900/40 text-emerald-300';
  if (action.includes('comment')) return 'bg-indigo-900/40 text-indigo-300';
  if (action.includes('edit') || action.includes('update')) return 'bg-yellow-900/40 text-yellow-300';
  if (action.includes('delete') || action.includes('revoke')) return 'bg-red-900/40 text-red-300';
  return 'bg-slate-700/40 text-slate-400';
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const WorkflowActivityPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);

  const [loadingComments, setLoadingComments] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [commentsData, setCommentsData] = useState<CommentsResponse | null>(null);

  const [loadingActivity, setLoadingActivity] = useState(false);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [activityData, setActivityData] = useState<ActivityResponse | null>(null);

  const loadAll = useCallback(async (fid: string) => {
    setLoadingComments(true);
    setLoadingActivity(true);
    setCommentsError(null);
    setActivityError(null);
    setCommentsData(null);
    setActivityData(null);

    const [commResp, actResp] = await Promise.allSettled([
      fetch(`${getBaseUrl()}/workflows/${fid}/comments`, { headers: authHeaders() }),
      fetch(`${getBaseUrl()}/workflows/${fid}/activity`, { headers: authHeaders() }),
    ]);

    if (commResp.status === 'fulfilled') {
      const r = commResp.value;
      if (r.ok) setCommentsData(await r.json());
      else setCommentsError(`Failed to load comments (${r.status})`);
    } else {
      setCommentsError('Network error loading comments');
    }
    setLoadingComments(false);

    if (actResp.status === 'fulfilled') {
      const r = actResp.value;
      if (r.ok) setActivityData(await r.json());
      else setActivityError(`Failed to load activity (${r.status})`);
    } else {
      setActivityError('Network error loading activity');
    }
    setLoadingActivity(false);
  }, []);

  const handleLoad = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim()) return;
      setActiveFlowId(flowId.trim());
      loadAll(flowId.trim());
    },
    [flowId, loadAll],
  );

  const comments = commentsData?.comments ?? [];
  const events = activityData?.events ?? [];

  return (
    <MainLayout title="Workflow Activity">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Workflow Activity
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Comments and activity feed for a workflow.
        </p>
      </div>

      {/* Flow selector */}
      <form onSubmit={handleLoad} className="mb-6 flex gap-2" data-testid="flow-selector-form">
        <input
          type="text"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          placeholder="Workflow / Flow ID"
          className="flex-1 rounded border border-slate-600 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          data-testid="flow-id-input"
        />
        <button
          type="submit"
          disabled={!flowId.trim() || loadingComments || loadingActivity}
          className="rounded bg-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="load-btn"
        >
          Load
        </button>
      </form>

      {!activeFlowId && (
        <p className="text-xs text-slate-500" data-testid="no-flow-state">
          Enter a workflow ID to view its comments and activity.
        </p>
      )}

      {activeFlowId && (
        <div className="grid gap-6 lg:grid-cols-2" data-testid="panels-container">
          {/* Comments panel */}
          <section
            className="rounded border border-slate-700 bg-slate-800/40 p-5"
            data-testid="comments-panel"
          >
            <p className="mb-4 text-sm font-semibold text-slate-300">
              Comments
              {commentsData && (
                <span className="ml-2 text-xs text-slate-500">({commentsData.count})</span>
              )}
            </p>

            {commentsError && (
              <p className="text-sm text-red-400" data-testid="comments-error">{commentsError}</p>
            )}

            {loadingComments && !commentsData && (
              <p className="text-xs text-slate-500" data-testid="comments-loading">Loading…</p>
            )}

            {!loadingComments && commentsData && comments.length === 0 && (
              <p className="text-xs text-slate-500" data-testid="no-comments">
                No comments yet.
              </p>
            )}

            {comments.length > 0 && (
              <div className="space-y-3" data-testid="comments-list">
                {comments.map((c) => (
                  <div
                    key={c.id}
                    className="rounded border border-slate-700/60 bg-slate-900/40 p-3"
                    data-testid="comment-row"
                  >
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="text-slate-400">{c.author}</span>
                      <span className="font-mono text-slate-500">
                        node: {c.node_id}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300">{c.content}</p>
                    {c.created_at && (
                      <p className="mt-1 text-xs text-slate-600">{c.created_at}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Activity panel */}
          <section
            className="rounded border border-slate-700 bg-slate-800/40 p-5"
            data-testid="activity-panel"
          >
            <p className="mb-4 text-sm font-semibold text-slate-300">
              Activity Feed
              {activityData && (
                <span className="ml-2 text-xs text-slate-500">({activityData.count})</span>
              )}
            </p>

            {activityError && (
              <p className="text-sm text-red-400" data-testid="activity-error">{activityError}</p>
            )}

            {loadingActivity && !activityData && (
              <p className="text-xs text-slate-500" data-testid="activity-loading">Loading…</p>
            )}

            {!loadingActivity && activityData && events.length === 0 && (
              <p className="text-xs text-slate-500" data-testid="no-activity">
                No activity recorded.
              </p>
            )}

            {events.length > 0 && (
              <div className="space-y-2" data-testid="activity-list">
                {events.map((ev, i) => (
                  <div
                    key={ev.id ?? i}
                    className="flex items-start gap-2"
                    data-testid="activity-row"
                  >
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${actionColor(ev.action)}`}
                      data-testid="action-badge"
                    >
                      {ev.action}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs text-slate-400">
                        {ev.actor}
                        {ev.detail && (
                          <span className="ml-1 text-slate-500">— {ev.detail}</span>
                        )}
                      </p>
                      {ev.timestamp && (
                        <p className="text-xs text-slate-600">{ev.timestamp}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </MainLayout>
  );
};

export default WorkflowActivityPage;
