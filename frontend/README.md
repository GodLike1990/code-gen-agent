# Code Gen Agent — Frontend

React + TypeScript UI for the Code Gen Agent backend.

## Stack

- **React 18** + **TypeScript 5** + **Vite 5**
- **Ant Design 5** for components
- **ReactFlow 11** for live graph visualisation
- **Zustand** (with `persist`) for session state
- **Monaco Editor** for the HITL patch editor
- **@ant-design/charts** for usage charts

## Directory Layout

```
frontend/src/
├── api/            # Backend client (fetch + SSE parser) and TS types
├── store/          # Zustand session store (threadId, events, run state, …)
├── components/     # Layout, graph canvas, code viewer, timeline bubbles, …
└── pages/          # One file per route
    ├── RequirementPage.tsx    # intake, clarify Q&A, HITL editor, file preview
    ├── GraphPage.tsx          # live topology with per-node status
    ├── HistoryPage.tsx        # past sessions (reads /agent/history)
    └── ObservabilityPage.tsx  # logs, usage charts, embedded LangSmith
```

## Pages

- `/requirement` — submit a requirement, stream timeline events, answer
  clarify questions inline, edit / retry / abort at HITL checkpoints, preview
  generated files and download the ZIP when done.
- `/graph` — ReactFlow diagram of the graph topology; nodes light up as they
  execute on the backend.
- `/history` — rows of `data/requests/{tid}.json`; click one to restore the
  session (the backend checkpointer replays saved state).
- `/observability` — merged memory + disk logs, token / cost breakdown, and
  an embedded LangSmith pane when `ENABLE_LANGSMITH=true` on the backend.

## Dev / Build

```bash
cd frontend
npm install
npm run dev      # Vite dev server on http://localhost:5173
npm run build    # production bundle into dist/
npm run preview  # serve the built bundle locally
```

The dev server proxies `/agent/*` to the backend on `:8000` (see
`vite.config.ts`), so no extra env vars are required during development.

## Session Persistence

The Zustand store persists the minimum required to recover an in-flight
session on reload (`threadId`, `runStatus`, `hitlPayload`, `clarifyPayload`,
`latestState`, `usage`). The streaming event buffer is deliberately **not**
persisted. A global poll in `Layout.tsx` calls `GET /agent/runs/{id}/interrupt`
so a user who refreshes the tab is pulled back to answer pending input.
