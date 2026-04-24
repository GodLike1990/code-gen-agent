import { useEffect, useState } from 'react';
import { Alert, Card, Empty, Input, Select, Space, Statistic, Table, Tabs, Tag, Row, Col, Button } from 'antd';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useSession } from '../store/session';
import { LogEntry, LogSource, UsageSnapshot } from '../api/types';

const SOURCE_COLOR: Record<LogSource, string> = {
  memory: 'blue',
  disk: 'orange',
  merged: 'green',
};

const SOURCE_HINT: Record<LogSource, string> = {
  memory: 'Live from backend process memory',
  disk: 'Loaded from rotating log file (backend was likely restarted)',
  merged: 'Memory + disk combined',
};

export default function ObservabilityPage() {
  const { threadId, latestState } = useSession();
  const nav = useNavigate();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [source, setSource] = useState<LogSource>('memory');
  const [usage, setUsage] = useState<UsageSnapshot | null>(null);
  const [levelFilter, setLevelFilter] = useState<string | null>(null);
  const [nodeFilter, setNodeFilter] = useState<string | null>(null);

  const refresh = async () => {
    if (!threadId) return;
    try {
      const l = await api.getLogs(threadId);
      setLogs(l.logs);
      setSource(l.source);
      const u = await api.getUsage(threadId);
      setUsage(u.usage);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [threadId]);

  const langsmithUrl = latestState?.langsmith_url || null;

  const filteredLogs = logs.filter(
    (l) => (!levelFilter || l.level === levelFilter) && (!nodeFilter || l.node === nodeFilter),
  );

  const byModelRows = usage
    ? Object.entries(usage.by_model).map(([model, v]) => ({ key: model, model, ...v }))
    : [];

  return (
    <Tabs
      items={[
        {
          key: 'langsmith',
          label: 'LangSmith',
          children: langsmithUrl ? (
            <iframe
              src={langsmithUrl}
              style={{ width: '100%', height: 'calc(100vh - 200px)', border: '1px solid #eee' }}
              title="LangSmith"
            />
          ) : (
            <Alert
              type="info"
              message="LangSmith not configured"
              description="Set AGENT_LANGSMITH=true and LANGSMITH_API_KEY on the backend to enable tracing."
            />
          ),
        },
        {
          key: 'logs',
          label: 'Local Logs',
          children: (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space wrap>
                <Select
                  allowClear
                  placeholder="Level"
                  style={{ width: 120 }}
                  options={['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((l) => ({ value: l, label: l }))}
                  onChange={setLevelFilter}
                />
                <Input
                  placeholder="Node filter"
                  style={{ width: 160 }}
                  onChange={(e) => setNodeFilter(e.target.value || null)}
                />
                <Button onClick={refresh}>Refresh</Button>
                {threadId && logs.length > 0 && (
                  <Tag color={SOURCE_COLOR[source]} title={SOURCE_HINT[source]}>
                    source: {source}
                  </Tag>
                )}
              </Space>
              {!threadId ? (
                <Empty
                  description={
                    <Space direction="vertical" size={4}>
                      <span>No thread selected.</span>
                      <span style={{ color: '#888' }}>
                        Submit a new requirement, or pick a past thread from History.
                      </span>
                      <Button type="primary" onClick={() => nav('/history')}>
                        Go to History
                      </Button>
                    </Space>
                  }
                />
              ) : logs.length === 0 ? (
                <Empty
                  description={
                    <span style={{ color: '#888' }}>
                      No logs for this thread yet. If the backend was just restarted, older
                      in-memory logs are gone — only entries persisted to{' '}
                      <code>logs/agent.log</code> will reappear here once the disk fallback runs.
                    </span>
                  }
                />
              ) : (
                <Table
                  size="small"
                  dataSource={filteredLogs.map((l, i) => ({ key: i, ...l }))}
                  columns={[
                    { title: 'Time', dataIndex: 'ts', render: (t: number) => new Date(t * 1000).toLocaleTimeString() },
                    { title: 'Level', dataIndex: 'level', render: (l) => <Tag>{l}</Tag> },
                    { title: 'Node', dataIndex: 'node' },
                    { title: 'Event', dataIndex: 'event' },
                    { title: 'Duration', dataIndex: 'duration_ms' },
                    { title: 'Message', dataIndex: 'message' },
                  ]}
                  pagination={{ pageSize: 50 }}
                />
              )}
            </Space>
          ),
        },
        {
          key: 'usage',
          label: 'Token Usage',
          children: usage ? (
            <Space direction="vertical" style={{ width: '100%' }} size="large">
              <Row gutter={16}>
                <Col span={6}><Statistic title="Input Tokens" value={usage.total_input_tokens} /></Col>
                <Col span={6}><Statistic title="Output Tokens" value={usage.total_output_tokens} /></Col>
                <Col span={6}><Statistic title="Total" value={usage.total_tokens} /></Col>
                <Col span={6}><Statistic title="Cost (USD)" value={usage.total_cost_usd} precision={4} /></Col>
              </Row>
              <Card title="By Model">
                <Table
                  size="small"
                  dataSource={byModelRows}
                  pagination={false}
                  columns={[
                    { title: 'Model', dataIndex: 'model' },
                    { title: 'Calls', dataIndex: 'calls' },
                    { title: 'Input', dataIndex: 'input_tokens' },
                    { title: 'Output', dataIndex: 'output_tokens' },
                    { title: 'Total', dataIndex: 'total_tokens' },
                    { title: 'Cost (USD)', dataIndex: 'cost_usd' },
                  ]}
                />
              </Card>
            </Space>
          ) : (
            <Empty description="No usage data yet" />
          ),
        },
      ]}
    />
  );
}
