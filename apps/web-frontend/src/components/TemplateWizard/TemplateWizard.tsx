/**
 * TemplateWizard - A 4-step guided workflow builder for non-technical users.
 *
 * Steps:
 *   1. Choose Use Case   - pick from predefined categories
 *   2. Configure Nodes   - customise the node list
 *   3. Test              - create a draft flow and execute it
 *   4. Publish           - fill in metadata and publish to the marketplace
 */
import React, { useState, useCallback } from 'react';
import { apiService } from '../../services/ApiService';

// ── Types ────────────────────────────────────────────────────────────────

interface WizardNodeConfig {
  type: string;
  label: string;
  config: Record<string, string>;
}

interface UseCaseOption {
  slug: string;
  icon: string;
  title: string;
  description: string;
  recommendedNodes: WizardNodeConfig[];
}

interface PublishFormData {
  name: string;
  description: string;
  category: string;
  tags: string;
}

interface TemplateWizardProps {
  onComplete?: (listingId: string) => void;
}

// ── Use case catalogue ───────────────────────────────────────────────────

const USE_CASES: UseCaseOption[] = [
  {
    slug: 'content-generation',
    icon: '\u270D\uFE0F',
    title: 'Content Generation',
    description: 'Generate blog posts, social media content, and marketing copy with AI.',
    recommendedNodes: [
      { type: 'llm', label: 'Content Writer', config: { prompt: 'Write content about the topic' } },
      { type: 'transform', label: 'Formatter', config: { format: 'markdown' } },
    ],
  },
  {
    slug: 'data-processing',
    icon: '\uD83D\uDCCA',
    title: 'Data Processing',
    description: 'Clean, transform, and analyse datasets with automated pipelines.',
    recommendedNodes: [
      { type: 'http', label: 'Data Fetcher', config: { url: 'https://api.example.com/data' } },
      { type: 'transform', label: 'Data Transformer', config: { operation: 'map' } },
      { type: 'code', label: 'Analyser', config: { language: 'python' } },
    ],
  },
  {
    slug: 'api-integration',
    icon: '\uD83D\uDD17',
    title: 'API Integration',
    description: 'Connect external APIs and orchestrate data flows between services.',
    recommendedNodes: [
      { type: 'http', label: 'API Request', config: { method: 'GET' } },
      { type: 'transform', label: 'Response Mapper', config: { operation: 'extract' } },
      { type: 'http', label: 'API Response', config: { method: 'POST' } },
    ],
  },
  {
    slug: 'image-creation',
    icon: '\uD83C\uDFA8',
    title: 'Image Creation',
    description: 'Generate and process images using AI models and pipelines.',
    recommendedNodes: [
      { type: 'llm', label: 'Prompt Generator', config: { model: 'gpt-4' } },
      { type: 'http', label: 'Image API', config: { url: 'https://api.example.com/images' } },
    ],
  },
  {
    slug: 'text-analysis',
    icon: '\uD83D\uDD0D',
    title: 'Text Analysis',
    description: 'Analyse text for sentiment, entities, summaries, and insights.',
    recommendedNodes: [
      { type: 'llm', label: 'Text Analyser', config: { task: 'analyse' } },
      { type: 'transform', label: 'Result Extractor', config: { format: 'json' } },
    ],
  },
  {
    slug: 'custom',
    icon: '\u2699\uFE0F',
    title: 'Custom',
    description: 'Start from scratch and build a fully custom workflow.',
    recommendedNodes: [
      { type: 'llm', label: 'Node 1', config: {} },
    ],
  },
];

const NODE_TYPES = ['llm', 'http', 'code', 'transform', 'ifelse', 'merge', 'foreach'] as const;

const STEP_LABELS = ['Use Case', 'Configure', 'Test', 'Publish'] as const;

// ── Component ────────────────────────────────────────────────────────────

const TemplateWizard: React.FC<TemplateWizardProps> = ({ onComplete }) => {
  // Step tracking (0-indexed)
  const [currentStep, setCurrentStep] = useState(0);

  // Step 1 state
  const [selectedUseCase, setSelectedUseCase] = useState<string | null>(null);

  // Step 2 state
  const [nodes, setNodes] = useState<WizardNodeConfig[]>([]);

  // Step 3 state
  const [flowId, setFlowId] = useState<string | null>(null);
  const [testRunning, setTestRunning] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  // Step 4 state
  const [publishForm, setPublishForm] = useState<PublishFormData>({
    name: '',
    description: '',
    category: 'automation',
    tags: '',
  });
  const [publishing, setPublishing] = useState(false);
  const [publishedId, setPublishedId] = useState<string | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);

  // ── Navigation helpers ───────────────────────────────────────────────

  const canAdvance = useCallback((): boolean => {
    switch (currentStep) {
      case 0:
        return selectedUseCase !== null;
      case 1:
        return nodes.length > 0;
      case 2:
        return flowId !== null;
      case 3:
        return publishForm.name.trim().length > 0;
      default:
        return false;
    }
  }, [currentStep, selectedUseCase, nodes, flowId, publishForm.name]);

  const goNext = useCallback(() => {
    if (canAdvance() && currentStep < 3) {
      setCurrentStep((s) => s + 1);
    }
  }, [canAdvance, currentStep]);

  const goBack = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep((s) => s - 1);
    }
  }, [currentStep]);

  // ── Step 1 handlers ──────────────────────────────────────────────────

  const selectUseCase = useCallback((slug: string) => {
    setSelectedUseCase(slug);
    const useCase = USE_CASES.find((uc) => uc.slug === slug);
    if (useCase) {
      setNodes(useCase.recommendedNodes.map((n) => ({ ...n, config: { ...n.config } })));
    }
  }, []);

  // ── Step 2 handlers ──────────────────────────────────────────────────

  const addNode = useCallback(() => {
    setNodes((prev) => [...prev, { type: 'llm', label: '', config: {} }]);
  }, []);

  const updateNodeType = useCallback((index: number, type: string) => {
    setNodes((prev) => prev.map((n, i) => (i === index ? { ...n, type } : n)));
  }, []);

  const updateNodeLabel = useCallback((index: number, label: string) => {
    setNodes((prev) => prev.map((n, i) => (i === index ? { ...n, label } : n)));
  }, []);

  const removeNode = useCallback((index: number) => {
    setNodes((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const addConfigRow = useCallback((nodeIndex: number) => {
    setNodes((prev) =>
      prev.map((n, i) =>
        i === nodeIndex ? { ...n, config: { ...n.config, '': '' } } : n,
      ),
    );
  }, []);

  const removeConfigRow = useCallback((nodeIndex: number, key: string) => {
    setNodes((prev) =>
      prev.map((n, i) => {
        if (i !== nodeIndex) return n;
        const newConfig = { ...n.config };
        delete newConfig[key];
        return { ...n, config: newConfig };
      }),
    );
  }, []);

  const updateConfigKey = useCallback(
    (nodeIndex: number, oldKey: string, newKey: string) => {
      setNodes((prev) =>
        prev.map((n, i) => {
          if (i !== nodeIndex) return n;
          const entries = Object.entries(n.config).map(([k, v]) =>
            k === oldKey ? [newKey, v] : [k, v],
          );
          return { ...n, config: Object.fromEntries(entries) };
        }),
      );
    },
    [],
  );

  const updateConfigValue = useCallback(
    (nodeIndex: number, key: string, value: string) => {
      setNodes((prev) =>
        prev.map((n, i) =>
          i === nodeIndex ? { ...n, config: { ...n.config, [key]: value } } : n,
        ),
      );
    },
    [],
  );

  // ── Step 3 handler ───────────────────────────────────────────────────

  const runTest = useCallback(async () => {
    setTestRunning(true);
    setTestResult(null);
    setTestError(null);

    try {
      const flowNodes = nodes.map((n, i) => ({
        id: `node-${i}`,
        type: n.type,
        position: { x: 200 * i, y: 100 },
        data: { label: n.label, config: n.config },
      }));

      const flowEdges = nodes.slice(1).map((_, i) => ({
        id: `edge-${i}`,
        source: `node-${i}`,
        target: `node-${i + 1}`,
      }));

      const created = await apiService.createFlow({
        name: `Wizard Draft - ${selectedUseCase}`,
        nodes: flowNodes,
        edges: flowEdges,
      });

      const createdFlowId = created.id;
      setFlowId(createdFlowId);

      const result = await apiService.executeFlow(createdFlowId, {
        input: 'Test input from wizard',
      });
      setTestResult(result as Record<string, unknown>);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Test execution failed';
      setTestError(message);
    } finally {
      setTestRunning(false);
    }
  }, [nodes, selectedUseCase]);

  // ── Step 4 handler ───────────────────────────────────────────────────

  const publishToMarketplace = useCallback(async () => {
    if (!flowId) return;

    setPublishing(true);
    setPublishError(null);

    try {
      const result = await apiService.publishToMarketplace({
        flow_id: flowId,
        name: publishForm.name.trim(),
        description: publishForm.description.trim(),
        category: publishForm.category,
        tags: publishForm.tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      });
      setPublishedId(result.listing_id);
      onComplete?.(result.listing_id);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Publish failed';
      setPublishError(message);
    } finally {
      setPublishing(false);
    }
  }, [flowId, publishForm, onComplete]);

  // ── Step indicator ───────────────────────────────────────────────────

  const renderStepIndicator = () => (
    <div className="mb-8 flex items-center justify-center gap-2" data-testid="step-indicator">
      {STEP_LABELS.map((label, i) => (
        <React.Fragment key={label}>
          {i > 0 && (
            <span className="text-slate-500 select-none">{'\u2192'}</span>
          )}
          <span
            className={`rounded-full px-3 py-1 text-sm font-medium ${
              i === currentStep
                ? 'bg-blue-600 text-white'
                : i < currentStep
                  ? 'bg-blue-900/40 text-blue-300'
                  : 'bg-slate-800 text-slate-400'
            }`}
          >
            {i + 1} {label}
          </span>
        </React.Fragment>
      ))}
    </div>
  );

  // ── Step 1 ───────────────────────────────────────────────────────────

  const renderStep1 = () => (
    <div data-testid="wizard-step-1">
      <h2 className="mb-4 text-xl font-semibold text-slate-100">Choose a Use Case</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {USE_CASES.map((uc) => (
          <button
            key={uc.slug}
            data-testid={`use-case-card-${uc.slug}`}
            onClick={() => selectUseCase(uc.slug)}
            className={`rounded-lg border p-4 text-left transition-colors ${
              selectedUseCase === uc.slug
                ? 'border-blue-500 bg-blue-950/50 ring-2 ring-blue-500/50'
                : 'border-slate-700 bg-slate-800/50 hover:border-slate-600'
            }`}
          >
            <div className="mb-2 text-2xl">{uc.icon}</div>
            <h3 className="mb-1 font-semibold text-slate-100">{uc.title}</h3>
            <p className="text-sm text-slate-400">{uc.description}</p>
          </button>
        ))}
      </div>
    </div>
  );

  // ── Step 2 ───────────────────────────────────────────────────────────

  const renderStep2 = () => (
    <div data-testid="wizard-step-2">
      <h2 className="mb-4 text-xl font-semibold text-slate-100">Configure Nodes</h2>
      <div className="space-y-4">
        {nodes.map((node, index) => (
          <div
            key={index}
            data-testid={`node-row-${index}`}
            className="rounded-lg border border-slate-700 bg-slate-800/50 p-4"
          >
            <div className="mb-3 flex items-center gap-3">
              <select
                value={node.type}
                onChange={(e) => updateNodeType(index, e.target.value)}
                className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-200"
                data-testid={`node-type-select-${index}`}
              >
                {NODE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={node.label}
                onChange={(e) => updateNodeLabel(index, e.target.value)}
                placeholder="Node label"
                className="flex-1 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-200 placeholder-slate-500"
                data-testid={`node-label-input-${index}`}
              />
              <button
                onClick={() => removeNode(index)}
                className="rounded px-2 py-1 text-sm text-red-400 hover:bg-red-900/30"
                data-testid={`remove-node-${index}`}
              >
                Remove
              </button>
            </div>
            <div className="space-y-2">
              {Object.entries(node.config).map(([key, value]) => (
                <div key={key} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={key}
                    onChange={(e) => updateConfigKey(index, key, e.target.value)}
                    placeholder="Key"
                    className="w-1/3 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-200 placeholder-slate-500"
                  />
                  <input
                    type="text"
                    value={value}
                    onChange={(e) => updateConfigValue(index, key, e.target.value)}
                    placeholder="Value"
                    className="flex-1 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-200 placeholder-slate-500"
                  />
                  <button
                    onClick={() => removeConfigRow(index, key)}
                    className="text-sm text-slate-400 hover:text-red-400"
                  >
                    x
                  </button>
                </div>
              ))}
              <button
                onClick={() => addConfigRow(index)}
                className="text-sm text-blue-400 hover:text-blue-300"
              >
                + Add config
              </button>
            </div>
          </div>
        ))}
      </div>
      <button
        onClick={addNode}
        data-testid="add-node-button"
        className="mt-4 rounded-lg border border-dashed border-slate-600 px-4 py-2 text-sm text-slate-300 hover:border-slate-500 hover:text-slate-200"
      >
        + Add Node
      </button>
    </div>
  );

  // ── Step 3 ───────────────────────────────────────────────────────────

  const renderStep3 = () => (
    <div data-testid="wizard-step-3">
      <h2 className="mb-4 text-xl font-semibold text-slate-100">Test Your Workflow</h2>

      <div className="mb-6 rounded-lg border border-slate-700 bg-slate-800/50 p-4">
        <h3 className="mb-2 font-medium text-slate-200">Node Summary</h3>
        <ul className="space-y-1">
          {nodes.map((node, i) => (
            <li key={i} className="text-sm text-slate-400">
              <span className="font-mono text-slate-300">{node.type}</span>
              {node.label && ` \u2014 ${node.label}`}
            </li>
          ))}
        </ul>
      </div>

      <button
        data-testid="run-test-button"
        onClick={runTest}
        disabled={testRunning}
        className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-50"
      >
        {testRunning ? 'Running...' : 'Run Test'}
      </button>

      {testRunning && (
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          Executing workflow...
        </div>
      )}

      {testResult && (
        <div data-testid="test-result" className="mt-4 rounded-lg border border-green-700 bg-green-950/30 p-4">
          <h3 className="mb-2 font-medium text-green-300">Test Passed</h3>
          <pre className="overflow-auto text-sm text-slate-300">
            {JSON.stringify(testResult, null, 2)}
          </pre>
        </div>
      )}

      {testError && (
        <div data-testid="test-result" className="mt-4 rounded-lg border border-red-700 bg-red-950/30 p-4">
          <h3 className="mb-2 font-medium text-red-300">Test Failed</h3>
          <p className="text-sm text-red-400">{testError}</p>
        </div>
      )}
    </div>
  );

  // ── Step 4 ───────────────────────────────────────────────────────────

  const renderStep4 = () => (
    <div data-testid="wizard-step-4">
      <h2 className="mb-4 text-xl font-semibold text-slate-100">Publish to Marketplace</h2>

      {publishedId ? (
        <div data-testid="publish-success" className="rounded-lg border border-green-700 bg-green-950/30 p-6 text-center">
          <h3 className="mb-2 text-lg font-semibold text-green-300">Published!</h3>
          <a
            href="/marketplace"
            className="text-blue-400 underline hover:text-blue-300"
          >
            View in marketplace
          </a>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Name <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={publishForm.name}
                onChange={(e) => setPublishForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="My Awesome Workflow"
                className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500"
                data-testid="publish-name-input"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">Description</label>
              <textarea
                value={publishForm.description}
                onChange={(e) => setPublishForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Describe what this workflow does..."
                rows={3}
                className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">Category</label>
              <select
                value={publishForm.category}
                onChange={(e) => setPublishForm((f) => ({ ...f, category: e.target.value }))}
                className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200"
              >
                <option value="automation">Automation</option>
                <option value="content">Content</option>
                <option value="data">Data</option>
                <option value="integration">Integration</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Tags (comma-separated)
              </label>
              <input
                type="text"
                value={publishForm.tags}
                onChange={(e) => setPublishForm((f) => ({ ...f, tags: e.target.value }))}
                placeholder="ai, workflow, automation"
                className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500"
              />
            </div>
          </div>

          {/* Preview card */}
          <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4">
            <h3 className="mb-2 text-sm font-medium text-slate-400">Marketplace Preview</h3>
            <div className="rounded-lg border border-slate-600 bg-slate-900 p-4">
              <h4 className="text-lg font-semibold text-slate-100">
                {publishForm.name || 'Untitled Workflow'}
              </h4>
              <p className="mt-1 text-sm text-slate-400">
                {publishForm.description || 'No description provided.'}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {publishForm.tags
                  .split(',')
                  .map((t) => t.trim())
                  .filter(Boolean)
                  .map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300"
                    >
                      {tag}
                    </span>
                  ))}
              </div>
            </div>
          </div>

          {publishError && (
            <p className="text-sm text-red-400">{publishError}</p>
          )}

          <button
            data-testid="publish-button"
            onClick={publishToMarketplace}
            disabled={publishing || !publishForm.name.trim()}
            className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {publishing ? 'Publishing...' : 'Publish to Marketplace'}
          </button>
        </div>
      )}
    </div>
  );

  // ── Main render ──────────────────────────────────────────────────────

  const stepRenderers = [renderStep1, renderStep2, renderStep3, renderStep4];

  return (
    <div className="mx-auto max-w-4xl px-4 py-6" data-testid="template-wizard">
      {renderStepIndicator()}

      <div className="mb-8">{stepRenderers[currentStep]()}</div>

      <div className="flex justify-between">
        <button
          onClick={goBack}
          disabled={currentStep === 0}
          data-testid="wizard-back-button"
          className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-30"
        >
          Back
        </button>
        {currentStep < 3 && (
          <button
            onClick={goNext}
            disabled={!canAdvance()}
            data-testid="wizard-next-button"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            Next
          </button>
        )}
      </div>
    </div>
  );
};

export default TemplateWizard;
