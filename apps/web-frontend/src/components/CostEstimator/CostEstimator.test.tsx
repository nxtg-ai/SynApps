/**
 * CostEstimator tests
 *
 * Strategy:
 *   - Mock apiService at the module level so no real network calls are made
 *   - Use @testing-library/react for rendering and user interaction
 *   - Cover: loading state, cost display, formatting, breakdown toggle,
 *     breakdown table content, re-fetch on prop change, error state,
 *     free workflow display, foreachIterations forwarding
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CostEstimator from './CostEstimator';
import type { CostEstimate } from '../../types';

// ── Mock apiService ──────────────────────────────────────────────────────────

vi.mock('../../services/ApiService', () => ({
  default: {
    estimateFlowCost: vi.fn(),
    estimateCost: vi.fn(),
  },
}));

import apiService from '../../services/ApiService';

const mockEstimateFlowCost = vi.mocked(apiService.estimateFlowCost);
const mockEstimateCost = vi.mocked(apiService.estimateCost);

// ── Fixtures ─────────────────────────────────────────────────────────────────

const SAMPLE_ESTIMATE: CostEstimate = {
  total_usd: 0.024,
  currency: 'USD',
  breakdown: [
    { node_id: 'n1', node_type: 'llm', cost_usd: 0.002, note: 'llm base cost' },
    { node_id: 'n2', node_type: 'imagegen', cost_usd: 0.02, note: 'imagegen base cost' },
    { node_id: 'n3', node_type: 'code', cost_usd: 0.001, note: 'code base cost' },
    { node_id: 'n4', node_type: 'http', cost_usd: 0.0, note: 'free' },
  ],
  node_count: 4,
  billable_node_count: 3,
};

const FREE_ESTIMATE: CostEstimate = {
  total_usd: 0.0,
  currency: 'USD',
  breakdown: [
    { node_id: 'n1', node_type: 'http', cost_usd: 0.0, note: 'free' },
  ],
  node_count: 1,
  billable_node_count: 0,
};

// ── Tests ────────────────────────────────────────────────────────────────────

describe('CostEstimator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state while fetching', () => {
    // Never resolve to keep it in loading state
    mockEstimateFlowCost.mockReturnValue(new Promise(() => {}));
    render(<CostEstimator flowId="flow-1" />);
    expect(screen.getByText('Calculating cost...')).toBeTruthy();
  });

  it('shows cost estimate after load', async () => {
    mockEstimateFlowCost.mockResolvedValue(SAMPLE_ESTIMATE);
    render(<CostEstimator flowId="flow-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('cost-estimate-total')).toBeTruthy();
    });
    expect(screen.getByTestId('cost-estimate-total').textContent).toContain('$0.0240');
  });

  it('formats cost as $X.XXXX', async () => {
    mockEstimateFlowCost.mockResolvedValue(SAMPLE_ESTIMATE);
    render(<CostEstimator flowId="flow-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('cost-estimate-total')).toBeTruthy();
    });
    const text = screen.getByTestId('cost-estimate-total').textContent ?? '';
    // Should match $X.XXXX pattern
    expect(text).toMatch(/\$\d+\.\d{4}/);
  });

  it('breakdown toggle hidden initially', async () => {
    mockEstimateFlowCost.mockResolvedValue(SAMPLE_ESTIMATE);
    render(<CostEstimator flowId="flow-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('cost-breakdown-toggle')).toBeTruthy();
    });
    expect(screen.queryByTestId('cost-breakdown-table')).toBeNull();
  });

  it('clicking toggle shows breakdown table', async () => {
    mockEstimateFlowCost.mockResolvedValue(SAMPLE_ESTIMATE);
    render(<CostEstimator flowId="flow-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('cost-breakdown-toggle')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('cost-breakdown-toggle'));
    expect(screen.getByTestId('cost-breakdown-table')).toBeTruthy();
  });

  it('breakdown table shows node types', async () => {
    mockEstimateFlowCost.mockResolvedValue(SAMPLE_ESTIMATE);
    render(<CostEstimator flowId="flow-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('cost-breakdown-toggle')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('cost-breakdown-toggle'));
    const table = screen.getByTestId('cost-breakdown-table');
    expect(table.textContent).toContain('llm');
    expect(table.textContent).toContain('imagegen');
    expect(table.textContent).toContain('code');
    expect(table.textContent).toContain('http');
  });

  it('re-fetches when flowId changes', async () => {
    mockEstimateFlowCost.mockResolvedValue(SAMPLE_ESTIMATE);
    const { rerender } = render(<CostEstimator flowId="flow-1" />);
    await waitFor(() => {
      expect(mockEstimateFlowCost).toHaveBeenCalledTimes(1);
    });

    rerender(<CostEstimator flowId="flow-2" />);
    await waitFor(() => {
      expect(mockEstimateFlowCost).toHaveBeenCalledTimes(2);
    });
    expect(mockEstimateFlowCost).toHaveBeenLastCalledWith('flow-2', undefined);
  });

  it('error state shown on API failure', async () => {
    mockEstimateFlowCost.mockRejectedValue(new Error('Network error'));
    render(<CostEstimator flowId="flow-1" />);
    await waitFor(() => {
      expect(screen.getByText('Cost estimate unavailable')).toBeTruthy();
    });
  });

  it('shows $0.0000 for free workflows', async () => {
    mockEstimateFlowCost.mockResolvedValue(FREE_ESTIMATE);
    render(<CostEstimator flowId="flow-free" />);
    await waitFor(() => {
      expect(screen.getByTestId('cost-estimate-total')).toBeTruthy();
    });
    expect(screen.getByTestId('cost-estimate-total').textContent).toContain('$0.0000');
  });

  it('foreachIterations prop passed to API', async () => {
    mockEstimateFlowCost.mockResolvedValue(SAMPLE_ESTIMATE);
    render(<CostEstimator flowId="flow-1" foreachIterations={25} />);
    await waitFor(() => {
      expect(mockEstimateFlowCost).toHaveBeenCalledWith('flow-1', 25);
    });
  });
});
