import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { AgentStateSnapshot, UsageSnapshot } from '../api/types';

export interface TimelineEvent {
  ts: number;
  event: string;
  data: unknown;
}

export type RunStatus = 'idle' | 'running' | 'done' | 'failed' | 'hitl';

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
      // Don't persist the streaming `events` buffer (can be huge);
      // keep only the bits needed to re-enter the session on refresh.
      // hitlPayload / clarifyPayload MUST survive reload so the user can
      // still submit a decision after navigating away or refreshing.
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
