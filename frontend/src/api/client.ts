import { AgentStateSnapshot, GraphSchema, InterruptResponse, LogsResponse, RequirementRecord, UsageSnapshot } from './types';

const BASE = '';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json();
}

export const api = {
  graphSchema: () => req<GraphSchema>('/agent/graph/schema'),
  listHistory: () => req<{ items: RequirementRecord[] }>('/agent/history'),
  getHistory: (tid: string) => req<RequirementRecord>(`/agent/history/${tid}`),
  getState: (tid: string) => req<AgentStateSnapshot>(`/agent/runs/${tid}/state`),
  getLogs: (tid: string) => req<LogsResponse>(`/agent/runs/${tid}/logs`),
  getInterrupt: (tid: string) => req<InterruptResponse>(`/agent/runs/${tid}/interrupt`),
  downloadUrl: (tid: string) => `/agent/runs/${tid}/download`,
  getUsage: (tid: string) =>
    req<{ thread_id: string; usage: UsageSnapshot }>(`/agent/runs/${tid}/usage`),
  resume: (tid: string, human_feedback: unknown) =>
    fetch(`/agent/runs/${tid}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ human_feedback }),
    }),
  createRun: (user_input: string, thread_id?: string) =>
    fetch('/agent/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_input, thread_id }),
    }),
};
