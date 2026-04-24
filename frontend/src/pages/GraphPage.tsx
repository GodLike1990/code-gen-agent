import { useEffect, useMemo, useState } from 'react';
import { Card, Descriptions, Empty, Space, Tag } from 'antd';
import { api } from '../api/client';
import { GraphSchema } from '../api/types';
import GraphCanvas from '../components/GraphCanvas';
import { useSession } from '../store/session';

type Status = 'pending' | 'running' | 'success' | 'failed' | 'interrupted';

export default function GraphPage() {
  const [schema, setSchema] = useState<GraphSchema | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const { threadId, events, latestState, setState } = useSession();

  useEffect(() => {
    api.graphSchema().then(setSchema).catch(console.error);
  }, []);

  // refresh state periodically while a thread is active
  useEffect(() => {
    if (!threadId) return;
    const t = setInterval(async () => {
      try {
        const s = await api.getState(threadId);
        setState(s);
      } catch {
        /* thread may not exist yet */
      }
    }, 2000);
    return () => clearInterval(t);
  }, [threadId, setState]);

  const nodeStatus = useMemo(() => {
    const status: Record<string, Status> = {
      intent: 'pending',
      clarify: 'pending',
      decompose: 'pending',
      codegen: 'pending',
      checks: 'pending',
      repair: 'pending',
      hitl: 'pending',
    };
    for (const e of events) {
      const t = e.event;
      if (t.startsWith('node:')) {
        const name = t.slice(5);
        if (name in status) status[name] = 'success';
      }
    }
    const next = (latestState?.next || [])[0];
    if (next && next in status) status[next] = 'running';
    const failed = Object.values(latestState?.values.check_results || {}).some((r) => !r.passed);
    if (failed) status['checks'] = 'failed';
    if (latestState?.values.escalated) status['hitl'] = 'interrupted';
    return status;
  }, [events, latestState]);

  const activeNode = (latestState?.next || [])[0] || null;

  if (!schema) return <Empty description="Loading graph..." />;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card
        title="Graph Topology"
        extra={
          <Space>
            <Tag>thread: {threadId || '—'}</Tag>
            <Tag color="blue">repair_attempts: {latestState?.values.repair_attempts ?? 0}</Tag>
            <Tag color={latestState?.values.escalated ? 'red' : 'default'}>
              escalated: {String(latestState?.values.escalated ?? false)}
            </Tag>
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
