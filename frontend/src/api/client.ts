import { AgentStateSnapshot, GraphSchema, InterruptResponse, LogsResponse, RequirementRecord, UsageSnapshot } from './types';
import { readSse, SseEvent } from './sse';

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

  /** POST to start or resume a run; returns immediately with {thread_id, status}. */
  createRun: (user_input: string, thread_id?: string) =>
    req<{ thread_id: string; status: string }>('/agent/runs', {
      method: 'POST',
      body: JSON.stringify({ user_input, thread_id }),
    }),

  /** POST to resume an interrupted run; returns immediately with {thread_id, status}. */
  resume: (tid: string, human_feedback: unknown) =>
    req<{ thread_id: string; status: string }>(`/agent/runs/${tid}/resume`, {
      method: 'POST',
      body: JSON.stringify({ human_feedback }),
    }),

  /**
   * Subscribe to the SSE event stream for a running thread.
   * Replays buffered frames from the ring buffer first, then delivers live frames.
   * The returned async iterable can be iterated with `for await`.
   */
  subscribeEvents: async function* (tid: string): AsyncIterable<SseEvent> {
    const res = await fetch(`/agent/runs/${tid}/events`, {
      headers: { Accept: 'text/event-stream' },
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
    yield* readSse(res);
  },
};
