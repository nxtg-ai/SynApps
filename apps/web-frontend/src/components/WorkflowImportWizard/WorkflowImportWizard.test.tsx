/**
 * Tests for WorkflowImportWizard -- N-62 Workflow Import Wizard.
 *
 * 12 tests covering the 3-step wizard flow: format selection, JSON input,
 * review & import.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach, type Mock } from 'vitest';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import WorkflowImportWizard from './WorkflowImportWizard';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let mockFetch: Mock;

const VALID_JSON = JSON.stringify({ nodes: [{ id: 'n1' }, { id: 'n2' }], edges: [] });
const INVALID_JSON = '{ not valid json';

function renderWizard() {
  return render(
    <MemoryRouter>
      <WorkflowImportWizard />
    </MemoryRouter>,
  );
}

function advanceToStep2() {
  fireEvent.click(screen.getByText('Next'));
}

function fillTextarea(value: string) {
  const textarea = screen.getByTestId('json-textarea');
  fireEvent.change(textarea, { target: { value } });
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockFetch = vi.fn();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowImportWizard', () => {
  // 1. renders step 1 with format options (Gate 2)
  it('renders step 1 with format options', () => {
    renderWizard();
    const radios = screen.getAllByRole('radio');
    expect(radios).toBeTruthy();
    expect(radios.length).toBeGreaterThanOrEqual(1); // Gate 2: at least 1
    expect(radios.length).toBe(3); // n8n, zapier, synapps
    expect(screen.getByText('n8n')).toBeInTheDocument();
    expect(screen.getByText('Zapier')).toBeInTheDocument();
    expect(screen.getByText('SynApps (native)')).toBeInTheDocument();
  });

  // 2. selecting format enables Next (Next is always enabled on step 1)
  it('selecting a format keeps Next enabled', () => {
    renderWizard();
    const nextBtn = screen.getByText('Next');
    expect(nextBtn).not.toBeDisabled();

    // Switch to Zapier
    fireEvent.click(screen.getByLabelText('Zapier'));
    expect(nextBtn).not.toBeDisabled();
  });

  // 3. clicking Next advances to step 2
  it('clicking Next advances to step 2', () => {
    renderWizard();
    advanceToStep2();
    expect(screen.getByTestId('step-2')).toBeInTheDocument();
    expect(screen.getByText('Paste or Upload JSON')).toBeInTheDocument();
  });

  // 4. Next in step 2 disabled when textarea empty
  it('Next in step 2 is disabled when textarea is empty', () => {
    renderWizard();
    advanceToStep2();
    const nextBtn = screen.getByTestId('step2-next');
    expect(nextBtn).toBeDisabled();
  });

  // 5. valid JSON in textarea enables Next
  it('valid JSON in textarea enables Next', () => {
    renderWizard();
    advanceToStep2();
    fillTextarea(VALID_JSON);
    const nextBtn = screen.getByTestId('step2-next');
    expect(nextBtn).not.toBeDisabled();
  });

  // 6. invalid JSON shows error message
  it('invalid JSON shows error message', () => {
    renderWizard();
    advanceToStep2();
    fillTextarea(INVALID_JSON);
    expect(screen.getByTestId('parse-error')).toBeInTheDocument();
  });

  // 7. clicking Next (step 2 -> 3) shows review step
  it('clicking Next from step 2 shows review step', () => {
    renderWizard();
    advanceToStep2();
    fillTextarea(VALID_JSON);
    fireEvent.click(screen.getByTestId('step2-next'));
    expect(screen.getByTestId('step-3')).toBeInTheDocument();
    expect(screen.getByText('Review & Import')).toBeInTheDocument();
  });

  // 8. review step shows correct format label
  it('review step shows correct format label', () => {
    renderWizard();
    // Select Zapier first
    fireEvent.click(screen.getByLabelText('Zapier'));
    advanceToStep2();
    fillTextarea(VALID_JSON);
    fireEvent.click(screen.getByTestId('step2-next'));
    expect(screen.getByTestId('review-format')).toHaveTextContent('Zapier');
  });

  // 9. Import button calls POST /api/v1/workflows/import
  it('Import button calls POST /api/v1/workflows/import', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ flow_id: 'f1', name: 'Test', nodes_imported: 2, edges_imported: 1 }),
    });

    renderWizard();
    advanceToStep2();
    fillTextarea(VALID_JSON);
    fireEvent.click(screen.getByTestId('step2-next'));
    fireEvent.click(screen.getByTestId('import-button'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/workflows/import',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('"format"'),
        }),
      );
    });
  });

  // 10. on success shows "Imported!" with node/edge counts
  it('on success shows Imported with node and edge counts', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ flow_id: 'f1', name: 'Test', nodes_imported: 2, edges_imported: 1 }),
    });

    renderWizard();
    advanceToStep2();
    fillTextarea(VALID_JSON);
    fireEvent.click(screen.getByTestId('step2-next'));
    fireEvent.click(screen.getByTestId('import-button'));

    await waitFor(() => {
      const success = screen.getByTestId('import-success');
      expect(success).toBeInTheDocument();
      expect(success.textContent).toContain('Imported!');
      expect(success.textContent).toContain('2 nodes');
      expect(success.textContent).toContain('1 edges');
    });
  });

  // 11. on success shows Open in Editor link
  it('on success shows Open in Editor link', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ flow_id: 'f1', name: 'Test', nodes_imported: 2, edges_imported: 1 }),
    });

    renderWizard();
    advanceToStep2();
    fillTextarea(VALID_JSON);
    fireEvent.click(screen.getByTestId('step2-next'));
    fireEvent.click(screen.getByTestId('import-button'));

    await waitFor(() => {
      expect(screen.getByTestId('open-editor-link')).toBeInTheDocument();
      expect(screen.getByTestId('open-editor-link')).toHaveTextContent('Open in Editor');
    });
  });

  // 12. on error shows error message
  it('on error shows error message', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Unsupported format' }),
    });

    renderWizard();
    advanceToStep2();
    fillTextarea(VALID_JSON);
    fireEvent.click(screen.getByTestId('step2-next'));
    fireEvent.click(screen.getByTestId('import-button'));

    await waitFor(() => {
      const error = screen.getByTestId('import-error');
      expect(error).toBeInTheDocument();
      expect(error.textContent).toContain('Unsupported format');
    });
  });
});
