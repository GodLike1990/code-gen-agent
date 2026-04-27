/**
 * Shared status mapping constants — single source of truth for all status
 * colors, labels, and alert types across HistoryPage, RequirementPage,
 * GraphPage, and GraphCanvas.
 *
 * STATUS LAYERS
 * ─────────────
 * 1. Backend RequestStore / SSE final_status
 *      running | done | aborted | failed | interrupted | cancelled
 *
 * 2. Frontend RunStatus (session store) — superset of backend statuses
 *      idle        – front-end only: no run has started yet
 *      running     – mirrors backend
 *      done        – mirrors backend
 *      aborted     – mirrors backend
 *      failed      – mirrors backend
 *      cancelled   – mirrors backend
 *      hitl        – front-end name for backend "interrupted" (agent paused,
 *                    waiting for human input). The mapping is applied in
 *                    RequirementPage.tsx when reading RequirementRecord.status.
 *
 * 3. Node-level status (GraphPage / GraphCanvas) — derived locally from state
 *      pending | running | paused | success | failed | interrupted | cancelled
 *    These are never persisted to the backend; derived from LangGraph state
 *    snapshots + live SSE events.
 */

// ---------------------------------------------------------------------------
// Run-level status — used by HistoryPage Tag, RequirementPage Alert
// Values are Ant Design Tag `color` presets.
// Keys cover backend RequirementRecord.status values.
// ---------------------------------------------------------------------------

export const RUN_STATUS_COLOR: Record<string, string> = {
  running:     'processing',
  done:        'success',
  aborted:     'warning',
  failed:      'error',
  interrupted: 'orange',   // backend "interrupted" → HITL pause
  cancelled:   'default',
};

export const RUN_STATUS_LABEL: Record<string, string> = {
  running:     'Running',
  done:        'Completed',
  aborted:     'Aborted',
  failed:      'Failed',
  interrupted: 'Interrupted',
  cancelled:   'Cancelled',
};

// Alert `type` prop mapping for RequirementPage status banner.
// Covers both backend statuses (interrupted) and frontend-only statuses
// (idle, hitl) since RunStatus is a superset.
export const RUN_STATUS_ALERT: Record<string, 'success' | 'info' | 'warning' | 'error'> = {
  idle:        'info',
  running:     'info',
  done:        'success',
  hitl:        'warning',      // front-end name for "interrupted"
  interrupted: 'warning',      // backend name for HITL pause (same colour)
  aborted:     'warning',
  cancelled:   'warning',
  failed:      'error',
};

// ---------------------------------------------------------------------------
// Node-level status (GraphCanvas nodeStatus)
// Values are CSS hex / colour strings for inline styles.
// ---------------------------------------------------------------------------

export const NODE_STATUS_COLOR: Record<string, string> = {
  pending:     '#d9d9d9',
  running:     '#1677ff',
  paused:      '#9ca3af',
  success:     '#52c41a',
  failed:      '#ff4d4f',
  interrupted: '#faad14',
  cancelled:   '#9ca3af',
};

export const NODE_STATUS_LABEL: Record<string, string> = {
  pending:     'Pending',
  running:     'Running',
  paused:      'Paused',
  success:     'Success',
  failed:      'Failed',
  interrupted: 'Interrupted',
  cancelled:   'Cancelled',
};
