export type StatusLabel = string;

export interface Task {
  id: string;
  title: string;
  goal: string;
  workspace: string;
  status: string;
  status_label: string;
  progress: number;
  priority: string;
  owner: string;
  created_at: string;
  updated_at: string;
  run_id: string | null;
  steps: string;
}

export interface Step {
  id: number;
  seq: number;
  agent: string;
  title: string;
  tool: string;
  args: Record<string, unknown>;
  status: string;
  status_label: string;
  output: string | null;
  duration_ms: number;
  started_at: string | null;
}

export interface Deliverable {
  filename: string;
  size: number;
  sha256: string;
  path: string;
}

export interface Approval {
  id: string;
  run_id: string;
  task_id: string;
  task_title: string;
  step_seq: number;
  risk: 'high' | 'mid' | 'low';
  action: string;
  summary: string;
  detail: Record<string, string>;
  status: string;
  note: string | null;
  decided_by: string | null;
  created_at: string;
  decided_at: string | null;
  wait_seconds: number;
}

export interface DagNode {
  key: string;
  seq: number;
  title: string;
  agent: string;
  tool: string;
  skill: string | null;
  depends_on: string[];
}

export interface DagInfo {
  nodes: DagNode[];
  edges: { from: string; to: string }[];
  topo_order: string[];
  cyclic: boolean;
  parallel_width: number;
}

export interface RunDetail {
  id: string;
  task_id: string;
  status: string;
  status_label: string;
  total_steps: number;
  done_steps: number;
  tool_calls: number;
  slots_used: number;
  slots_total: number;
  pending_approval_id: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  steps: Step[];
  task: Task | null;
  dag: DagInfo | null;
  events: { seq: number; type: string; payload: Record<string, unknown>; at: string }[];
  deliverables: Deliverable[];
  pending_approval: Approval | null;
}

export interface Conversation {
  id: string;
  title: string;
  workspace: string;
  subtitle: string;
  unread: number;
  preview: string;
  updated_at: string;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant' | 'system';
  agent: string;
  content: string;
  run_id: string | null;
  attachment: { filename?: string; size?: string; note?: string } | null;
  created_at: string;
}

export interface Provider {
  id: string;
  name: string;
  provider: string;
  model: string;
  base_url: string;
  has_key: boolean;
  key_hint: string;
  is_default: boolean;
  enabled: boolean;
}

export interface Tool {
  name: string;
  label: string;
  risk: 'high' | 'mid' | 'low';
  whitelist: string[];
}
