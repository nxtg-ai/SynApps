/**
 * NodeCommentsPage — Per-node threaded comment management (N-104).
 *
 * Covers:
 *   POST /workflows/{flow_id}/nodes/{node_id}/comments  → add comment
 *   GET  /workflows/{flow_id}/nodes/{node_id}/comments  → list comments
 *
 * Route: /node-comments (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NodeComment {
  comment_id: string;
  flow_id: string;
  node_id: string;
  author: string;
  content: string;
  parent_id?: string | null;
  created_at?: string | number;
  [key: string]: unknown;
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const NodeCommentsPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [nodeId, setNodeId] = useState('');

  // List state
  const [loadingList, setLoadingList] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [comments, setComments] = useState<NodeComment[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);

  // Create form
  const [content, setContent] = useState('');
  const [parentId, setParentId] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<NodeComment | null>(null);

  // ---------------------------------------------------------------------------
  // Load
  // ---------------------------------------------------------------------------

  const handleLoadComments = useCallback(async () => {
    if (!flowId.trim() || !nodeId.trim()) return;
    setLoadingList(true);
    setListError(null);
    setComments(null);
    setTotal(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/workflows/${encodeURIComponent(flowId.trim())}/nodes/${encodeURIComponent(nodeId.trim())}/comments`,
        { headers: authHeaders() },
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setListError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      const data = await resp.json();
      const items: NodeComment[] = Array.isArray(data)
        ? data
        : Array.isArray(data.comments)
          ? data.comments
          : [];
      setComments(items);
      setTotal(typeof data.count === 'number' ? data.count : items.length);
    } catch {
      setListError('Network error loading comments');
    } finally {
      setLoadingList(false);
    }
  }, [flowId, nodeId]);

  // ---------------------------------------------------------------------------
  // Create
  // ---------------------------------------------------------------------------

  const handleCreate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!flowId.trim() || !nodeId.trim() || !content.trim()) return;
      setCreating(true);
      setCreateError(null);
      setCreateSuccess(null);
      try {
        const body: Record<string, unknown> = { content: content.trim() };
        if (parentId.trim()) body.parent_id = parentId.trim();

        const resp = await fetch(
          `${getBaseUrl()}/workflows/${encodeURIComponent(flowId.trim())}/nodes/${encodeURIComponent(nodeId.trim())}/comments`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setCreateError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const created: NodeComment = await resp.json();
        setCreateSuccess(created);
        setContent('');
        setParentId('');
        // Prepend to list if already loaded
        setComments((prev) => (prev !== null ? [created, ...prev] : null));
      } catch {
        setCreateError('Network error creating comment');
      } finally {
        setCreating(false);
      }
    },
    [flowId, nodeId, content, parentId],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Node Comments">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Node Comments
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          View and add threaded comments on specific workflow nodes.
        </p>
      </div>

      {/* Flow + Node selectors */}
      <div className="mb-6 flex flex-wrap gap-3">
        <input
          type="text"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          placeholder="Flow ID"
          className="w-64 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
          data-testid="flow-id-input"
        />
        <input
          type="text"
          value={nodeId}
          onChange={(e) => setNodeId(e.target.value)}
          placeholder="Node ID"
          className="w-48 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
          data-testid="node-id-input"
        />
        <button
          onClick={handleLoadComments}
          disabled={loadingList || !flowId.trim() || !nodeId.trim()}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="load-btn"
        >
          {loadingList ? 'Loading…' : 'Load Comments'}
        </button>
      </div>

      {/* Create form */}
      <section
        className="mb-6 rounded border border-slate-700 bg-slate-800/30 p-4"
        data-testid="create-section"
      >
        <h2 className="mb-3 text-sm font-semibold text-slate-300">Add Comment</h2>
        <form onSubmit={handleCreate} className="space-y-3" data-testid="create-form">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Write a comment…"
            rows={3}
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
            data-testid="content-input"
          />
          <input
            type="text"
            value={parentId}
            onChange={(e) => setParentId(e.target.value)}
            placeholder="Parent comment ID (optional thread reply)"
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
            data-testid="parent-id-input"
          />
          <button
            type="submit"
            disabled={creating || !flowId.trim() || !nodeId.trim() || !content.trim()}
            className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
            data-testid="create-btn"
          >
            {creating ? 'Posting…' : 'Post Comment'}
          </button>
        </form>
        {createError && (
          <p className="mt-2 text-sm text-red-400" data-testid="create-error">
            {createError}
          </p>
        )}
        {createSuccess && (
          <div
            className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
            data-testid="create-success"
          >
            <p className="font-semibold text-emerald-400">Comment posted!</p>
            <p className="mt-1 font-mono text-slate-300" data-testid="new-comment-id">
              {createSuccess.comment_id}
            </p>
          </div>
        )}
      </section>

      {/* Comment list */}
      {listError && (
        <p className="mb-4 text-sm text-red-400" data-testid="list-error">
          {listError}
        </p>
      )}
      {loadingList && (
        <p className="text-xs text-slate-500" data-testid="list-loading">
          Loading…
        </p>
      )}
      {comments !== null && comments.length === 0 && (
        <p className="text-xs text-slate-500" data-testid="no-comments">
          No comments on this node.
        </p>
      )}
      {comments !== null && comments.length > 0 && (
        <div data-testid="comments-list">
          <p className="mb-3 text-xs text-slate-500">
            {total} comment{total !== 1 ? 's' : ''}
          </p>
          {comments.map((c) => (
            <div
              key={c.comment_id}
              className={`mb-3 rounded border bg-slate-900/40 p-3 text-xs ${c.parent_id ? 'ml-6 border-indigo-700/30' : 'border-slate-700/50'}`}
              data-testid="comment-item"
            >
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-slate-300" data-testid="comment-author">
                  {c.author}
                </span>
                <span className="font-mono text-slate-500">{c.comment_id}</span>
                {c.parent_id && (
                  <span className="text-indigo-400">
                    ↳ reply to {c.parent_id}
                  </span>
                )}
              </div>
              <p className="text-slate-300" data-testid="comment-content">
                {c.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </MainLayout>
  );
};

export default NodeCommentsPage;
