/**
 * Type definitions for SynApps MVP
 */

export interface FlowNode {
  id: string;
  type: string;
  position: {
    x: number;
    y: number;
  };
  data: Record<string, any>;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  animated?: boolean;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

export interface Flow {
  id: string;
  name: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface WorkflowRunStatus {
  run_id: string;
  flow_id: string;
  status: 'running' | 'success' | 'error';
  current_applet?: string;
  progress: number;
  total_steps: number;
  start_time: number;
  end_time?: number;
  results: Record<string, any>;
  error?: string;
  completed_applets?: string[];
  input_data?: Record<string, any>;
}

export interface AppletMetadata {
  type: string;
  name: string;
  description: string;
  version: string;
  capabilities: string[];
}

export interface FlowTemplate {
  id: string;
  name: string;
  description: string;
  tags: string[];
  flow: Flow;
}

export interface WebSocketMessage {
  type: string;
  data: any;
}

export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  type: 'info' | 'success' | 'error' | 'warning';
  timestamp: number;
  read: boolean;
}

export interface CodeSuggestionRequest {
  code: string;
  hint: string;
}

export interface CodeSuggestionResponse {
  original: string;
  suggestion: string;
  diff: string;
}

// ── Auth ────────────────────────────────────────────────────────────────

export interface AuthCredentials {
  email: string;
  password: string;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  access_expires_in: number;
  refresh_expires_in: number;
}

export interface UserProfile {
  id: string;
  email: string;
  is_active: boolean;
  created_at: number;
}

// ── Workflow Versioning + Diff ────────────────────────────────────────

export interface FlowVersion {
  version_id: string;
  flow_id: string;
  version: number;
  snapshotted_at: string;
}

export interface FlowVersionDetail extends FlowVersion {
  snapshot: {
    nodes: any[];
    edges: any[];
    name?: string;
  };
}

export interface FlowDiffResult {
  nodes_added: string[];
  nodes_removed: string[];
  nodes_changed: string[];
  edges_added: string[];
  edges_removed: string[];
  summary: {
    nodes_added: number;
    nodes_removed: number;
    nodes_changed: number;
    edges_added: number;
    edges_removed: number;
  };
}

// ── Cost Estimation ─────────────────────────────────────────────────────

export interface CostBreakdownItem {
  node_id: string;
  node_type: string;
  model: string;
  estimated_usd: number;
  tokens: number;
}

export interface WorkflowCostEstimate {
  flow_id: string;
  node_count: number;
  llm_node_count: number;
  http_node_count: number;
  estimated_token_input: number;
  estimated_token_output: number;
  estimated_usd: number;
  estimated_usd_formatted: string;
  confidence: 'low' | 'medium' | 'high';
  breakdown: CostBreakdownItem[];
}
