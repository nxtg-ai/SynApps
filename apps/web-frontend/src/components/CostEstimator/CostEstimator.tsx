/**
 * CostEstimator
 * Displays a pre-execution cost estimate for a workflow.
 * Fetches from the node-level cost calculator endpoint and shows
 * "Estimated cost: $X.XXXX" with an expandable breakdown table.
 */
import React, { useEffect, useState, useCallback } from 'react';
import apiService from '../../services/ApiService';
import { CostEstimate } from '../../types';

export interface CostEstimatorProps {
  /** Saved flow ID — triggers POST /flows/{flowId}/estimate-cost */
  flowId?: string;
  /** Arbitrary node list — triggers POST /flows/estimate-cost */
  nodes?: Array<{ id: string; type: string }>;
  /** Assumed iterations for foreach nodes (default 10) */
  foreachIterations?: number;
}

/** Group breakdown items by node_type for the summary table. */
function groupByType(
  breakdown: CostEstimate['breakdown'],
): Array<{ node_type: string; count: number; cost_per_node: number; subtotal: number }> {
  const map = new Map<string, { count: number; totalCost: number; perNode: number }>();
  for (const item of breakdown) {
    const existing = map.get(item.node_type);
    if (existing) {
      existing.count += 1;
      existing.totalCost += item.cost_usd;
    } else {
      map.set(item.node_type, {
        count: 1,
        totalCost: item.cost_usd,
        perNode: item.cost_usd,
      });
    }
  }
  return Array.from(map.entries()).map(([node_type, v]) => ({
    node_type,
    count: v.count,
    cost_per_node: v.count > 0 ? v.totalCost / v.count : 0,
    subtotal: v.totalCost,
  }));
}

const CostEstimator: React.FC<CostEstimatorProps> = ({ flowId, nodes, foreachIterations }) => {
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [showBreakdown, setShowBreakdown] = useState(false);

  const fetchEstimate = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      let result: CostEstimate;
      if (flowId) {
        result = await apiService.estimateFlowCost(flowId, foreachIterations);
      } else if (nodes) {
        result = await apiService.estimateCost(nodes, foreachIterations);
      } else {
        setLoading(false);
        return;
      }
      setEstimate(result);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [flowId, nodes, foreachIterations]);

  useEffect(() => {
    fetchEstimate();
  }, [fetchEstimate]);

  if (loading) {
    return (
      <div data-testid="cost-estimator" className="cost-estimator">
        <span>Calculating cost...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="cost-estimator" className="cost-estimator">
        <span>Cost estimate unavailable</span>
      </div>
    );
  }

  if (!estimate) {
    return null;
  }

  const grouped = groupByType(estimate.breakdown);

  return (
    <div data-testid="cost-estimator" className="cost-estimator">
      <span data-testid="cost-estimate-total">
        Estimated cost: ${estimate.total_usd.toFixed(4)}
      </span>
      <button
        data-testid="cost-breakdown-toggle"
        onClick={() => setShowBreakdown((prev) => !prev)}
        className="cost-breakdown-toggle-btn"
        title="Toggle cost breakdown"
      >
        {showBreakdown ? '-' : 'i'}
      </button>

      {showBreakdown && (
        <table data-testid="cost-breakdown-table" className="cost-breakdown-table">
          <thead>
            <tr>
              <th>Node Type</th>
              <th>Count</th>
              <th>Cost/Node</th>
              <th>Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {grouped.map((row) => (
              <tr key={row.node_type}>
                <td>{row.node_type}</td>
                <td>{row.count}</td>
                <td>${row.cost_per_node.toFixed(4)}</td>
                <td>${row.subtotal.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default CostEstimator;
