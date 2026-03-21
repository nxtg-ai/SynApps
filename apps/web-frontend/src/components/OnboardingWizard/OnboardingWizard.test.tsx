/**
 * OnboardingWizard tests - 14 tests covering all 5 steps, API calls,
 * localStorage persistence, and navigation.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import OnboardingWizard from './OnboardingWizard';

// ── Mock ApiService ──────────────────────────────────────────────────────

vi.mock('../../services/ApiService', () => ({
  apiService: {
    createFlow: vi.fn(),
    updateFlow: vi.fn(),
    executeFlow: vi.fn(),
    publishToMarketplace: vi.fn(),
  },
}));

// ── Mock authStore ───────────────────────────────────────────────────────

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: any) => any) =>
    selector({
      user: { email: 'test@synapps.dev', name: 'Test User' },
      isAuthenticated: true,
      isLoading: false,
    }),
}));

import { apiService } from '../../services/ApiService';

// ── Helpers ──────────────────────────────────────────────────────────────

const STORAGE_KEY = 'synapps_onboarding';

function renderWizard(props?: Partial<{ onComplete: () => void; onDismiss: () => void }>) {
  const onComplete = props?.onComplete ?? vi.fn();
  const onDismiss = props?.onDismiss ?? vi.fn();
  return {
    onComplete,
    onDismiss,
    ...render(<OnboardingWizard onComplete={onComplete} onDismiss={onDismiss} />),
  };
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('OnboardingWizard', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  // 1. Renders step 1 on first visit (no localStorage)
  it('renders step 1 on first visit when no localStorage exists', () => {
    renderWizard();

    expect(screen.getByTestId('onboarding-step-1')).toBeInTheDocument();
    expect(screen.getByText('Welcome to SynApps')).toBeInTheDocument();
    expect(screen.getByText(/build your first AI workflow/)).toBeInTheDocument();
  });

  // 2. "Let's go!" advances to step 2
  it('advances to step 2 when "Let\'s go!" is clicked', () => {
    renderWizard();

    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));

    expect(screen.getByTestId('onboarding-step-2')).toBeInTheDocument();
    expect(screen.getByText('Create Your Workflow')).toBeInTheDocument();
  });

  // 3. Step 2 shows workflow name input
  it('shows workflow name input on step 2', () => {
    renderWizard();

    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));

    const input = screen.getByTestId('workflow-name-input');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('type', 'text');
  });

  // 4. Create Workflow calls POST /flows API
  it('calls createFlow API when Create Workflow is clicked', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });

    renderWizard();

    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));

    const input = screen.getByTestId('workflow-name-input');
    fireEvent.change(input, { target: { value: 'My Test Workflow' } });

    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => {
      expect(apiService.createFlow).toHaveBeenCalledWith({
        name: 'My Test Workflow',
        nodes: [],
        edges: [],
      });
    });

    // Should advance to step 3
    await waitFor(() => {
      expect(screen.getByTestId('onboarding-step-3')).toBeInTheDocument();
    });
  });

  // 5. Step 3 shows node type cards
  it('shows node type cards on step 3', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });

    renderWizard();

    // Navigate to step 3
    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('onboarding-step-3')).toBeInTheDocument();
    });

    expect(screen.getByTestId('add-node-llm')).toBeInTheDocument();
    expect(screen.getByTestId('add-node-http')).toBeInTheDocument();
    expect(screen.getByTestId('add-node-code')).toBeInTheDocument();
  });

  // 6. Add LLM node calls update flow API
  it('calls updateFlow API when adding an LLM node', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });
    (apiService.updateFlow as Mock).mockResolvedValue({});

    renderWizard();

    // Navigate to step 3
    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('add-node-llm')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('add-node-llm'));

    await waitFor(() => {
      expect(apiService.updateFlow).toHaveBeenCalledWith(
        'flow-123',
        expect.objectContaining({
          name: 'Test Flow',
          nodes: expect.arrayContaining([
            expect.objectContaining({ type: 'llm' }),
          ]),
          edges: [],
        }),
      );
    });
  });

  // 7. Node count increments after adding node
  it('increments node count after adding a node', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });
    (apiService.updateFlow as Mock).mockResolvedValue({});

    renderWizard();

    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('0 node(s) added');
    });

    fireEvent.click(screen.getByTestId('add-node-llm'));

    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('1 node(s) added');
    });
  });

  // 8. Continue button disabled with 0 nodes, enabled with 1+
  it('disables continue button with 0 nodes and enables with 1+', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });
    (apiService.updateFlow as Mock).mockResolvedValue({});

    renderWizard();

    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('onboarding-step-3')).toBeInTheDocument();
    });

    // Continue button should be disabled with 0 nodes
    const continueBtn = screen.getByText(/Continue with 0 node/);
    expect(continueBtn).toBeDisabled();

    // Add a node
    fireEvent.click(screen.getByTestId('add-node-http'));

    await waitFor(() => {
      const enabledBtn = screen.getByText(/Continue with 1 node/);
      expect(enabledBtn).not.toBeDisabled();
    });
  });

  // 9. Step 4 shows test run button
  it('shows test run button on step 4', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });
    (apiService.updateFlow as Mock).mockResolvedValue({});

    renderWizard();

    // Navigate through steps 1-3
    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => screen.getByTestId('add-node-llm'));
    fireEvent.click(screen.getByTestId('add-node-llm'));

    await waitFor(() => screen.getByText(/Continue with 1 node/));
    fireEvent.click(screen.getByText(/Continue with 1 node/));

    expect(screen.getByTestId('onboarding-step-4')).toBeInTheDocument();
    expect(screen.getByTestId('test-run-btn')).toBeInTheDocument();
  });

  // 10. Test run calls execute API
  it('calls executeFlow API when Run Test is clicked', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });
    (apiService.updateFlow as Mock).mockResolvedValue({});
    (apiService.executeFlow as Mock).mockResolvedValue({ status: 'success' });

    renderWizard();

    // Navigate to step 4
    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => screen.getByTestId('add-node-llm'));
    fireEvent.click(screen.getByTestId('add-node-llm'));
    await waitFor(() => screen.getByText(/Continue with 1 node/));
    fireEvent.click(screen.getByText(/Continue with 1 node/));

    fireEvent.click(screen.getByTestId('test-run-btn'));

    await waitFor(() => {
      expect(apiService.executeFlow).toHaveBeenCalledWith('flow-123', {
        input: 'Hello from SynApps onboarding!',
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('test-result')).toBeInTheDocument();
    });
  });

  // 11. Skip test advances to step 5
  it('advances to step 5 when skip test is clicked', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });
    (apiService.updateFlow as Mock).mockResolvedValue({});

    renderWizard();

    // Navigate to step 4
    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => screen.getByTestId('add-node-llm'));
    fireEvent.click(screen.getByTestId('add-node-llm'));
    await waitFor(() => screen.getByText(/Continue with 1 node/));
    fireEvent.click(screen.getByText(/Continue with 1 node/));

    fireEvent.click(screen.getByTestId('skip-test'));

    expect(screen.getByTestId('onboarding-step-5')).toBeInTheDocument();
  });

  // 12. Step 5 shows publish form
  it('shows publish form on step 5', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });
    (apiService.updateFlow as Mock).mockResolvedValue({});

    renderWizard();

    // Navigate to step 5
    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => screen.getByTestId('add-node-llm'));
    fireEvent.click(screen.getByTestId('add-node-llm'));
    await waitFor(() => screen.getByText(/Continue with 1 node/));
    fireEvent.click(screen.getByText(/Continue with 1 node/));
    fireEvent.click(screen.getByTestId('skip-test'));

    expect(screen.getByTestId('onboarding-step-5')).toBeInTheDocument();
    expect(screen.getByText('Share Your Workflow')).toBeInTheDocument();
    expect(screen.getByTestId('publish-btn')).toBeInTheDocument();
  });

  // 13. Skip publish calls onComplete
  it('calls onComplete when skip publish is clicked', async () => {
    (apiService.createFlow as Mock).mockResolvedValue({ id: 'flow-123' });
    (apiService.updateFlow as Mock).mockResolvedValue({});

    const onComplete = vi.fn();
    render(
      <OnboardingWizard onComplete={onComplete} onDismiss={vi.fn()} />,
    );

    // Navigate to step 5
    fireEvent.click(screen.getByTestId('onboarding-welcome-btn'));
    fireEvent.change(screen.getByTestId('workflow-name-input'), {
      target: { value: 'Test Flow' },
    });
    fireEvent.click(screen.getByTestId('create-workflow-btn'));

    await waitFor(() => screen.getByTestId('add-node-llm'));
    fireEvent.click(screen.getByTestId('add-node-llm'));
    await waitFor(() => screen.getByText(/Continue with 1 node/));
    fireEvent.click(screen.getByText(/Continue with 1 node/));
    fireEvent.click(screen.getByTestId('skip-test'));

    fireEvent.click(screen.getByTestId('skip-publish'));

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  // 14. Progress restored from localStorage on remount
  it('restores progress from localStorage on remount', () => {
    const savedProgress = {
      step: 3,
      completed: [true, true, false, false, false],
      flowId: 'flow-saved',
      workflowName: 'Saved Flow',
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(savedProgress));

    renderWizard();

    // Should render step 3 (not step 1)
    expect(screen.getByTestId('onboarding-step-3')).toBeInTheDocument();
    expect(screen.getByText('Add Nodes to Your Workflow')).toBeInTheDocument();
  });
});
