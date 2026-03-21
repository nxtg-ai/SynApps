/**
 * ApiService - Handles HTTP communication with the backend
 */
import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import {
  Flow,
  AppletMetadata,
  WorkflowRunStatus,
  CodeSuggestionRequest,
  CodeSuggestionResponse,
  WorkflowCostEstimate,
  CostEstimate,
  FlowVersion,
  FlowVersionDetail,
  FlowDiffResult,
  RollbackAuditEntry,
} from '../types';

// ── Token refresh queue ────────────────────────────────────────────────
// Prevents multiple concurrent refresh calls when several 401s fire at once.
let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

function onRefreshed(token: string) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
}

function addRefreshSubscriber(cb: (token: string) => void) {
  refreshSubscribers.push(cb);
}

class ApiService {
  private api: AxiosInstance;

  constructor() {
    const baseURL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

    this.api = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // ── Request interceptor: attach Bearer token ──────────────────────
    this.api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
      const token =
        typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // ── Response interceptor: auto-refresh on 401 ─────────────────────
    this.api.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;

          if (isRefreshing) {
            // Another refresh is in-flight – queue this request
            return new Promise((resolve) => {
              addRefreshSubscriber((newToken: string) => {
                if (originalRequest.headers) {
                  originalRequest.headers.Authorization = `Bearer ${newToken}`;
                }
                resolve(this.api(originalRequest));
              });
            });
          }

          isRefreshing = true;

          try {
            // Dynamic import to avoid circular dependency with AuthService
            const { authService } = await import('./AuthService');
            const refreshToken =
              typeof window !== 'undefined'
                ? window.localStorage.getItem('refresh_token')
                : null;

            if (!refreshToken) {
              throw new Error('No refresh token');
            }

            const tokens = await authService.refresh(refreshToken);

            // Persist new tokens
            window.localStorage.setItem('access_token', tokens.access_token);
            window.localStorage.setItem('refresh_token', tokens.refresh_token);

            isRefreshing = false;
            onRefreshed(tokens.access_token);

            // Retry the original request with the new token
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${tokens.access_token}`;
            }
            return this.api(originalRequest);
          } catch (refreshError) {
            isRefreshing = false;
            refreshSubscribers = [];

            // Clear auth state – user must log in again
            window.localStorage.removeItem('access_token');
            window.localStorage.removeItem('refresh_token');
            window.localStorage.removeItem('auth_user');

            // Redirect to login (only in browser)
            if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
              window.location.href = '/login';
            }

            return Promise.reject(refreshError);
          }
        }

        console.error('API Error:', error.response?.data || error.message);
        return Promise.reject(error);
      },
    );
  }

  /**
   * Unwrap a paginated response: { items: T[], total, ... } → T[]
   * Falls back to returning data as-is if it's already an array.
   */
  private unwrapPaginated<T>(data: T[] | { items: T[] }): T[] {
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object' && 'items' in data) return data.items;
    return [];
  }

  /**
   * Get all available applets
   */
  public async getApplets(): Promise<AppletMetadata[]> {
    const response = await this.api.get('/applets');
    return this.unwrapPaginated(response.data);
  }

  /**
   * Get all flows
   */
  public async getFlows(): Promise<Flow[]> {
    const response = await this.api.get('/flows');
    return this.unwrapPaginated(response.data);
  }

  /**
   * Get a specific flow
   */
  public async getFlow(flowId: string): Promise<Flow> {
    const response = await this.api.get(`/flows/${flowId}`);
    return response.data;
  }

  /**
   * Create or update a flow
   */
  public async saveFlow(flow: Flow): Promise<{ id: string }> {
    const response = await this.api.post('/flows', flow);
    return response.data;
  }

  /**
   * Delete a flow
   */
  public async deleteFlow(flowId: string): Promise<void> {
    await this.api.delete(`/flows/${flowId}`);
  }

  /**
   * Run a flow with the given input data
   */
  public async runFlow(flowId: string, inputData: Record<string, any>): Promise<{ run_id: string }> {
    const response = await this.api.post(`/flows/${flowId}/run`, { input: inputData });
    return response.data;
  }

  /**
   * Get all workflow runs
   */
  public async getRuns(): Promise<WorkflowRunStatus[]> {
    const response = await this.api.get('/runs');
    return this.unwrapPaginated(response.data);
  }

  /**
   * Get a specific workflow run
   */
  public async getRun(runId: string): Promise<WorkflowRunStatus> {
    const response = await this.api.get(`/runs/${runId}`);
    return response.data;
  }

  /**
   * Get AI code suggestions
   */
  public async getCodeSuggestion(request: CodeSuggestionRequest): Promise<CodeSuggestionResponse> {
    const response = await this.api.post('/ai/suggest', request);
    return response.data;
  }

  /**
   * Export a flow as JSON
   */
  public async exportFlow(flowId: string): Promise<any> {
    const response = await this.api.get(`/flows/${flowId}/export`);
    return response.data;
  }

  /**
   * Import a flow from JSON
   */
  public async importFlow(flowData: any): Promise<{ id: string }> {
    const response = await this.api.post('/flows/import', flowData);
    return response.data;
  }

  /**
   * Estimate execution cost for a workflow before running it.
   */
  public async estimateWorkflowCost(
    flowId: string,
    inputText: string = ''
  ): Promise<WorkflowCostEstimate> {
    const response = await this.api.post(`/workflows/${flowId}/estimate-cost`, {
      input_data: {},
      input_text: inputText,
    });
    return response.data;
  }

  /**
   * Estimate execution cost for a saved flow using the node-level calculator.
   */
  public async estimateFlowCost(
    flowId: string,
    foreachIterations?: number,
  ): Promise<CostEstimate> {
    const body = foreachIterations !== undefined ? { foreach_iterations: foreachIterations } : {};
    const response = await this.api.post(`/flows/${flowId}/estimate-cost`, body);
    return response.data;
  }

  /**
   * Estimate execution cost for an arbitrary list of nodes (before flow is saved).
   */
  public async estimateCost(
    nodes: Array<{ id: string; type: string }>,
    foreachIterations?: number,
  ): Promise<CostEstimate> {
    const response = await this.api.post('/flows/estimate-cost', {
      nodes,
      foreach_iterations: foreachIterations ?? 10,
    });
    return response.data;
  }

  /**
   * Trigger a replay of an execution. Returns metadata about the newly
   * created replay run so callers can track or navigate to it.
   */
  public async replayExecution(executionId: string): Promise<{
    replay_run_id: string;
    original_run_id: string;
    flow_id: string;
    status: string;
  }> {
    const response = await this.api.post(`/executions/${executionId}/replay`);
    return response.data;
  }

  /**
   * Fetch the full replay chain for an execution — the original run plus
   * every subsequent replay, ordered chronologically.
   */
  public async getReplayHistory(executionId: string): Promise<{
    execution_id: string;
    chain: string[];
    length: number;
  }> {
    const response = await this.api.get(`/executions/${executionId}/replay-history`);
    return response.data;
  }

  /**
   * List all saved snapshots for a flow, newest-first.
   */
  public async getFlowVersions(flowId: string): Promise<{ items: FlowVersion[] }> {
    const response = await this.api.get(`/flows/${flowId}/versions`);
    return response.data;
  }

  /**
   * Fetch a specific version snapshot including the full node/edge graph.
   */
  public async getFlowVersion(flowId: string, versionId: string): Promise<FlowVersionDetail> {
    const response = await this.api.get(`/flows/${flowId}/versions/${versionId}`);
    return response.data;
  }

  /**
   * Compute the diff between two versions. Pass "current" as versionB to
   * compare against the live (unsaved) flow.
   */
  public async diffFlowVersions(
    flowId: string,
    versionA: string,
    versionB: string
  ): Promise<FlowDiffResult> {
    const response = await this.api.get(`/flows/${flowId}/diff`, {
      params: { version_a: versionA, version_b: versionB },
    });
    return response.data;
  }

  /**
   * Create a new flow from a node/edge definition.
   */
  public async createFlow(data: {
    name: string;
    nodes: Array<{ id: string; type: string; position: { x: number; y: number }; data: Record<string, any> }>;
    edges: Array<{ id: string; source: string; target: string }>;
  }): Promise<{ id: string }> {
    const response = await this.api.post('/flows', data);
    return response.data;
  }

  /**
   * Update an existing flow's nodes and edges via PUT.
   */
  public async updateFlow(
    flowId: string,
    data: {
      name?: string;
      nodes: Array<{ id: string; type: string; position: { x: number; y: number }; data: Record<string, any> }>;
      edges: Array<{ id: string; source: string; target: string }>;
    },
  ): Promise<Record<string, any>> {
    const response = await this.api.put(`/flows/${flowId}`, data);
    return response.data;
  }

  /**
   * Execute a flow with the given input payload.
   */
  public async executeFlow(
    flowId: string,
    input: Record<string, any>,
  ): Promise<Record<string, any>> {
    const response = await this.api.post(`/flows/${flowId}/execute`, input);
    return response.data;
  }

  /**
   * Publish a flow to the marketplace.
   */
  public async publishToMarketplace(data: {
    flow_id: string;
    name: string;
    description: string;
    category: string;
    tags: string[];
  }): Promise<{ listing_id: string }> {
    const response = await this.api.post('/marketplace/publish', data);
    return response.data;
  }
  /**
   * Roll back a flow to a specific version snapshot.
   */
  public async rollbackFlow(
    flowId: string,
    versionId: string,
    reason: string = '',
  ): Promise<{ flow: Flow; rolled_back_to: string; audit_entry: RollbackAuditEntry }> {
    const response = await this.api.post(
      `/flows/${flowId}/rollback`,
      { reason },
      { params: { version_id: versionId } },
    );
    return response.data;
  }

  /**
   * Fetch rollback audit history for a specific flow.
   */
  public async getRollbackHistory(flowId: string): Promise<{ items: RollbackAuditEntry[] }> {
    const response = await this.api.get(`/flows/${flowId}/rollback/history`);
    return response.data;
  }

  // ── Workflow Test Runner (N-33b) ─────────────────────────────────────────

  /**
   * List all test cases for a flow.
   */
  public async getFlowTests(flowId: string): Promise<{ tests: any[]; total: number }> {
    const response = await this.api.get(`/flows/${flowId}/tests`);
    return response.data;
  }

  /**
   * Add a test case to a flow.
   */
  public async addFlowTest(
    flowId: string,
    data: {
      name: string;
      description?: string;
      input?: Record<string, any>;
      expected_output?: Record<string, any>;
      match_mode?: 'exact' | 'contains' | 'keys_present';
    },
  ): Promise<any> {
    const response = await this.api.post(`/flows/${flowId}/tests`, data);
    return response.data;
  }

  /**
   * Delete a test case from a flow.
   */
  public async deleteFlowTest(flowId: string, testId: string): Promise<void> {
    await this.api.delete(`/flows/${flowId}/tests/${testId}`);
  }

  /**
   * Run all or selected test cases for a flow.
   */
  public async runFlowTests(
    flowId: string,
    testIds?: string[],
  ): Promise<{ results: any[]; summary: any; exit_code: number }> {
    const response = await this.api.post(`/flows/${flowId}/tests/run`, {
      test_ids: testIds || [],
    });
    return response.data;
  }

  /**
   * Get test results for a flow.
   */
  public async getFlowTestResults(flowId: string): Promise<{ results: any[]; total: number }> {
    const response = await this.api.get(`/flows/${flowId}/tests/results`);
    return response.data;
  }

  /**
   * Get test suite summary for a flow.
   */
  public async getFlowTestSummary(
    flowId: string,
  ): Promise<{ total: number; passed: number; failed: number; error: number; pass_rate_pct: number }> {
    const response = await this.api.get(`/flows/${flowId}/tests/summary`);
    return response.data;
  }
}

// Create a singleton instance
export const apiService = new ApiService();
export default apiService;
