/**
 * CostEstimatePanel
 * Shows a pre-execution cost estimate for a saved workflow.
 * Collapses/expands and fetches data on demand.
 */
import React, { useState, useCallback } from 'react';
import apiService from '../../services/ApiService';
import { WorkflowCostEstimate } from '../../types';
import './CostEstimatePanel.css';

interface CostEstimatePanelProps {
  /** The saved flow ID. Pass null/undefined when the flow is not yet saved. */
  flowId: string | undefined;
  /** Optional input text (forwarded to the estimate endpoint for token sizing). */
  inputText?: string;
}

function confidenceLabel(confidence: WorkflowCostEstimate['confidence']): string {
  switch (confidence) {
    case 'high':
      return 'High';
    case 'medium':
      return 'Medium';
    case 'low':
      return 'Low';
  }
}

function costColorClass(usd: number): string {
  if (usd < 0.01) return 'cost-green';
  if (usd <= 0.10) return 'cost-yellow';
  return 'cost-red';
}

const CostEstimatePanel: React.FC<CostEstimatePanelProps> = ({ flowId, inputText = '' }) => {
  const [collapsed, setCollapsed] = useState(true);
  const [loading, setLoading] = useState(false);
  const [estimate, setEstimate] = useState<WorkflowCostEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchEstimate = useCallback(async () => {
    if (!flowId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await apiService.estimateWorkflowCost(flowId, inputText);
      setEstimate(result);
    } catch (err) {
      setError('Failed to fetch cost estimate.');
    } finally {
      setLoading(false);
    }
  }, [flowId, inputText]);

  const handleToggle = () => {
    setCollapsed((prev) => !prev);
  };

  if (!flowId) return null;

  return (
    <div className="cost-estimate-panel">
      <button className="cost-estimate-header" onClick={handleToggle} aria-expanded={!collapsed}>
        <span className="cost-estimate-title">Cost Estimate</span>
        <span className="cost-estimate-chevron">{collapsed ? '+' : '-'}</span>
      </button>

      {!collapsed && (
        <div className="cost-estimate-body">
          <button
            className="cost-estimate-btn"
            onClick={fetchEstimate}
            disabled={loading}
          >
            {loading ? (
              <span className="cost-estimate-spinner" aria-label="Loading" />
            ) : (
              'Estimate Cost'
            )}
          </button>

          {error && <p className="cost-estimate-error">{error}</p>}

          {estimate && !loading && (
            <div className="cost-estimate-result">
              <span className={`cost-estimate-usd ${costColorClass(estimate.estimated_usd)}`}>
                Estimated cost: {estimate.estimated_usd_formatted}
              </span>
              <span className="cost-estimate-tokens">
                Tokens: ~{estimate.estimated_token_input + estimate.estimated_token_output}
              </span>
              <span className={`cost-estimate-confidence confidence-${estimate.confidence}`}>
                Confidence: {confidenceLabel(estimate.confidence)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CostEstimatePanel;
