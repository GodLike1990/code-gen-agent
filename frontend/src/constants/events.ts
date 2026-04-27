/**
 * SSE event type strings emitted by the backend streaming.py.
 *
 * BACKEND CONTRACT
 * ─────────────────
 * These values must stay in sync with EVENT_* constants in:
 *   backend/code_gen_agent/graph/constants.py
 *
 * SSE frame shape: { event: SseEventType, data: JSON string }
 *
 * Key events and their data shapes:
 *   state_delta   — { thread_id, node }                triggers a state + usage poll
 *   clarify       — { thread_id, node, type, questions, ... }
 *   hitl          — { thread_id, node, type, summary, ... }
 *   interrupt     — { thread_id, node, type, ... }      generic interrupt fallback
 *   hitl_decision — { thread_id, node, type, action }   user's HITL decision recorded
 *   done          — { final_status }                    run finished; check final_status
 *   error         — { thread_id, error_type, message, last_node }
 *   node:<name>   — emitted by BaseNode on enter/exit; e.g. "node:intent"
 */

export const SSE_EVENT = {
  STATE_DELTA:   'state_delta',
  INTERRUPT:     'interrupt',
  CLARIFY:       'clarify',
  HITL:          'hitl',
  HITL_DECISION: 'hitl_decision',
  DONE:          'done',
  ERROR:         'error',
  /** Node-level events use this prefix + node name, e.g. "node:intent" */
  NODE_PREFIX:   'node:',
} as const;

export type SseEventType = typeof SSE_EVENT[keyof typeof SSE_EVENT];
