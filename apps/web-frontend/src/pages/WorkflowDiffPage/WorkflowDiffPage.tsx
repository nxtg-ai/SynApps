/**
 * WorkflowDiffPage — compare two saved versions of a workflow side-by-side.
 *
 * Route: /workflows/:id/diff
 *
 * Layout:
 *   - Header: back link + flow name
 *   - Controls: version A selector, version B selector (with "Current" option), Compare button
 *   - Summary badges: counts per change type
 *   - Nodes section: added (green), removed (red), changed (yellow, expandable field diff)
 *   - Edges section: added (green), removed (red)
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiService } from '../../services/ApiService';
import { FlowDiffResult, FlowVersion, FlowVersionDetail } from '../../types';

// ── Local helpers ─────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function getNodeLabel(snapshot: FlowVersionDetail | null, nodeId: string): string {
  if (!snapshot) return nodeId;
  const node = snapshot.snapshot.nodes.find((n: any) => n.id === nodeId);
  return node?.data?.label ?? node?.data?.name ?? nodeId;
}

function getNodeType(snapshot: FlowVersionDetail | null, nodeId: string): string {
  if (!snapshot) return '';
  const node = snapshot.snapshot.nodes.find((n: any) => n.id === nodeId);
  return node?.type ?? '';
}

/**
 * Compute field-level diff between two `data` objects.
 * Returns an array of { field, before, after } for every key whose value differs.
 */
function diffNodeData(
  dataA: Record<string, any> | undefined,
  dataB: Record<string, any> | undefined
): Array<{ field: string; before: string; after: string }> {
  const a = dataA ?? {};
  const b = dataB ?? {};
  const allKeys = Array.from(new Set([...Object.keys(a), ...Object.keys(b)]));
  return allKeys
    .filter((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k]))
    .map((k) => ({
      field: k,
      before: a[k] === undefined ? '(absent)' : JSON.stringify(a[k]),
      after: b[k] === undefined ? '(absent)' : JSON.stringify(b[k]),
    }));
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface SummaryBadgeProps {
  count: number;
  label: string;
  colorClass: string;
}

function SummaryBadge({ count, label, colorClass }: SummaryBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm font-medium ${colorClass}`}
    >
      <span className="font-bold">{count}</span>
      <span>{label}</span>
    </span>
  );
}

interface NodeRowProps {
  nodeId: string;
  variant: 'added' | 'removed' | 'changed';
  snapshotA: FlowVersionDetail | null;
  snapshotB: FlowVersionDetail | null;
}

function NodeRow({ nodeId, variant, snapshotA, snapshotB }: NodeRowProps) {
  const [expanded, setExpanded] = useState(false);

  const variantStyles: Record<string, string> = {
    added: 'text-green-400 bg-green-900/20 border-green-700',
    removed: 'text-red-400 bg-red-900/20 border-red-700',
    changed: 'text-yellow-400 bg-yellow-900/20 border-yellow-700',
  };

  const icons: Record<string, string> = {
    added: '✚',
    removed: '✕',
    changed: '≈',
  };

  // For "added" nodes use snapshot B; for "removed" use A; for "changed" prefer B for current state
  const primarySnapshot = variant === 'removed' ? snapshotA : snapshotB;
  const label = getNodeLabel(primarySnapshot, nodeId);
  const type = getNodeType(primarySnapshot, nodeId);

  const fieldDiffs =
    variant === 'changed'
      ? diffNodeData(
          snapshotA?.snapshot.nodes.find((n: any) => n.id === nodeId)?.data,
          snapshotB?.snapshot.nodes.find((n: any) => n.id === nodeId)?.data
        )
      : [];

  return (
    <div>
      <div
        className={`flex items-center justify-between rounded border px-4 py-2 ${variantStyles[variant]} ${variant === 'changed' ? 'cursor-pointer select-none' : ''}`}
        onClick={variant === 'changed' ? () => setExpanded((v) => !v) : undefined}
        data-testid={`node-row-${variant}`}
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-base" aria-label={variant}>
            {icons[variant]}
          </span>
          <span className="font-mono text-sm">{nodeId}</span>
          {type && (
            <span className="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-300">{type}</span>
          )}
          {label !== nodeId && (
            <span className="text-sm text-gray-400">&ldquo;{label}&rdquo;</span>
          )}
        </div>
        {variant === 'changed' && (
          <span className="text-xs text-gray-500">{expanded ? '▲ collapse' : '▼ expand'}</span>
        )}
      </div>

      {variant === 'changed' && expanded && (
        <div className="ml-8 mt-1 space-y-1 rounded border border-yellow-800 bg-yellow-950/30 px-4 py-3">
          {fieldDiffs.length === 0 ? (
            <p className="text-xs text-gray-500">No data field differences detected.</p>
          ) : (
            fieldDiffs.map(({ field, before, after }) => (
              <div key={field} className="text-xs text-yellow-300">
                <span className="font-semibold">{field}:</span>{' '}
                <span className="text-red-400">{before}</span>
                <span className="mx-1 text-gray-500">→</span>
                <span className="text-green-400">{after}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

interface EdgeRowProps {
  edgeKey: string;
  variant: 'added' | 'removed';
}

function EdgeRow({ edgeKey, variant }: EdgeRowProps) {
  const variantStyles: Record<string, string> = {
    added: 'text-green-400 bg-green-900/20 border-green-700',
    removed: 'text-red-400 bg-red-900/20 border-red-700',
  };

  const icons: Record<string, string> = {
    added: '✚',
    removed: '✕',
  };

  return (
    <div
      className={`flex items-center gap-3 rounded border px-4 py-2 ${variantStyles[variant]}`}
      data-testid={`edge-row-${variant}`}
    >
      <span className="font-mono text-base" aria-label={variant}>
        {icons[variant]}
      </span>
      <span className="font-mono text-sm">{edgeKey}</span>
    </div>
  );
}

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div className="flex items-center justify-center" data-testid="spinner">
      <svg
        className="h-8 w-8 animate-spin text-blue-400"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-label="Loading"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
        />
      </svg>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const WorkflowDiffPage: React.FC = () => {
  const { id: flowId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // Versions list state
  const [versions, setVersions] = useState<FlowVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(true);
  const [versionsError, setVersionsError] = useState<string | null>(null);

  // Selector state
  const [versionA, setVersionA] = useState<string>('');
  const [versionB, setVersionB] = useState<string>('current');

  // Diff result state
  const [diff, setDiff] = useState<FlowDiffResult | null>(null);
  const [snapshotA, setSnapshotA] = useState<FlowVersionDetail | null>(null);
  const [snapshotB, setSnapshotB] = useState<FlowVersionDetail | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);

  // Flow name (extracted from first available snapshot)
  const [flowName, setFlowName] = useState<string>('');

  // ── Load versions on mount ─────────────────────────────────────────────────
  useEffect(() => {
    if (!flowId) return;

    setVersionsLoading(true);
    setVersionsError(null);

    apiService
      .getFlowVersions(flowId)
      .then(({ items }) => {
        setVersions(items);
        if (items.length > 0) {
          // Default: oldest version as A, current as B
          const oldest = items[items.length - 1];
          setVersionA(oldest.version_id);
          setVersionB('current');
        }
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load versions';
        setVersionsError(msg);
      })
      .finally(() => setVersionsLoading(false));
  }, [flowId]);

  // ── Compare handler ────────────────────────────────────────────────────────
  const handleCompare = useCallback(async () => {
    if (!flowId || !versionA) return;

    setDiffLoading(true);
    setDiffError(null);
    setDiff(null);
    setSnapshotA(null);
    setSnapshotB(null);

    try {
      // Fetch diff and snapshot A in parallel; snapshot B only if it's not "current"
      const [diffResult, snapA] = await Promise.all([
        apiService.diffFlowVersions(flowId, versionA, versionB),
        apiService.getFlowVersion(flowId, versionA),
      ]);

      let snapB: FlowVersionDetail | null = null;
      if (versionB !== 'current') {
        snapB = await apiService.getFlowVersion(flowId, versionB);
      }

      setDiff(diffResult);
      setSnapshotA(snapA);
      setSnapshotB(snapB);

      // Derive flow name from snapshot A
      if (snapA.snapshot.name) {
        setFlowName(snapA.snapshot.name);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to compute diff';
      setDiffError(msg);
    } finally {
      setDiffLoading(false);
    }
  }, [flowId, versionA, versionB]);

  // ── Derived values ─────────────────────────────────────────────────────────
  const isIdentical =
    diff !== null &&
    diff.summary.nodes_added === 0 &&
    diff.summary.nodes_removed === 0 &&
    diff.summary.nodes_changed === 0 &&
    diff.summary.edges_added === 0 &&
    diff.summary.edges_removed === 0;

  const hasEdgeChanges =
    diff && (diff.edges_added.length > 0 || diff.edges_removed.length > 0);

  const hasNodeChanges =
    diff &&
    (diff.nodes_added.length > 0 ||
      diff.nodes_removed.length > 0 ||
      diff.nodes_changed.length > 0);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-900 text-gray-100">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-gray-700 bg-gray-900/90 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-4">
          <button
            onClick={() => navigate(flowId ? `/editor/${flowId}` : '/dashboard')}
            className="flex items-center gap-1 text-sm text-gray-400 transition-colors hover:text-gray-100"
            aria-label="Back to editor"
          >
            <span>←</span>
            <span>Back to Editor</span>
          </button>
          <span className="text-gray-600">|</span>
          <h1 className="text-sm font-semibold text-gray-100">
            Workflow Diff{flowName ? ` — ${flowName}` : ''}
          </h1>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
        {/* Loading state for version list */}
        {versionsLoading && (
          <div className="flex flex-col items-center justify-center gap-3 py-20">
            <Spinner />
            <p className="text-sm text-gray-400">Loading version history…</p>
          </div>
        )}

        {/* Error loading versions */}
        {!versionsLoading && versionsError && (
          <div className="rounded border border-red-700 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            Error: {versionsError}
          </div>
        )}

        {/* Empty version history */}
        {!versionsLoading && !versionsError && versions.length === 0 && (
          <div className="rounded border border-gray-700 bg-gray-800 px-6 py-10 text-center">
            <p className="text-gray-300">No version history yet.</p>
            <p className="mt-1 text-sm text-gray-500">
              Save the workflow to create a snapshot.
            </p>
          </div>
        )}

        {/* Version selectors + compare button */}
        {!versionsLoading && !versionsError && versions.length > 0 && (
          <section className="rounded border border-gray-700 bg-gray-800 p-5">
            <div className="flex flex-wrap items-end gap-4">
              <div className="flex flex-col gap-1">
                <label htmlFor="version-a" className="text-xs font-medium text-gray-400">
                  Version A (base)
                </label>
                <select
                  id="version-a"
                  value={versionA}
                  onChange={(e) => setVersionA(e.target.value)}
                  className="rounded border border-gray-600 bg-gray-700 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none"
                  data-testid="version-a-select"
                >
                  {versions.map((v) => (
                    <option key={v.version_id} value={v.version_id}>
                      v{v.version} — {formatDate(v.snapshotted_at)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label htmlFor="version-b" className="text-xs font-medium text-gray-400">
                  Version B (compare to)
                </label>
                <select
                  id="version-b"
                  value={versionB}
                  onChange={(e) => setVersionB(e.target.value)}
                  className="rounded border border-gray-600 bg-gray-700 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none"
                  data-testid="version-b-select"
                >
                  <option value="current">Current (live)</option>
                  {versions.map((v) => (
                    <option key={v.version_id} value={v.version_id}>
                      v{v.version} — {formatDate(v.snapshotted_at)}
                    </option>
                  ))}
                </select>
              </div>

              <button
                onClick={handleCompare}
                disabled={diffLoading || !versionA}
                className="rounded bg-blue-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="compare-button"
              >
                {diffLoading ? 'Comparing…' : 'Compare'}
              </button>
            </div>
          </section>
        )}

        {/* Diff loading spinner */}
        {diffLoading && (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        )}

        {/* Diff error */}
        {!diffLoading && diffError && (
          <div className="rounded border border-red-700 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            Error: {diffError}
          </div>
        )}

        {/* Results */}
        {!diffLoading && diff && (
          <>
            {/* Identical banner */}
            {isIdentical && (
              <div
                className="flex items-center gap-2 rounded border border-green-700 bg-green-900/20 px-5 py-4 text-green-400"
                data-testid="identical-banner"
              >
                <span className="text-lg">✓</span>
                <span className="font-medium">Workflows are identical</span>
              </div>
            )}

            {/* Summary badges */}
            {!isIdentical && (
              <section
                className="flex flex-wrap gap-2 rounded border border-gray-700 bg-gray-800 px-5 py-4"
                data-testid="summary-section"
              >
                {diff.summary.nodes_added > 0 && (
                  <SummaryBadge
                    count={diff.summary.nodes_added}
                    label={diff.summary.nodes_added === 1 ? 'node added' : 'nodes added'}
                    colorClass="bg-green-900/40 text-green-400"
                  />
                )}
                {diff.summary.nodes_removed > 0 && (
                  <SummaryBadge
                    count={diff.summary.nodes_removed}
                    label={diff.summary.nodes_removed === 1 ? 'node removed' : 'nodes removed'}
                    colorClass="bg-red-900/40 text-red-400"
                  />
                )}
                {diff.summary.nodes_changed > 0 && (
                  <SummaryBadge
                    count={diff.summary.nodes_changed}
                    label={diff.summary.nodes_changed === 1 ? 'node changed' : 'nodes changed'}
                    colorClass="bg-yellow-900/40 text-yellow-400"
                  />
                )}
                {diff.summary.edges_added > 0 && (
                  <SummaryBadge
                    count={diff.summary.edges_added}
                    label={diff.summary.edges_added === 1 ? 'edge added' : 'edges added'}
                    colorClass="bg-green-900/40 text-green-400"
                  />
                )}
                {diff.summary.edges_removed > 0 && (
                  <SummaryBadge
                    count={diff.summary.edges_removed}
                    label={diff.summary.edges_removed === 1 ? 'edge removed' : 'edges removed'}
                    colorClass="bg-red-900/40 text-red-400"
                  />
                )}
              </section>
            )}

            {/* Nodes section */}
            {hasNodeChanges && (
              <section className="space-y-3">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500">
                  Nodes
                </h2>
                <div className="space-y-2">
                  {diff.nodes_added.map((nodeId) => (
                    <NodeRow
                      key={nodeId}
                      nodeId={nodeId}
                      variant="added"
                      snapshotA={snapshotA}
                      snapshotB={snapshotB}
                    />
                  ))}
                  {diff.nodes_removed.map((nodeId) => (
                    <NodeRow
                      key={nodeId}
                      nodeId={nodeId}
                      variant="removed"
                      snapshotA={snapshotA}
                      snapshotB={snapshotB}
                    />
                  ))}
                  {diff.nodes_changed.map((nodeId) => (
                    <NodeRow
                      key={nodeId}
                      nodeId={nodeId}
                      variant="changed"
                      snapshotA={snapshotA}
                      snapshotB={snapshotB}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Edges section */}
            {hasEdgeChanges && (
              <section className="space-y-3">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500">
                  Edges
                </h2>
                <div className="space-y-2">
                  {diff.edges_added.map((edgeKey) => (
                    <EdgeRow key={edgeKey} edgeKey={edgeKey} variant="added" />
                  ))}
                  {diff.edges_removed.map((edgeKey) => (
                    <EdgeRow key={edgeKey} edgeKey={edgeKey} variant="removed" />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
};

export default WorkflowDiffPage;
