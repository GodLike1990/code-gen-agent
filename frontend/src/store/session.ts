import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { AgentStateSnapshot, UsageSnapshot } from '../api/types';

export interface TimelineEvent {
  ts: number;
  event: string;
  data: unknown;
}

/**
 * RunStatus is a superset of the backend RequirementRecord.status values.
 *
 * Backend statuses (written to RequestStore by streaming.py):
 *   running | done | aborted | failed | interrupted | cancelled
 *
 * Frontend-only additions:
 *   idle   — no run has started in this session yet
 *   hitl   — alias for backend "interrupted"; the agent is paused waiting for
 *            human input.  The mapping is applied in RequirementPage.tsx when
 *            reading RequirementRecord.status from the API:
 *              rec.status === 'interrupted'  →  setRunStatus('hitl')
 *
 * The "hitl" alias exists so UI components can use a more descriptive name
 * while the backend uses the generic LangGraph term "interrupted".
 */
export type RunStatus = 'idle' | 'running' | 'done' | 'aborted' | 'failed' | 'hitl' | 'cancelled';

export interface HitlPayload {
  thread_id?: string;
  type?: 'hitl';
  summary?: {
    attempts?: number;
    failed_checks?: string[];
    files?: string[];
    history?: unknown[];
  };
  [k: string]: unknown;
}

interface SessionState {
  threadId: string | null;
  events: TimelineEvent[];
  latestState: AgentStateSnapshot | null;
  usage: UsageSnapshot | null;
  hitlPayload: HitlPayload | null;
  clarifyPayload: { questions: string[] } | null;
  /** ms epoch when the current interrupt first arrived; null when not pending. */
  interruptedAt: number | null;
  runStatus: RunStatus;
  setThread: (id: string) => void;
  pushEvent: (e: TimelineEvent) => void;
  setState: (s: AgentStateSnapshot | null) => void;
  setUsage: (u: UsageSnapshot | null) => void;
  setHitl: (p: HitlPayload | null) => void;
  setClarify: (p: { questions: string[] } | null) => void;
  setRunStatus: (s: RunStatus) => void;
  reset: () => void;
}

export const useSession = create<SessionState>()(
  persist(
    (set, get) => ({
      threadId: null,
      events: [],
      latestState: null,
      usage: null,
      hitlPayload: null,
      clarifyPayload: null,
      interruptedAt: null,
      runStatus: 'idle',
      setThread: (id) => set({ threadId: id }),
      pushEvent: (e) => set((s) => ({ events: [...s.events, e].slice(-500) })),
      setState: (s) => set({ latestState: s }),
      setUsage: (u) => set({ usage: u }),
      setHitl: (p) =>
        set({
          hitlPayload: p,
          interruptedAt: p ? get().interruptedAt || Date.now() : null,
        }),
      setClarify: (p) =>
        set({
          clarifyPayload: p,
          interruptedAt: p ? get().interruptedAt || Date.now() : null,
        }),
      setRunStatus: (s) => set({ runStatus: s }),
      reset: () =>
        set({
          threadId: null,
          events: [],
          latestState: null,
          usage: null,
          hitlPayload: null,
          clarifyPayload: null,
          interruptedAt: null,
          runStatus: 'idle',
        }),
    }),
    {
      name: 'code-gen-agent-session',
      version: 2,
      storage: createJSONStorage(() => localStorage),
      // Identity migration: preserves current v2 behaviour explicitly so that
      // bumping `version` in the future forces us to write a real migration
      // rather than silently dropping old payloads.
      migrate: (state) => state as SessionState,
      // Selective persistence: only the fields needed to re-enter an in-flight
      // session on reload are persisted to localStorage.
      //
      // Persisted (survive reload):
      //   threadId, runStatus, hitlPayload, clarifyPayload — needed to know
      //     whether a run is active and whether user input is pending
      //   latestState, usage — last known agent state + token counts
      //   interruptedAt — used to show elapsed wait time in the HITL banner
      //
      // NOT persisted (intentionally excluded):
      //   events — the SSE event buffer can be large (up to 500 frames) and
      //     is ephemeral by nature; replaying it on reload would be misleading
      partialize: (s) => ({
        threadId: s.threadId,
        latestState: s.latestState,
        usage: s.usage,
        runStatus: s.runStatus,
        hitlPayload: s.hitlPayload,
        clarifyPayload: s.clarifyPayload,
        interruptedAt: s.interruptedAt,
      }),
    },
  ),
);
