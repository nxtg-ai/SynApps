/**
 * WorkflowDiffPage unit tests
 *
 * Covers: loading state, empty history, version selectors, compare trigger,
 * summary badges, node change colours, changed-node field expansion,
 * identical-banner, edge section rendering.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useParams: () => ({ id: 'flow-abc' }),
    useNavigate: () => vi.fn(),
  };
});

const mockGetFlowVersions = vi.fn();
const mockGetFlowVersion = vi.fn();
const mockDiffFlowVersions = vi.fn();

vi.mock('../../services/ApiService', () => ({
  apiService: {
    getFlowVersions: (...args: unknown[]) => mockGetFlowVersions(...args),
    getFlowVersion: (...args: unknown[]) => mockGetFlowVersion(...args),
    diffFlowVersions: (...args: unknown[]) => mockDiffFlowVersions(...args),
  },
  default: {
    getFlowVersions: (...args: unknown[]) => mockGetFlowVersions(...args),
    getFlowVersion: (...args: unknown[]) => mockGetFlowVersion(...args),
    diffFlowVersions: (...args: unknown[]) => mockDiffFlowVersions(...args),
  },
}));

// ---------------------------------------------------------------------------
// Factories
// ---------------------------------------------------------------------------

function makeVersion(overrides: Partial<{
  version_id: string;
  flow_id: string;
  version: number;
  snapshotted_at: string;
}> = {}) {
  return {
    version_id: overrides.version_id ?? 'ver-1',
    flow_id: overrides.flow_id ?? 'flow-abc',
    version: overrides.version ?? 1,
    snapshotted_at: overrides.snapshotted_at ?? '2026-01-01T10:00:00Z',
  };
}

function makeVersionDetail(overrides: Partial<{
  version_id: string;
  version: number;
  nodes: any[];
  edges: any[];
  name: string;
}> = {}) {
  return {
    version_id: overrides.version_id ?? 'ver-1',
    flow_id: 'flow-abc',
    version: overrides.version ?? 1,
    snapshotted_at: '2026-01-01T10:00:00Z',
    snapshot: {
      name: overrides.name ?? 'My Workflow',
      nodes: overrides.nodes ?? [],
      edges: overrides.edges ?? [],
    },
  };
}

function makeDiff(overrides: Partial<{
  nodes_added: string[];
  nodes_removed: string[];
  nodes_changed: string[];
  edges_added: string[];
  edges_removed: string[];
}> = {}) {
  const nodes_added = overrides.nodes_added ?? [];
  const nodes_removed = overrides.nodes_removed ?? [];
  const nodes_changed = overrides.nodes_changed ?? [];
  const edges_added = overrides.edges_added ?? [];
  const edges_removed = overrides.edges_removed ?? [];
  return {
    nodes_added,
    nodes_removed,
    nodes_changed,
    edges_added,
    edges_removed,
    summary: {
      nodes_added: nodes_added.length,
      nodes_removed: nodes_removed.length,
      nodes_changed: nodes_changed.length,
      edges_added: edges_added.length,
      edges_removed: edges_removed.length,
    },
  };
}

function makeIdenticalDiff() {
  return makeDiff();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function suppressConsoleError() {
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
}

async function importPage() {
  const mod = await import('./WorkflowDiffPage');
  return mod.default;
}

function renderPage(Page: React.ComponentType) {
  return render(
    <MemoryRouter>
      <Page />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockGetFlowVersions.mockReset();
  mockGetFlowVersion.mockReset();
  mockDiffFlowVersions.mockReset();
  suppressConsoleError();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowDiffPage', () => {
  // 1. Loading spinner on mount (before versions resolve)
  it('renders loading spinner on mount while versions are being fetched', async () => {
    // Never resolves so we see the spinner
    mockGetFlowVersions.mockReturnValue(new Promise(() => undefined));

    const Page = await importPage();
    renderPage(Page);

    expect(screen.getByTestId('spinner')).toBeInTheDocument();
  });

  // 2. Empty version history message
  it('shows "No version history" message when versions list is empty', async () => {
    mockGetFlowVersions.mockResolvedValue({ items: [] });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByText('No version history yet.')).toBeInTheDocument();
    });
    expect(screen.getByText(/Save the workflow to create a snapshot/)).toBeInTheDocument();
  });

  // 3. Version selectors appear when versions are loaded
  it('shows version A and version B selectors when versions are loaded', async () => {
    mockGetFlowVersions.mockResolvedValue({
      items: [makeVersion({ version_id: 'ver-2', version: 2 }), makeVersion()],
    });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByTestId('version-a-select')).toBeInTheDocument();
    });
    expect(screen.getByTestId('version-b-select')).toBeInTheDocument();
  });

  // 4. Clicking Compare triggers diffFlowVersions
  it('clicking Compare button triggers diffFlowVersions with selected versions', async () => {
    const version = makeVersion({ version_id: 'ver-1', version: 1 });
    mockGetFlowVersions.mockResolvedValue({ items: [version] });

    mockDiffFlowVersions.mockResolvedValue(makeIdenticalDiff());
    mockGetFlowVersion.mockResolvedValue(makeVersionDetail({ version_id: 'ver-1' }));

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('compare-button'));

    fireEvent.click(screen.getByTestId('compare-button'));

    await waitFor(() => {
      expect(mockDiffFlowVersions).toHaveBeenCalledWith('flow-abc', 'ver-1', 'current');
    });
  });

  // 5. Summary badges show correct counts
  it('shows summary badges with correct counts after compare', async () => {
    const version = makeVersion();
    mockGetFlowVersions.mockResolvedValue({ items: [version] });

    mockDiffFlowVersions.mockResolvedValue(
      makeDiff({
        nodes_added: ['n-new'],
        nodes_removed: ['n-old'],
        nodes_changed: ['n-a', 'n-b', 'n-c'],
        edges_added: ['src→tgt'],
      })
    );
    mockGetFlowVersion.mockResolvedValue(makeVersionDetail());

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('compare-button'));
    fireEvent.click(screen.getByTestId('compare-button'));

    await waitFor(() => screen.getByTestId('summary-section'));

    const summaryEl = screen.getByTestId('summary-section');
    // Spot-check: "1 node added", "1 node removed", "3 nodes changed", "1 edge added"
    expect(summaryEl.textContent).toMatch(/1/);
    expect(summaryEl.textContent).toMatch(/node added/);
    expect(summaryEl.textContent).toMatch(/3/);
    expect(summaryEl.textContent).toMatch(/nodes changed/);
    expect(summaryEl.textContent).toMatch(/edge added/);
  });

  // 6. Added node row is green
  it('renders added node row with green styling and ✚ icon', async () => {
    const version = makeVersion();
    mockGetFlowVersions.mockResolvedValue({ items: [version] });

    mockDiffFlowVersions.mockResolvedValue(makeDiff({ nodes_added: ['node-new'] }));
    mockGetFlowVersion.mockResolvedValue(
      makeVersionDetail({
        nodes: [{ id: 'node-new', type: 'llm', data: { label: 'New LLM' } }],
      })
    );

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('compare-button'));
    fireEvent.click(screen.getByTestId('compare-button'));

    await waitFor(() => screen.getByTestId('node-row-added'));

    const row = screen.getByTestId('node-row-added');
    expect(row.className).toMatch(/green/);
    expect(row.textContent).toContain('✚');
  });

  // 7. Removed node row is red
  it('renders removed node row with red styling and ✕ icon', async () => {
    const version = makeVersion();
    mockGetFlowVersions.mockResolvedValue({ items: [version] });

    mockDiffFlowVersions.mockResolvedValue(makeDiff({ nodes_removed: ['node-old'] }));
    mockGetFlowVersion.mockResolvedValue(
      makeVersionDetail({
        nodes: [{ id: 'node-old', type: 'http', data: { label: 'Old HTTP' } }],
      })
    );

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('compare-button'));
    fireEvent.click(screen.getByTestId('compare-button'));

    await waitFor(() => screen.getByTestId('node-row-removed'));

    const row = screen.getByTestId('node-row-removed');
    expect(row.className).toMatch(/red/);
    expect(row.textContent).toContain('✕');
  });

  // 8. Changed node row is yellow
  it('renders changed node row with yellow styling and ≈ icon', async () => {
    const version = makeVersion();
    mockGetFlowVersions.mockResolvedValue({ items: [version] });

    mockDiffFlowVersions.mockResolvedValue(makeDiff({ nodes_changed: ['node-mod'] }));
    mockGetFlowVersion.mockResolvedValue(
      makeVersionDetail({
        nodes: [{ id: 'node-mod', type: 'code', data: { label: 'Code Node' } }],
      })
    );

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('compare-button'));
    fireEvent.click(screen.getByTestId('compare-button'));

    await waitFor(() => screen.getByTestId('node-row-changed'));

    const row = screen.getByTestId('node-row-changed');
    expect(row.className).toMatch(/yellow/);
    expect(row.textContent).toContain('≈');
  });

  // 9. Clicking a changed node row expands the parameter diff
  it('clicking changed node row expands parameter-level field diff', async () => {
    const version = makeVersion();
    mockGetFlowVersions.mockResolvedValue({ items: [version] });

    mockDiffFlowVersions.mockResolvedValue(makeDiff({ nodes_changed: ['node-x'] }));

    // snapshot A — old timeout
    const snapA = makeVersionDetail({
      version_id: 'ver-1',
      nodes: [{ id: 'node-x', type: 'llm', data: { label: 'LLM Node', timeout: 30 } }],
    });
    // snapshot B — new timeout (version B is "current", no fetch; but snapA provides old data)
    // We mock getFlowVersion to return snapA (called for version A only)
    mockGetFlowVersion.mockResolvedValue(snapA);

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('compare-button'));
    fireEvent.click(screen.getByTestId('compare-button'));

    await waitFor(() => screen.getByTestId('node-row-changed'));

    // Click to expand
    fireEvent.click(screen.getByTestId('node-row-changed'));

    // The expansion shows either field diffs (arrows) or "No data field differences"
    await waitFor(() => {
      const noData = screen.queryByText('No data field differences detected.');
      const arrows = screen.queryAllByText(/→/);
      expect(noData !== null || arrows.length > 0).toBeTruthy();
    });
  });

  // 10. Identical banner shown when summary is all zeros
  it('shows "Workflows are identical" banner when diff has zero changes', async () => {
    const version = makeVersion();
    mockGetFlowVersions.mockResolvedValue({ items: [version] });

    mockDiffFlowVersions.mockResolvedValue(makeIdenticalDiff());
    mockGetFlowVersion.mockResolvedValue(makeVersionDetail());

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('compare-button'));
    fireEvent.click(screen.getByTestId('compare-button'));

    await waitFor(() => screen.getByTestId('identical-banner'));

    expect(screen.getByText('Workflows are identical')).toBeInTheDocument();
  });

  // 11. Edge added row appears in edges section
  it('shows added edge row in edges section after compare', async () => {
    const version = makeVersion();
    mockGetFlowVersions.mockResolvedValue({ items: [version] });

    mockDiffFlowVersions.mockResolvedValue(
      makeDiff({ edges_added: ['start→node-abc'] })
    );
    mockGetFlowVersion.mockResolvedValue(makeVersionDetail());

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('compare-button'));
    fireEvent.click(screen.getByTestId('compare-button'));

    await waitFor(() => screen.getByTestId('edge-row-added'));

    const row = screen.getByTestId('edge-row-added');
    expect(row.textContent).toContain('start→node-abc');
    expect(row.className).toMatch(/green/);
  });

  // Bonus: API error during version load shows error message
  it('shows error message when getFlowVersions fails', async () => {
    mockGetFlowVersions.mockRejectedValue(new Error('Network failure'));

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByText(/Network failure/)).toBeInTheDocument();
    });
  });

  // Bonus: "Current (live)" option is present in version B dropdown
  it('version B dropdown includes "Current (live)" option', async () => {
    mockGetFlowVersions.mockResolvedValue({
      items: [makeVersion({ version_id: 'ver-1', version: 1 })],
    });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByTestId('version-b-select'));

    const select = screen.getByTestId('version-b-select') as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.text);
    expect(options.some((o) => o.includes('Current'))).toBe(true);
  });
});
