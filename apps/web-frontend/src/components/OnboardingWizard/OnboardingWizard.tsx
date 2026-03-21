/**
 * OnboardingWizard - 5-step guided setup for new SynApps users.
 *
 * Progress is persisted to localStorage so users can resume if they leave.
 * Steps: Welcome -> Create Workflow -> Add Nodes -> Test Run -> Publish
 */
import React, { useState, useEffect, useCallback } from 'react';
import { apiService } from '../../services/ApiService';
import { useAuthStore } from '../../stores/authStore';

// ── Types ────────────────────────────────────────────────────────────────

export interface OnboardingWizardProps {
  onComplete: () => void;
  onDismiss: () => void;
}

interface OnboardingProgress {
  step: number;
  completed: boolean[];
  flowId?: string;
  workflowName?: string;
  publishedListingId?: string;
}

interface AddedNode {
  id: string;
  type: string;
  label: string;
}

const STORAGE_KEY = 'synapps_onboarding';

const STEP_NAMES = ['Welcome', 'Create', 'Add Nodes', 'Test', 'Publish'] as const;

const DEFAULT_PROGRESS: OnboardingProgress = {
  step: 1,
  completed: [false, false, false, false, false],
};

// ── localStorage helpers (SSR-safe) ──────────────────────────────────────

function loadProgress(): OnboardingProgress {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as OnboardingProgress;
      if (parsed && typeof parsed.step === 'number' && Array.isArray(parsed.completed)) {
        return parsed;
      }
    }
  } catch {
    // corrupt or unavailable — use defaults
  }
  return { ...DEFAULT_PROGRESS, completed: [...DEFAULT_PROGRESS.completed] };
}

function saveProgress(progress: OnboardingProgress): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch {
    // storage full or unavailable — silently degrade
  }
}

function markOnboardingComplete(): void {
  try {
    const progress = loadProgress();
    progress.completed = progress.completed.map(() => true);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch {
    // storage unavailable
  }
}

// ── Component ────────────────────────────────────────────────────────────

const OnboardingWizard: React.FC<OnboardingWizardProps> = ({ onComplete, onDismiss }) => {
  const user = useAuthStore((s) => s.user);

  const [progress, setProgress] = useState<OnboardingProgress>(loadProgress);
  const [workflowName, setWorkflowName] = useState(progress.workflowName ?? '');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [workflowCategory, setWorkflowCategory] = useState('general');
  const [addedNodes, setAddedNodes] = useState<AddedNode[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [publishName, setPublishName] = useState('');
  const [publishDescription, setPublishDescription] = useState('');
  const [publishTags, setPublishTags] = useState('');
  const [publishSuccess, setPublishSuccess] = useState(false);

  // Persist progress on every step change
  useEffect(() => {
    saveProgress(progress);
  }, [progress]);

  // Sync publish name with workflow name when entering step 5
  useEffect(() => {
    if (progress.step === 5 && !publishName) {
      setPublishName(workflowName);
    }
  }, [progress.step, workflowName, publishName]);

  const goToStep = useCallback(
    (step: number) => {
      setError(null);
      setProgress((prev) => ({ ...prev, step }));
    },
    [],
  );

  const markStepCompleted = useCallback(
    (stepIndex: number) => {
      setProgress((prev) => {
        const completed = [...prev.completed];
        completed[stepIndex] = true;
        return { ...prev, completed };
      });
    },
    [],
  );

  const handleBack = useCallback(() => {
    if (progress.step > 1) {
      goToStep(progress.step - 1);
    }
  }, [progress.step, goToStep]);

  const handleDismiss = useCallback(() => {
    saveProgress(progress);
    onDismiss();
  }, [progress, onDismiss]);

  // ── Step 1: Welcome ──────────────────────────────────────────────────

  const handleWelcome = useCallback(() => {
    markStepCompleted(0);
    goToStep(2);
  }, [markStepCompleted, goToStep]);

  // ── Step 2: Create Workflow ──────────────────────────────────────────

  const handleCreateWorkflow = useCallback(async () => {
    if (!workflowName.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const result = await apiService.createFlow({
        name: workflowName.trim(),
        nodes: [],
        edges: [],
      });

      setProgress((prev) => ({
        ...prev,
        flowId: result.id,
        workflowName: workflowName.trim(),
        step: 3,
        completed: prev.completed.map((c, i) => (i === 1 ? true : c)),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create workflow';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [workflowName]);

  // ── Step 3: Add Nodes ────────────────────────────────────────────────

  const handleAddNode = useCallback(
    async (nodeType: string, label: string) => {
      if (!progress.flowId) return;

      setIsLoading(true);
      setError(null);

      const nodeId = `${nodeType}-${Date.now()}`;
      const newNode = {
        id: nodeId,
        type: nodeType,
        position: { x: 100 + addedNodes.length * 200, y: 100 },
        data: { label },
      };

      const allNodes = [
        ...addedNodes.map((n, i) => ({
          id: n.id,
          type: n.type,
          position: { x: 100 + i * 200, y: 100 },
          data: { label: n.label },
        })),
        newNode,
      ];

      try {
        await apiService.updateFlow(progress.flowId, {
          name: workflowName,
          nodes: allNodes,
          edges: [],
        });

        setAddedNodes((prev) => [...prev, { id: nodeId, type: nodeType, label }]);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to add node';
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    [progress.flowId, addedNodes, workflowName],
  );

  const handleContinueWithNodes = useCallback(() => {
    markStepCompleted(2);
    goToStep(4);
  }, [markStepCompleted, goToStep]);

  // ── Step 4: Test Run ─────────────────────────────────────────────────

  const handleTestRun = useCallback(async () => {
    if (!progress.flowId) return;

    setIsLoading(true);
    setError(null);
    setTestResult(null);

    try {
      const result = await apiService.executeFlow(progress.flowId, {
        input: 'Hello from SynApps onboarding!',
      });

      setTestResult({
        success: true,
        message: result?.status === 'error'
          ? `Execution completed with errors: ${result?.error || 'Unknown error'}`
          : 'Workflow executed successfully!',
      });
      markStepCompleted(3);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Test execution failed';
      setTestResult({ success: false, message });
    } finally {
      setIsLoading(false);
    }
  }, [progress.flowId, markStepCompleted]);

  const handleSkipTest = useCallback(() => {
    goToStep(5);
  }, [goToStep]);

  // ── Step 5: Publish ──────────────────────────────────────────────────

  const handlePublish = useCallback(async () => {
    if (!progress.flowId) return;

    setIsLoading(true);
    setError(null);

    const tags = publishTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      const result = await apiService.publishToMarketplace({
        flow_id: progress.flowId,
        name: publishName.trim() || workflowName,
        description: publishDescription.trim(),
        category: workflowCategory,
        tags,
      });

      setProgress((prev) => ({
        ...prev,
        publishedListingId: result.listing_id,
        completed: prev.completed.map((c, i) => (i === 4 ? true : c)),
      }));
      setPublishSuccess(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to publish';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [progress.flowId, publishName, publishDescription, publishTags, workflowName, workflowCategory]);

  const handleSkipPublish = useCallback(() => {
    markOnboardingComplete();
    onComplete();
  }, [onComplete]);

  const handleFinish = useCallback(() => {
    markOnboardingComplete();
    onComplete();
  }, [onComplete]);

  // ── Render helpers ───────────────────────────────────────────────────

  const renderProgressBar = () => (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-400">Step {progress.step} of 5</span>
        <span className="text-sm text-slate-400">{STEP_NAMES[progress.step - 1]}</span>
      </div>
      <div className="flex gap-1">
        {STEP_NAMES.map((name, i) => (
          <div key={name} className="flex-1 flex flex-col items-center gap-1">
            <div
              className={`h-2 w-full rounded-full transition-colors ${
                i < progress.step
                  ? 'bg-indigo-500'
                  : i === progress.step - 1
                    ? 'bg-indigo-500'
                    : 'bg-slate-700'
              }`}
            />
            <span
              className={`text-xs ${
                i === progress.step - 1 ? 'text-indigo-400 font-medium' : 'text-slate-500'
              }`}
            >
              {name}
            </span>
          </div>
        ))}
      </div>
    </div>
  );

  const renderStep1 = () => (
    <div data-testid="onboarding-step-1" className="text-center">
      <h2 className="text-3xl font-bold text-white mb-4">Welcome to SynApps</h2>
      <p className="text-lg text-slate-300 mb-8">
        Let&apos;s build your first AI workflow in 5 minutes.
      </p>
      {user && (
        <p className="text-sm text-slate-400 mb-6">
          Signed in as <span className="text-indigo-400">{user.email}</span>
        </p>
      )}
      <button
        data-testid="onboarding-welcome-btn"
        onClick={handleWelcome}
        className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg transition-colors"
      >
        Let&apos;s go!
      </button>
    </div>
  );

  const renderStep2 = () => (
    <div data-testid="onboarding-step-2">
      <h2 className="text-2xl font-bold text-white mb-6">Create Your Workflow</h2>

      <div className="space-y-4 max-w-md mx-auto">
        <div>
          <label htmlFor="workflow-name" className="block text-sm font-medium text-slate-300 mb-1">
            Workflow Name <span className="text-red-400">*</span>
          </label>
          <input
            id="workflow-name"
            data-testid="workflow-name-input"
            type="text"
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            placeholder="My First Workflow"
            className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>

        <div>
          <label htmlFor="workflow-desc" className="block text-sm font-medium text-slate-300 mb-1">
            Description
          </label>
          <textarea
            id="workflow-desc"
            value={workflowDescription}
            onChange={(e) => setWorkflowDescription(e.target.value)}
            placeholder="What does this workflow do?"
            rows={3}
            className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
          />
        </div>

        <div>
          <label htmlFor="workflow-cat" className="block text-sm font-medium text-slate-300 mb-1">
            Category
          </label>
          <select
            id="workflow-cat"
            value={workflowCategory}
            onChange={(e) => setWorkflowCategory(e.target.value)}
            className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          >
            <option value="general">General</option>
            <option value="automation">Automation</option>
            <option value="data-processing">Data Processing</option>
            <option value="ai-ml">AI / ML</option>
          </select>
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button
          data-testid="create-workflow-btn"
          onClick={handleCreateWorkflow}
          disabled={!workflowName.trim() || isLoading}
          className="w-full px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-semibold rounded-lg transition-colors"
        >
          {isLoading ? 'Creating...' : 'Create Workflow'}
        </button>
      </div>
    </div>
  );

  const nodeTypes = [
    {
      type: 'llm',
      label: 'LLM Node',
      icon: '\uD83E\uDDE0',
      description: 'Process text with AI language models',
      testId: 'add-node-llm',
    },
    {
      type: 'http',
      label: 'HTTP Node',
      icon: '\uD83C\uDF10',
      description: 'Make HTTP requests to external APIs',
      testId: 'add-node-http',
    },
    {
      type: 'code',
      label: 'Code Node',
      icon: '\uD83D\uDCBB',
      description: 'Run custom JavaScript or Python code',
      testId: 'add-node-code',
    },
  ];

  const renderStep3 = () => (
    <div data-testid="onboarding-step-3">
      <h2 className="text-2xl font-bold text-white mb-2">Add Nodes to Your Workflow</h2>
      <p className="text-slate-400 mb-6">Choose node types to add to your workflow.</p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto mb-6">
        {nodeTypes.map((node) => (
          <div
            key={node.type}
            className="bg-slate-800 border border-slate-700 rounded-lg p-4 flex flex-col items-center text-center"
          >
            <span className="text-3xl mb-2">{node.icon}</span>
            <h3 className="text-white font-semibold mb-1">{node.label}</h3>
            <p className="text-slate-400 text-sm mb-3">{node.description}</p>
            <button
              data-testid={node.testId}
              onClick={() => handleAddNode(node.type, node.label)}
              disabled={isLoading}
              className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 text-white text-sm rounded-md transition-colors"
            >
              Add
            </button>
          </div>
        ))}
      </div>

      <p data-testid="node-count" className="text-center text-slate-300 mb-4">
        {addedNodes.length} node(s) added
      </p>

      {error && <p className="text-center text-red-400 text-sm mb-4">{error}</p>}

      <div className="text-center">
        <button
          onClick={handleContinueWithNodes}
          disabled={addedNodes.length < 1}
          className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-semibold rounded-lg transition-colors"
        >
          Continue with {addedNodes.length} node{addedNodes.length !== 1 ? 's' : ''}
        </button>
      </div>
    </div>
  );

  const renderStep4 = () => (
    <div data-testid="onboarding-step-4">
      <h2 className="text-2xl font-bold text-white mb-2">Test Your Workflow</h2>
      <p className="text-slate-400 mb-6">Run a quick test to make sure everything works.</p>

      <div className="max-w-md mx-auto text-center">
        <button
          data-testid="test-run-btn"
          onClick={handleTestRun}
          disabled={isLoading}
          className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 text-white font-semibold rounded-lg transition-colors mb-4"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Running...
            </span>
          ) : (
            'Run Test'
          )}
        </button>

        {testResult && (
          <div
            data-testid="test-result"
            className={`p-4 rounded-lg mb-4 ${
              testResult.success
                ? 'bg-green-900/30 border border-green-700 text-green-300'
                : 'bg-red-900/30 border border-red-700 text-red-300'
            }`}
          >
            {testResult.message}
          </div>
        )}

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {testResult?.success && (
          <button
            onClick={() => {
              markStepCompleted(3);
              goToStep(5);
            }}
            className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg transition-colors"
          >
            Continue
          </button>
        )}

        <div className="mt-4">
          <button
            data-testid="skip-test"
            onClick={handleSkipTest}
            className="text-slate-400 hover:text-slate-300 text-sm underline transition-colors"
          >
            Skip for now &rarr;
          </button>
        </div>
      </div>
    </div>
  );

  const renderStep5 = () => (
    <div data-testid="onboarding-step-5">
      {publishSuccess ? (
        <div data-testid="onboarding-complete-banner" className="text-center">
          <div className="mb-6 text-6xl animate-bounce">
            <span className="inline-block animate-pulse">&#127881;</span>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Published!</h2>
          <p className="text-lg text-slate-300 mb-8">You&apos;re a SynApps creator.</p>
          <style>{`
            @keyframes confetti-fall {
              0% { transform: translateY(-100%) rotate(0deg); opacity: 1; }
              100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
            }
            .confetti-piece {
              position: fixed;
              top: 0;
              width: 10px;
              height: 10px;
              animation: confetti-fall 3s ease-in-out forwards;
            }
          `}</style>
          <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
            {Array.from({ length: 20 }).map((_, i) => (
              <div
                key={i}
                className="confetti-piece rounded-sm"
                style={{
                  left: `${5 + i * 4.5}%`,
                  backgroundColor: ['#818cf8', '#f472b6', '#34d399', '#fbbf24', '#60a5fa'][
                    i % 5
                  ],
                  animationDelay: `${i * 0.1}s`,
                  animationDuration: `${2 + Math.random() * 2}s`,
                }}
              />
            ))}
          </div>
          <button
            onClick={handleFinish}
            className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg transition-colors"
          >
            Go to Dashboard
          </button>
        </div>
      ) : (
        <>
          <h2 className="text-2xl font-bold text-white mb-6">Share Your Workflow</h2>

          <div className="space-y-4 max-w-md mx-auto">
            <div>
              <label htmlFor="publish-name" className="block text-sm font-medium text-slate-300 mb-1">
                Listing Name
              </label>
              <input
                id="publish-name"
                type="text"
                value={publishName}
                onChange={(e) => setPublishName(e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>

            <div>
              <label htmlFor="publish-desc" className="block text-sm font-medium text-slate-300 mb-1">
                Description
              </label>
              <textarea
                id="publish-desc"
                value={publishDescription}
                onChange={(e) => setPublishDescription(e.target.value)}
                rows={3}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
              />
            </div>

            <div>
              <label htmlFor="publish-tags" className="block text-sm font-medium text-slate-300 mb-1">
                Tags (comma-separated)
              </label>
              <input
                id="publish-tags"
                type="text"
                value={publishTags}
                onChange={(e) => setPublishTags(e.target.value)}
                placeholder="ai, automation, workflow"
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              data-testid="publish-btn"
              onClick={handlePublish}
              disabled={isLoading}
              className="w-full px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 text-white font-semibold rounded-lg transition-colors"
            >
              {isLoading ? 'Publishing...' : 'Publish to Marketplace'}
            </button>

            <div className="text-center">
              <button
                data-testid="skip-publish"
                onClick={handleSkipPublish}
                className="text-slate-400 hover:text-slate-300 text-sm underline transition-colors"
              >
                Not now, take me to the editor &rarr;
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );

  const renderCurrentStep = () => {
    switch (progress.step) {
      case 1:
        return renderStep1();
      case 2:
        return renderStep2();
      case 3:
        return renderStep3();
      case 4:
        return renderStep4();
      case 5:
        return renderStep5();
      default:
        return renderStep1();
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950 flex flex-col">
      {/* Header with close button */}
      <div className="flex items-center justify-between px-6 py-4">
        <h1 className="text-lg font-semibold text-white">SynApps Setup</h1>
        <button
          onClick={handleDismiss}
          className="text-slate-400 hover:text-white text-2xl leading-none transition-colors"
          aria-label="Close onboarding"
        >
          &times;
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 flex items-center justify-center px-6 pb-8">
        <div className="w-full max-w-2xl">
          {renderProgressBar()}

          {/* Back button for steps 2-5 */}
          {progress.step > 1 && (
            <button
              onClick={handleBack}
              className="mb-4 text-slate-400 hover:text-white text-sm flex items-center gap-1 transition-colors"
            >
              &larr; Back
            </button>
          )}

          {renderCurrentStep()}
        </div>
      </div>
    </div>
  );
};

export default OnboardingWizard;
