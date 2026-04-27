import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Radio,
  Space,
  Spin,
  Statistic,
  Row,
  Col,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../store/session';
import { api } from '../api/client';
import { RequirementRecord } from '../api/types';
import { RUN_STATUS_ALERT } from '../constants/status';
import { SSE_EVENT } from '../constants/events';
import EventTimeline from '../components/EventTimeline';
import FileTree from '../components/FileTree';
import CodeViewer from '../components/CodeViewer';
import CheckReport from '../components/CheckReport';

type HitlAction = 'retry' | 'patch' | 'abort';

const ACTION_HELP: Record<HitlAction, string> = {
  retry:
    'Agent re-runs the failing node with the hint you provide. Use this when the model just needs more context.',
  patch:
    'You manually edit the generated files below. On submit the agent re-runs the checks against your edits.',
  abort: 'Stop the run and keep current state. No more repair attempts.',
};

const ACTION_NEXT: Record<HitlAction, string> = {
  retry: 'Graph resumes at the repair node; a new attempt starts with your hint.',
  patch: 'Files you edited overwrite generated files; checks re-run on the new content.',
  abort: 'Run status becomes "aborted" — run stops immediately, no artifact produced.',
};

type Bubble =
  | { role: 'user'; text: string; ts: number }
  | { role: 'agent'; kind: 'clarify'; questions: string[]; ts: number }
  | { role: 'agent'; kind: 'hitl'; summary: any; ts: number }
  | { role: 'agent'; kind: 'verify'; passed: boolean; reasoning: string; gaps: string[]; ts: number };

function useElapsedSeconds(ts: number | null) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (!ts) return;
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [ts]);
  if (!ts) return null;
  const secs = Math.floor((Date.now() - ts) / 1000);
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export default function RequirementPage() {
  const [form] = Form.useForm();
  const [clarifyForm] = Form.useForm();
  const nav = useNavigate();
  const [loading, setLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [historyRec, setHistoryRec] = useState<RequirementRecord | null>(null);
  const [action, setAction] = useState<HitlAction>('retry');
  const [hint, setHint] = useState('');
  const [editedFiles, setEditedFiles] = useState<Record<string, string>>({});
  const {
    threadId,
    setThread,
    pushEvent,
    setState,
    setUsage,
    setHitl,
    setClarify,
    clarifyPayload,
    hitlPayload,
    latestState,
    usage,
    runStatus,
    interruptedAt,
    events,
    setRunStatus,
    reset,
  } = useSession();

  const elapsed = useElapsedSeconds(interruptedAt);

  // ---- mount / threadId reconciliation ----
  useEffect(() => {
    if (!threadId) {
      setHistoryRec(null);
      if (useSession.getState().runStatus !== 'idle') setRunStatus('idle');
      return;
    }
    if (useSession.getState().runStatus === 'running') setRunStatus('idle');
    let cancelled = false;
    (async () => {
      try {
        const rec = await api.getHistory(threadId);
        if (cancelled) return;
        setHistoryRec(rec);
        if (rec.status === 'done') setRunStatus('done');
        else if (rec.status === 'aborted') setRunStatus('aborted');
        else if (rec.status === 'failed') setRunStatus('failed');
        else if (rec.status === 'cancelled') setRunStatus('cancelled');
        else if (rec.status === 'interrupted') setRunStatus('hitl');
        else if (rec.status === 'running') setRunStatus('running');
      } catch {
        if (!cancelled) setHistoryRec(null);
      }

      // Recover pending interrupt from server if we have no local payload.
      const s = useSession.getState();
      if (!s.hitlPayload && !s.clarifyPayload) {
        try {
          const itp = await api.getInterrupt(threadId);
          if (cancelled || !itp.pending) return;
          if (itp.type === 'clarify') {
            setClarify({ questions: itp.questions });
          } else if (itp.type === 'hitl') {
            setHitl({ thread_id: itp.thread_id, type: 'hitl', summary: itp.summary });
            setRunStatus('hitl');
          }
        } catch {
          /* 404 = no pending interrupt — ignore */
        }
      }

      // Always refresh the authoritative state & usage on mount. The persisted
      // `latestState` can be stale (last snapshot happened before submit
      // finished), and the Conversation view relies on
      // `state.values.clarifications` / `hitl_decision` to reconstruct prior
      // turns after a refresh.
      try {
        const snap = await api.getState(threadId);
        if (!cancelled) setState(snap);
        const u = await api.getUsage(threadId);
        if (!cancelled) setUsage(u.usage);
      } catch {
        /* thread gone on backend */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  // ---- conversation thread derivation ----
  // Every bubble carries an absolute ms timestamp. We collect from several
  // sources (seed, live events, refresh-time payload fallbacks) and finally
  // sort by ts — that guarantees chronological order regardless of which
  // source each bubble came from. Role (user/agent) is a visual hint only,
  // NEVER a grouping key.
  const bubbles = useMemo<Bubble[]>(() => {
    const out: Bubble[] = [];
    const seedText = historyRec?.request || latestState?.values.user_input;
    const seedTs = historyRec?.created_at ? Date.parse(historyRec.created_at) : 0;
    if (seedText) out.push({ role: 'user', text: seedText, ts: seedTs || 1 });

    // (a) Authoritative: pull completed Q+A rounds from the checkpointer'ed
    // state. `clarifications` is written by the clarify node AFTER the user
    // answers, so it survives a browser refresh. We don't have per-pair
    // timestamps so we synthesize monotonically after the seed.
    const clars = (latestState?.values.clarifications || []) as {
      question: string;
      answer: string;
    }[];
    const base = (seedTs || 1) + 1;
    clars.forEach((c, idx) => {
      const t = base + idx * 2;
      out.push({ role: 'agent', kind: 'clarify', questions: [c.question], ts: t });
      out.push({ role: 'user', text: c.answer || '(empty)', ts: t + 1 });
    });

    // HITL decision also persists on state.values.hitl_decision.
    const decision = latestState?.values.hitl_decision as
      | { action?: string; hint?: string; files?: Record<string, string> }
      | undefined;
    let decisionTs: number | null = null;
    if (decision && decision.action) {
      decisionTs = base + clars.length * 2 + 1;
      const text =
        decision.action === 'patch'
          ? `patch (${Object.keys(decision.files || {}).length} files${
              decision.hint ? `, note: ${decision.hint}` : ''
            })`
          : `${decision.action}${decision.hint ? ` (${decision.hint})` : ''}`;
      out.push({ role: 'user', text, ts: decisionTs });
    }

    // Verify result — persisted in state, show as agent bubble.
    const vr = latestState?.values.verify_result;
    if (vr) {
      const ts = vr.ts || base + clars.length * 2 + 2;
      out.push({
        role: 'agent',
        kind: 'verify',
        passed: !!vr.passed,
        reasoning: vr.reasoning || '',
        gaps: vr.gaps || [],
        ts,
      });
    }

    // (b) Live SSE events — may duplicate (a); de-dupe by question text and
    // by answer substring.
    const seenQs = new Set(clars.map((c) => c.question));
    for (const e of events) {
      const d = e.data as any;
      if (e.event === 'clarify') {
        const qs = (d?.questions || []) as string[];
        const fresh = qs.filter((q) => !seenQs.has(q));
        if (fresh.length) {
          out.push({ role: 'agent', kind: 'clarify', questions: fresh, ts: e.ts });
          fresh.forEach((q) => seenQs.add(q));
        }
      } else if (e.event === 'hitl' || e.event === 'interrupt') {
        if (!decision) out.push({ role: 'agent', kind: 'hitl', summary: d?.summary || d, ts: e.ts });
      } else if (e.event === 'clarify_answers_submitted') {
        const txt = d?.text || '';
        const already = clars.some((c) => c.answer && txt.includes(c.answer));
        if (!already) out.push({ role: 'user', text: txt || '(answers)', ts: e.ts });
      } else if (e.event === 'hitl_decision_submitted') {
        if (!decision) out.push({ role: 'user', text: d?.text || '(decision)', ts: e.ts });
      } else if (e.event === 'verify') {
        // Only add if state-derived bubble isn't already present.
        if (!vr) {
          out.push({
            role: 'agent',
            kind: 'verify',
            passed: !!d?.passed,
            reasoning: d?.reasoning || '',
            gaps: d?.gaps || [],
            ts: e.ts,
          });
        }
      }
    }

    // (c) Refresh-time fallback: still-pending interrupt with no live event.
    const anchorTs = interruptedAt || Date.now();
    const hasClarifyBubble = out.some(
      (b) => b.role === 'agent' && 'kind' in b && b.kind === 'clarify',
    );
    if (clarifyPayload) {
      const fresh = clarifyPayload.questions.filter((q) => !seenQs.has(q));
      if (fresh.length && !hasClarifyBubble) {
        out.push({ role: 'agent', kind: 'clarify', questions: fresh, ts: anchorTs });
      }
    }
    const hasHitlBubble = out.some((b) => b.role === 'agent' && 'kind' in b && b.kind === 'hitl');
    if (hitlPayload && !hasHitlBubble && !decision) {
      out.push({
        role: 'agent',
        kind: 'hitl',
        summary: (hitlPayload as any)?.summary || hitlPayload,
        ts: anchorTs,
      });
    }

    // Strict chronological sort. Index is tiebreaker for stable order.
    return out
      .map((b, i) => ({ b, i }))
      .sort((a, z) => a.b.ts - z.b.ts || a.i - z.i)
      .map((x) => x.b);
  }, [events, historyRec, latestState, clarifyPayload, hitlPayload, interruptedAt]);

  // ---- SSE consumer ----
  // Iterates over the async generator from api.subscribeEvents() and dispatches
  // each frame to the appropriate state updater.
  //
  // Frame types and their handling:
  //   error         → setRunStatus('failed') + toast
  //   clarify       → setClarify() to show the Q&A form
  //   hitl/interrupt → setHitl() + setRunStatus('hitl') to show HITL form
  //   done          → read final_status from payload; 'aborted' or 'done'
  //   state_delta   → poll getState() + getUsage() for fresh snapshot
  const consumeEvents = async (tid: string) => {
    for await (const ev of api.subscribeEvents(tid)) {
      pushEvent({ ts: Date.now(), event: ev.event, data: ev.data });
      const data = ev.data as any;
      if (ev.event === SSE_EVENT.ERROR || data?.type === SSE_EVENT.ERROR) {
        setRunStatus('failed');
        const msg = data?.error_type
          ? `${data.error_type}: ${data.message}`
          : data?.message || 'Unknown error';
        message.error(msg.length > 200 ? msg.slice(0, 200) + '…' : msg, 6);
      }
      if (ev.event === SSE_EVENT.CLARIFY || data?.type === SSE_EVENT.CLARIFY) {
        setClarify({ questions: (data?.questions || []) as string[] });
      }
      if (ev.event === SSE_EVENT.HITL || data?.type === SSE_EVENT.HITL || ev.event === SSE_EVENT.INTERRUPT) {
        setHitl(data);
        setRunStatus('hitl');
      }
      if (ev.event === SSE_EVENT.DONE) {
        // The "done" frame carries final_status so the frontend can distinguish
        // normal completion ("done") from user abort ("aborted") without polling.
        const cur = useSession.getState().runStatus;
        const finalStatus = (ev.data as any)?.final_status;
        if (finalStatus === 'aborted') {
          setRunStatus('aborted');
        } else if (cur === 'running' || cur === 'idle') {
          setRunStatus('done');
        }
      }
      if (ev.event === SSE_EVENT.STATE_DELTA && data?.thread_id) {
        if (useSession.getState().runStatus === 'idle') setRunStatus('running');
        try {
          const snap = await api.getState(data.thread_id);
          setState(snap);
          const u = await api.getUsage(data.thread_id);
          setUsage(u.usage);
        } catch {
          /* ignore mid-stream errors */
        }
      }
    }
  };

  // ---- auto-reconnect on mount if a run is live ----
  useEffect(() => {
    const s = useSession.getState();
    if (!s.threadId || s.runStatus !== 'running') return;
    let cancelled = false;
    setLoading(true);
    consumeEvents(s.threadId)
      .catch(() => {
        if (!cancelled) setRunStatus('failed');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- submissions ----
  const onSubmitFresh = async (values: any) => {
    reset();
    const tid =
      't-' +
      (crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)).replace(/-/g, '').slice(0, 12);
    setThread(tid);
    setRunStatus('running');
    setLoading(true);
    try {
      await api.createRun(values.user_input, tid);
      await consumeEvents(tid);
    } catch (e: any) {
      setRunStatus('failed');
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const onSubmitClarify = async (values: any) => {
    if (!threadId) return;
    const answers = values.answers || [];
    const text = (clarifyPayload?.questions || [])
      .map((q, i) => `${q}\n  → ${answers[i] || ''}`)
      .join('\n');
    pushEvent({ ts: Date.now(), event: 'clarify_answers_submitted', data: { text } });
    setClarify(null);
    setRunStatus('running');
    setLoading(true);
    try {
      await api.resume(threadId, { answers });
      await consumeEvents(threadId);
    } catch (e: any) {
      setRunStatus('failed');
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const onSubmitHitl = async () => {
    if (!threadId) return;
    const payload: any = { action, hint };
    if (action === 'patch') payload.files = editedFiles;
    const text =
      action === 'retry'
        ? `retry${hint ? ` (hint: ${hint})` : ''}`
        : action === 'patch'
        ? `patch (${Object.keys(editedFiles).length} files${hint ? `, note: ${hint}` : ''})`
        : `abort${hint ? ` (reason: ${hint})` : ''}`;
    pushEvent({ ts: Date.now(), event: 'hitl_decision_submitted', data: { text } });
    setHitl(null);
    setEditedFiles({});
    setHint('');
    setAction('retry');
    setRunStatus(action === 'abort' ? 'cancelled' : 'running');
    setLoading(true);
    try {
      await api.resume(threadId, payload);
      await consumeEvents(threadId);
    } catch (e: any) {
      setRunStatus('failed');
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  // ---- files for composer (merged with in-progress HITL patches) ----
  const stateFiles = latestState?.values.generated_files || {};
  const files = { ...stateFiles, ...editedFiles };
  const checks = latestState?.values.check_results || {};

  // ---- composer mode ----
  type Mode = 'fresh' | 'waiting' | 'clarify' | 'hitl' | 'finished' | 'aborted' | 'failed';
  const mode: Mode =
    clarifyPayload
      ? 'clarify'
      : hitlPayload || runStatus === 'hitl'
      ? 'hitl'
      : runStatus === 'running'
      ? 'waiting'
      : runStatus === 'done'
      ? 'finished'
      : runStatus === 'aborted'
      ? 'aborted'
      : runStatus === 'failed'
      ? 'failed'
      : 'fresh';

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="How this page works"
        description={
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>
              One page for the whole conversation: your initial requirement, the agent's
              clarification questions, and any Human-in-the-loop decisions all happen in the
              composer below.
            </li>
            <li>
              The <b>node graph</b> and per-node execution status live on the{' '}
              <a onClick={() => nav('/graph')}>Graph</a> page.
            </li>
            <li>
              When the agent needs your input, we'll automatically bring you back here — even
              if you navigated to Graph or Observability.
            </li>
          </ul>
        }
      />

      {runStatus !== 'idle' && (
        <Alert
          type={RUN_STATUS_ALERT[runStatus] ?? 'info'}
          showIcon
          message={
            runStatus === 'running'
              ? `Running${
                  latestState?.next?.[0] ? ` — current node: ${latestState.next[0]}` : '…'
                }`
              : runStatus === 'done'
              ? 'Run completed successfully'
              : runStatus === 'hitl'
              ? `Waiting for your input${elapsed ? ` · ${elapsed}` : ''}`
              : runStatus === 'aborted'
              ? 'Run aborted by user — no artifact was produced'
              : runStatus === 'cancelled'
              ? `Run cancelled (client disconnected)${
                  latestState?.next?.[0] ? ` — paused at: ${latestState.next[0]}` : ''
                }`
              : 'Run failed'
          }
          description={
            threadId ? (
              <span>
                thread <Typography.Text code>{threadId}</Typography.Text>
              </span>
            ) : null
          }
          action={
            <Space>
              <Button
                size="small"
                type="primary"
                ghost={runStatus === 'running' || runStatus === 'done'}
                danger={runStatus === 'failed'}
                onClick={() => nav('/graph')}
              >
                Open Graph
              </Button>
              {runStatus !== 'running' && (
                <Button
                  size="small"
                  danger
                  onClick={() => {
                    reset();
                    setHistoryRec(null);
                    form.resetFields();
                  }}
                >
                  New Session
                </Button>
              )}
            </Space>
          }
        />
      )}

      <Card
        title="Conversation"
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Requirement · clarifications · HITL decisions — in submission order.
          </Typography.Text>
        }
      >
        {bubbles.length === 0 ? (
          <Typography.Text type="secondary">
            Start a new requirement below to begin.
          </Typography.Text>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {bubbles.map((b, i) => (
              <div
                key={i}
                style={{
                  alignSelf: b.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  background: b.role === 'user' ? '#e6f4ff' : '#fafafa',
                  border: '1px solid',
                  borderColor: b.role === 'user' ? '#91caff' : '#eee',
                  borderRadius: 8,
                  padding: '8px 12px',
                  fontSize: 13,
                }}
              >
                <div style={{ color: '#999', fontSize: 11, marginBottom: 4 }}>
                  #{i + 1} · {b.role === 'user' ? 'You' : 'Agent'}
                  {'kind' in b ? ` · ${b.kind}` : ''}
                  {b.ts ? ` · ${new Date(b.ts).toLocaleTimeString()}` : ''}
                </div>
                {b.role === 'user' ? (
                  <div style={{ whiteSpace: 'pre-wrap' }}>{b.text}</div>
                ) : b.kind === 'clarify' ? (
                  <div>
                    <div style={{ marginBottom: 4 }}>I need a bit more info:</div>
                    <ul style={{ margin: 0, paddingLeft: 20 }}>
                      {b.questions.map((q, j) => (
                        <li key={j}>{q}</li>
                      ))}
                    </ul>
                  </div>
                ) : b.kind === 'verify' ? (
                  <div>
                    <div style={{ marginBottom: 4 }}>
                      <Tag color={b.passed ? 'green' : 'orange'}>
                        {b.passed ? 'Verified' : 'Gaps flagged'}
                      </Tag>
                      Requirement acceptance review
                    </div>
                    {b.reasoning && (
                      <div style={{ fontSize: 12, color: '#555', marginBottom: 4 }}>
                        {b.reasoning}
                      </div>
                    )}
                    {b.gaps.length > 0 && (
                      <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, color: '#b45309' }}>
                        {b.gaps.map((g, j) => (
                          <li key={j}>{g}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : (
                  <div>
                    <div style={{ marginBottom: 4 }}>
                      Automatic repair exhausted. Human decision required.
                    </div>
                    <div style={{ fontSize: 12, color: '#555' }}>
                      <div>Attempts: {b.summary?.attempts ?? '?'}</div>
                      <div>
                        Failed checks:{' '}
                        {(b.summary?.failed_checks || []).map((c: string) => (
                          <Tag key={c} color="red">
                            {c}
                          </Tag>
                        )) || 'none'}
                      </div>
                      <div>Files: {(b.summary?.files || []).length}</div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card
        title={
          mode === 'fresh'
            ? 'New Requirement'
            : mode === 'waiting'
            ? 'Composer (agent is working…)'
            : mode === 'clarify'
            ? 'Answer the agent'
            : mode === 'hitl'
            ? 'Your decision'
            : mode === 'finished'
            ? 'Run completed'
            : mode === 'aborted'
            ? 'Run aborted'
            : 'Run failed'
        }
      >
        {mode === 'fresh' && (
          <Form form={form} onFinish={onSubmitFresh} layout="vertical">
            <Form.Item
              label="Describe what you want to build"
              name="user_input"
              rules={[{ required: true }]}
            >
              <Input.TextArea
                rows={4}
                placeholder="e.g. Build a FastAPI TODO service with JWT auth"
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              Start
            </Button>
          </Form>
        )}

        {mode === 'waiting' && (
          <Space>
            <Spin />
            <Typography.Text type="secondary">
              The agent is working. The composer will re-activate if your input is needed.
            </Typography.Text>
          </Space>
        )}

        {mode === 'clarify' && (
          <Form layout="vertical" form={clarifyForm} onFinish={onSubmitClarify}>
            {(clarifyPayload?.questions || []).map((q, i) => (
              <Form.Item key={i} label={q} name={['answers', i]}>
                <Input placeholder="Your answer" />
              </Form.Item>
            ))}
            <Button type="primary" htmlType="submit" loading={loading}>
              Submit answers
            </Button>
          </Form>
        )}

        {mode === 'hitl' && (
          <div>
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="Human decision required"
              description="The agent tried repairing the code automatically and couldn't pass all checks. Pick an action below."
            />

            {hitlPayload && (
              <Card size="small" title="Failure summary" style={{ marginBottom: 12 }}>
                <pre style={{ fontSize: 12, margin: 0 }}>
                  {JSON.stringify((hitlPayload as any)?.summary || hitlPayload, null, 2)}
                </pre>
                <CheckReport results={checks} />
              </Card>
            )}

            <Radio.Group value={action} onChange={(e) => setAction(e.target.value)}>
              {(['retry', 'patch', 'abort'] as HitlAction[]).map((a) => (
                <Tooltip key={a} title={ACTION_HELP[a]}>
                  <Radio.Button value={a}>
                    {a === 'retry' && 'Retry with hint'}
                    {a === 'patch' && 'Apply manual patch'}
                    {a === 'abort' && 'Abort'}
                    <InfoCircleOutlined style={{ marginLeft: 6, color: '#999' }} />
                  </Radio.Button>
                </Tooltip>
              ))}
            </Radio.Group>
            <div
              style={{
                marginTop: 8,
                padding: '8px 12px',
                background: '#fafafa',
                border: '1px dashed #e0e0e0',
                borderRadius: 4,
                fontSize: 13,
                color: '#555',
              }}
            >
              → {ACTION_NEXT[action]}
            </div>

            {action === 'patch' && (
              <Card size="small" title="Edit files" style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', gap: 16 }}>
                  <div style={{ width: 240 }}>
                    <FileTree files={Object.keys(files)} onSelect={setSelectedPath} />
                  </div>
                  <div style={{ flex: 1 }}>
                    {selectedPath ? (
                      <CodeViewer
                        path={selectedPath}
                        value={files[selectedPath] || ''}
                        onChange={(v) =>
                          setEditedFiles((prev) => ({ ...prev, [selectedPath]: v }))
                        }
                      />
                    ) : (
                      <div style={{ color: '#999' }}>Select a file to edit</div>
                    )}
                  </div>
                </div>
              </Card>
            )}

            <Input.TextArea
              rows={3}
              placeholder={
                action === 'retry'
                  ? 'Hint for the agent (e.g. "Use pytest instead of unittest")…'
                  : action === 'patch'
                  ? 'Optional note about your edits…'
                  : 'Reason for aborting (optional)…'
              }
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              style={{ marginTop: 12 }}
            />
            <Button
              type="primary"
              style={{ marginTop: 12 }}
              onClick={onSubmitHitl}
              loading={loading}
            >
              Submit decision
            </Button>
          </div>
        )}

        {(mode === 'finished' || mode === 'aborted' || mode === 'failed') && (
          <Space>
            <Typography.Text type={mode === 'failed' ? 'danger' : mode === 'aborted' ? 'warning' : 'secondary'}>
              {mode === 'finished'
                ? 'Run completed successfully. Start a new requirement?'
                : mode === 'aborted'
                ? 'Run was aborted — no code was generated. Start a new requirement?'
                : 'Previous run ended in failure. Start a new requirement?'}
            </Typography.Text>
            <Button
              type="primary"
              onClick={() => {
                reset();
                setHistoryRec(null);
                form.resetFields();
              }}
            >
              New requirement
            </Button>
          </Space>
        )}
      </Card>

      {usage && (
        <Card title="Token Usage (live)">
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="Input" value={usage.total_input_tokens} />
            </Col>
            <Col span={6}>
              <Statistic title="Output" value={usage.total_output_tokens} />
            </Col>
            <Col span={6}>
              <Statistic title="Total" value={usage.total_tokens} />
            </Col>
            <Col span={6}>
              <Statistic title="Cost (USD)" value={usage.total_cost_usd} precision={4} />
            </Col>
          </Row>
        </Card>
      )}

      <Card
        title="Event Timeline"
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Live SSE event stream — node enter/exit, file generation, check results, clarify,
            HITL, etc. The agent's progress log.
          </Typography.Text>
        }
      >
        <EventTimeline />
      </Card>

      <Card
        title="Generated Files"
        extra={
          <Space>
            {(() => {
              const art = latestState?.values.artifact;
              if (!art || !art.zip_path || !threadId) return null;
              const kb = Math.max(1, Math.round(art.size_bytes / 1024));
              return (
                <Tooltip title="Download the whole workspace as a single ZIP archive">
                  <Button
                    type="primary"
                    size="small"
                    href={api.downloadUrl(threadId)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Download ZIP · {art.file_count} files · {kb} KB
                  </Button>
                </Tooltip>
              );
            })()}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Virtual files produced by the agent (stored in state; editable during HITL patch).
              Persisted copies are under backend/data/workspaces/{`<thread>`}
            </Typography.Text>
          </Space>
        }
      >
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ width: 260, borderRight: '1px solid #eee', paddingRight: 8 }}>
            <FileTree files={Object.keys(stateFiles)} onSelect={setSelectedPath} />
          </div>
          <div style={{ flex: 1 }}>
            {selectedPath ? (
              <CodeViewer path={selectedPath} value={stateFiles[selectedPath] || ''} />
            ) : (
              <div style={{ color: '#999' }}>Select a file to preview</div>
            )}
          </div>
        </div>
      </Card>
    </Space>
  );
}
