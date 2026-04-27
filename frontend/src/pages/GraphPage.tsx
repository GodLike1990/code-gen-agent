import { useEffect, useMemo, useState } from 'react';
import { Card, Descriptions, Divider, Empty, Space, Tag } from 'antd';
import { api } from '../api/client';
import { GraphSchema, RequirementRecord } from '../api/types';
import GraphCanvas from '../components/GraphCanvas';
import { useSession } from '../store/session';
import { NODE_STATUS_COLOR, NODE_STATUS_LABEL, RUN_STATUS_COLOR, RUN_STATUS_LABEL } from '../constants/status';

type Status = 'pending' | 'running' | 'paused' | 'success' | 'failed' | 'interrupted' | 'cancelled';

const NODE_STATUS_ENTRIES = ['pending', 'running', 'paused', 'success', 'failed', 'interrupted', 'cancelled'] as const;

function NodeStatusLegend() {
  return (
    <Space size={8} wrap>
      {NODE_STATUS_ENTRIES.map((s) => (
        <span key={s} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#555' }}>
          <span
            style={{
              display: 'inline-block',
              width: 10,
              height: 10,
              borderRadius: 2,
              background: NODE_STATUS_COLOR[s],
              border: s === 'paused' || s === 'cancelled' ? '1px dashed #888' : '1px solid transparent',
              flexShrink: 0,
            }}
          />
          {NODE_STATUS_LABEL[s]}
        </span>
      ))}
    </Space>
  );
}

export default function GraphPage() {
  const [schema, setSchema] = useState<GraphSchema | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [record, setRecord] = useState<RequirementRecord | null>(null);
  const { threadId, events, latestState, setState } = useSession();

  useEffect(() => {
    api.graphSchema().then(setSchema).catch(console.error);
  }, []);

  // refresh state + record periodically while a thread is active
  useEffect(() => {
    if (!threadId) return;
    const tick = async () => {
      try {
        const [s, r] = await Promise.all([
          api.getState(threadId),
          api.getHistory(threadId).catch(() => null),
        ]);
        setState(s);
        if (r) setRecord(r);
      } catch {
        /* thread may not exist yet */
      }
    };
    tick();
    const t = setInterval(tick, 2000);
    return () => clearInterval(t);
  }, [threadId, setState]);

  const isLive = record?.status === 'running';

  const nodeStatus = useMemo(() => {
    // Initialize all 9 graph nodes as pending.
    // This list must stay in sync with GRAPH_TOPOLOGY node ids in builder.py.
    const status: Record<string, Status> = {
      intent:    'pending',
      clarify:   'pending',
      decompose: 'pending',
      codegen:   'pending',
      checks:    'pending',
      repair:    'pending',
      hitl:      'pending',
      verify:    'pending',
      package:   'pending',
    };

    const v = latestState?.values;

    // Derive completed nodes from persisted state — survives page refresh.
    if (v) {
      if (v.intent) status['intent'] = 'success';
      // clarify ran if questions were asked (clarifications array populated by the node)
      if ((v.clarifications && v.clarifications.length > 0) || (v.clarify_questions && v.clarify_questions.length > 0)) {
        status['clarify'] = 'success';
      }
      if (v.tasks && v.tasks.length > 0) status['decompose'] = 'success';
      if (v.generated_files && Object.keys(v.generated_files).length > 0) status['codegen'] = 'success';
      if (v.check_results && Object.keys(v.check_results).length > 0) {
        const failed = Object.values(v.check_results).some((r) => !(r as any).passed);
        status['checks'] = failed ? 'failed' : 'success';
      }
      if (v.repair_attempts && v.repair_attempts > 0) status['repair'] = 'success';
      if (v.escalated) status['hitl'] = 'interrupted';
      // verify ran if a verify_result is present
      if (v.verify_result) status['verify'] = (v.verify_result as any).passed ? 'success' : 'failed';
      // package ran if an artifact was produced
      if (v.artifact && (v.artifact as any).zip_path) status['package'] = 'success';
      // If the run is fully done with artifact, all remaining pending nodes → success.
      // But NOT for aborted runs — aborted means stopped early, pending = not executed.
      if (record?.status === 'done' && v.artifact) {
        for (const k of Object.keys(status)) {
          if (status[k] === 'pending') status[k] = 'success';
        }
      }
    }

    // Live SSE events add real-time refinement on top of the state-derived baseline.
    for (const e of events) {
      const t = e.event;
      if (t.startsWith('node:')) {
        const name = t.slice(5);
        if (name in status && status[name] !== 'failed' && status[name] !== 'interrupted') {
          status[name] = 'success';
        }
      }
    }

    // Current "next" node — running if live, paused if stopped mid-way.
    const next = (latestState?.next || [])[0];
    if (next && next in status) {
      status[next] = isLive ? 'running' : 'paused';
    }

    return status;
  }, [events, latestState, isLive, record?.status]);

  const activeNode = (latestState?.next || [])[0] || null;

  if (!schema) return <Empty description="Loading graph..." />;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card
        title="Graph Topology"
        extra={
          <Space split={<Divider type="vertical" />}>
            <NodeStatusLegend />
            <Space>
              <Tag>thread: {threadId || '—'}</Tag>
              {record && (
                <Tag color={RUN_STATUS_COLOR[record.status] ?? 'default'}>
                  {RUN_STATUS_LABEL[record.status] ?? record.status}
                </Tag>
              )}
              <Tag color="blue">repair_attempts: {latestState?.values.repair_attempts ?? 0}</Tag>
              <Tag color={latestState?.values.escalated ? 'red' : 'default'}>
                escalated: {String(latestState?.values.escalated ?? false)}
              </Tag>
            </Space>
          </Space>
        }
      >
        <GraphCanvas
          schema={schema}
          activeNode={activeNode}
          nodeStatus={nodeStatus}
          onSelect={setSelected}
        />
      </Card>

      <Card title={`Node Detail: ${selected || '—'}`}>
        {selected ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="Status">{nodeStatus[selected]}</Descriptions.Item>
            <Descriptions.Item label="Recent Events">
              <pre style={{ maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(
                  events.filter((e) => e.event.includes(selected)).slice(-10),
                  null,
                  2,
                )}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="State Slice">
              <pre style={{ maxHeight: 240, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(latestState?.values ?? {}, null, 2)}
              </pre>
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="Click a node to inspect" />
        )}
      </Card>
    </Space>
  );
}
