// Shared types that mirror backend schemas.

export interface CheckIssue {
  file: string;
  line: number;
  severity: 'info' | 'warn' | 'error';
  message: string;
  code?: string;
}

export interface CheckResult {
  name: string;
  passed: boolean;
  severity: 'info' | 'warn' | 'error';
  issues: CheckIssue[];
  raw_output: string;
}

export interface AgentStateSnapshot {
  values: {
    user_input?: string;
    intent?: { type: string; summary: string; confidence: number; missing_info: string[] };
    clarifications?: { question: string; answer: string }[];
    clarify_questions?: string[];
    language?: string;
    tasks?: { path: string; purpose: string; deps: string[]; acceptance: string }[];
    generated_files?: Record<string, string>;
    check_results?: Record<string, CheckResult>;
    repair_attempts?: number;
    max_repairs?: number;
    escalated?: boolean;
    hitl_decision?: unknown;
    verify_result?: {
      passed: boolean;
      reasoning?: string;
      gaps?: string[];
      ts?: number;
    } | null;
    artifact?: {
      zip_path: string | null;
      size_bytes: number;
      file_count: number;
      created_at: number;
      reason?: string;
    } | null;
  };
  next: string[];
  langsmith_url: string | null;
}

export interface GraphSchema {
  nodes: { id: string; label: string }[];
  edges: { source: string; target: string; label?: string }[];
}

export interface UsageSnapshot {
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  by_model: Record<
    string,
    {
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      calls: number;
      cost_usd: number;
    }
  >;
}

export interface LogEntry {
  ts: number;
  level: string;
  logger: string;
  message: string;
  node?: string | null;
  duration_ms?: number | null;
  event?: string | null;
}

export type LogSource = 'memory' | 'disk' | 'merged';

export interface LogsResponse {
  thread_id: string;
  source: LogSource;
  logs: LogEntry[];
}

export interface RequirementRecord {
  thread_id: string;
  created_at: string;
  updated_at: string;
  request: string;
  status: 'running' | 'done' | 'aborted' | 'failed' | 'interrupted' | 'cancelled';
  summary: string | null;
}

export type InterruptResponse =
  | { pending: false; thread_id: string }
  | { pending: true; type: 'hitl'; thread_id: string; summary: {
      attempts?: number;
      failed_checks?: string[];
      files?: string[];
      history?: unknown[];
    } }
  | { pending: true; type: 'clarify'; thread_id: string; questions: string[] };

export type AgentEvent =
  | { type: 'node:intent' | string; thread_id: string; node?: string; [k: string]: unknown }
  | { type: 'file_generated'; thread_id: string; path: string }
  | { type: 'check_report'; thread_id: string; passed: boolean; summary: Record<string, boolean> }
  | { type: 'repair'; thread_id: string; attempt: number; action: string; reasoning: string }
  | { type: 'clarify'; questions: string[]; intent: unknown }
  | { type: 'hitl'; summary: unknown }
  | { type: 'done' }
  | { type: 'error'; message: string };
