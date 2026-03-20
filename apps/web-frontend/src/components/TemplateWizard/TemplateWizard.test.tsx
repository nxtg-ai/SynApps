/**
 * TemplateWizard tests
 *
 * 12 tests covering the full 4-step wizard flow:
 *   - Step 1: use case selection
 *   - Step 2: node configuration
 *   - Step 3: test execution
 *   - Step 4: marketplace publish
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TemplateWizard from './TemplateWizard';

// ── Mock ApiService ──────────────────────────────────────────────────────

vi.mock('../../services/ApiService', () => ({
  apiService: {
    createFlow: vi.fn(),
    executeFlow: vi.fn(),
    publishToMarketplace: vi.fn(),
  },
}));

import { apiService } from '../../services/ApiService';

const mockCreateFlow = vi.mocked(apiService.createFlow);
const mockExecuteFlow = vi.mocked(apiService.executeFlow);
const mockPublishToMarketplace = vi.mocked(apiService.publishToMarketplace);

// ── Helpers ──────────────────────────────────────────────────────────────

function renderWizard(props: { onComplete?: (id: string) => void } = {}) {
  return render(<TemplateWizard {...props} />);
}

function selectUseCase(slug: string) {
  fireEvent.click(screen.getByTestId(`use-case-card-${slug}`));
}

function clickNext() {
  fireEvent.click(screen.getByTestId('wizard-next-button'));
}

function clickBack() {
  fireEvent.click(screen.getByTestId('wizard-back-button'));
}

// ── Setup ────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  mockCreateFlow.mockResolvedValue({ id: 'flow-wizard-1' });
  mockExecuteFlow.mockResolvedValue({ run_id: 'run-1', status: 'success', output: 'done' });
  mockPublishToMarketplace.mockResolvedValue({ listing_id: 'listing-abc' });
});

// ── Tests ────────────────────────────────────────────────────────────────

describe('TemplateWizard', () => {
  // 1. Renders step 1 with use case cards
  it('renders step 1 with use case cards', () => {
    renderWizard();
    expect(screen.getByTestId('wizard-step-1')).toBeInTheDocument();
    expect(screen.getByTestId('use-case-card-content-generation')).toBeInTheDocument();
    expect(screen.getByTestId('use-case-card-data-processing')).toBeInTheDocument();
    expect(screen.getByTestId('use-case-card-api-integration')).toBeInTheDocument();
    expect(screen.getByTestId('use-case-card-image-creation')).toBeInTheDocument();
    expect(screen.getByTestId('use-case-card-text-analysis')).toBeInTheDocument();
    expect(screen.getByTestId('use-case-card-custom')).toBeInTheDocument();
  });

  // 2. Clicking a use case card selects it (highlighted)
  it('highlights the selected use case card', () => {
    renderWizard();
    const card = screen.getByTestId('use-case-card-content-generation');
    expect(card.className).not.toContain('border-blue-500');

    selectUseCase('content-generation');
    expect(card.className).toContain('border-blue-500');
  });

  // 3. Next button advances to step 2
  it('advances to step 2 when next is clicked after selecting a use case', () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext();
    expect(screen.getByTestId('wizard-step-2')).toBeInTheDocument();
  });

  // 4. Back button returns to step 1
  it('returns to step 1 when back is clicked from step 2', () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext();
    expect(screen.getByTestId('wizard-step-2')).toBeInTheDocument();

    clickBack();
    expect(screen.getByTestId('wizard-step-1')).toBeInTheDocument();
  });

  // 5. Step 2 shows pre-populated nodes from selected use case
  it('pre-populates nodes from the selected use case', () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext();

    // Content Generation has 2 recommended nodes
    expect(screen.getByTestId('node-row-0')).toBeInTheDocument();
    expect(screen.getByTestId('node-row-1')).toBeInTheDocument();
  });

  // 6. Add Node button adds a new node row
  it('adds a new node row when Add Node is clicked', () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext();

    const addButton = screen.getByTestId('add-node-button');
    fireEvent.click(addButton);

    expect(screen.getByTestId('node-row-2')).toBeInTheDocument();
  });

  // 7. Step 3 shows test summary and run button
  it('shows test summary and run button on step 3', () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext(); // to step 2
    clickNext(); // to step 3

    expect(screen.getByTestId('wizard-step-3')).toBeInTheDocument();
    expect(screen.getByTestId('run-test-button')).toBeInTheDocument();
    // Node summary is shown
    expect(screen.getByText(/Content Writer/)).toBeInTheDocument();
  });

  // 8. Run test button triggers flow create + execute API calls
  it('calls createFlow and executeFlow when Run Test is clicked', async () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext();
    clickNext();

    fireEvent.click(screen.getByTestId('run-test-button'));

    await waitFor(() => {
      expect(mockCreateFlow).toHaveBeenCalledTimes(1);
    });

    expect(mockCreateFlow).toHaveBeenCalledWith(
      expect.objectContaining({
        name: expect.stringContaining('content-generation'),
        nodes: expect.any(Array),
        edges: expect.any(Array),
      }),
    );

    await waitFor(() => {
      expect(mockExecuteFlow).toHaveBeenCalledWith('flow-wizard-1', {
        input: 'Test input from wizard',
      });
    });
  });

  // 9. Test result shown after execution
  it('displays test result after successful execution', async () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext();
    clickNext();

    fireEvent.click(screen.getByTestId('run-test-button'));

    await waitFor(() => {
      expect(screen.getByTestId('test-result')).toBeInTheDocument();
    });

    expect(screen.getByText(/Test Passed/)).toBeInTheDocument();
  });

  // 10. Step 4 shows publish form
  it('shows the publish form on step 4', async () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext();
    clickNext();

    // Run test to unlock step 4 (flowId must be set)
    fireEvent.click(screen.getByTestId('run-test-button'));
    await waitFor(() => {
      expect(screen.getByTestId('test-result')).toBeInTheDocument();
    });

    clickNext(); // to step 4

    expect(screen.getByTestId('wizard-step-4')).toBeInTheDocument();
    expect(screen.getByTestId('publish-button')).toBeInTheDocument();
    expect(screen.getByTestId('publish-name-input')).toBeInTheDocument();
  });

  // 11. Publish button calls marketplace publish endpoint
  it('calls publishToMarketplace when publish button is clicked', async () => {
    renderWizard();
    selectUseCase('content-generation');
    clickNext();
    clickNext();

    fireEvent.click(screen.getByTestId('run-test-button'));
    await waitFor(() => {
      expect(screen.getByTestId('test-result')).toBeInTheDocument();
    });

    clickNext();

    // Fill in required name
    fireEvent.change(screen.getByTestId('publish-name-input'), {
      target: { value: 'My Workflow' },
    });

    fireEvent.click(screen.getByTestId('publish-button'));

    await waitFor(() => {
      expect(mockPublishToMarketplace).toHaveBeenCalledWith(
        expect.objectContaining({
          flow_id: 'flow-wizard-1',
          name: 'My Workflow',
        }),
      );
    });
  });

  // 12. Success state shown after publish
  it('shows success state after successful publish', async () => {
    const onComplete = vi.fn();
    renderWizard({ onComplete });

    selectUseCase('content-generation');
    clickNext();
    clickNext();

    fireEvent.click(screen.getByTestId('run-test-button'));
    await waitFor(() => {
      expect(screen.getByTestId('test-result')).toBeInTheDocument();
    });

    clickNext();

    fireEvent.change(screen.getByTestId('publish-name-input'), {
      target: { value: 'Published Flow' },
    });

    fireEvent.click(screen.getByTestId('publish-button'));

    await waitFor(() => {
      expect(screen.getByTestId('publish-success')).toBeInTheDocument();
    });

    expect(screen.getByText(/Published!/)).toBeInTheDocument();
    expect(screen.getByText(/View in marketplace/)).toBeInTheDocument();
    expect(onComplete).toHaveBeenCalledWith('listing-abc');
  });
});
