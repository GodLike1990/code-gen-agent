import { useEffect, useState } from 'react';
import { Button, Card, Space, Table, Tag, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { RequirementRecord } from '../api/types';
import { useSession } from '../store/session';
import { RUN_STATUS_COLOR, RUN_STATUS_LABEL } from '../constants/status';

function truncate(s: string, n = 80): string {
  if (!s) return '';
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function formatTs(iso: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function HistoryPage() {
  const nav = useNavigate();
  const setThread = useSession((s) => s.setThread);
  const setState = useSession((s) => s.setState);
  const [items, setItems] = useState<RequirementRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.listHistory();
      setItems(res.items);
    } catch (e: any) {
      message.error(`Failed to load history: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openGraph = async (rec: RequirementRecord) => {
    setThread(rec.thread_id);
    try {
      const snap = await api.getState(rec.thread_id);
      setState(snap);
    } catch {
      // state may have been wiped; still navigate
      setState(null);
    }
    nav('/graph');
  };

  const columns = [
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatTs(v),
    },
    {
      title: 'Thread ID',
      dataIndex: 'thread_id',
      key: 'thread_id',
      width: 280,
      render: (v: string) => <Typography.Text code>{v}</Typography.Text>,
    },
    {
      title: 'Request',
      dataIndex: 'request',
      key: 'request',
      render: (v: string) => <span title={v}>{truncate(v)}</span>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (v: string) => <Tag color={RUN_STATUS_COLOR[v] ?? 'default'}>{RUN_STATUS_LABEL[v] ?? v}</Tag>,
    },
    {
      title: 'Action',
      key: 'action',
      width: 200,
      render: (_: unknown, rec: RequirementRecord) => (
        <Space>
          <Button type="link" onClick={() => openGraph(rec)}>
            View Graph
          </Button>
          <Button
            type="link"
            onClick={() => {
              setThread(rec.thread_id);
              nav('/requirement');
            }}
          >
            View Request
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="Session History"
      extra={
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          Refresh
        </Button>
      }
    >
      <Table
        rowKey="thread_id"
        loading={loading}
        dataSource={items}
        columns={columns as any}
        pagination={{ pageSize: 20 }}
        locale={{ emptyText: 'No sessions yet — submit a requirement to get started.' }}
      />
    </Card>
  );
}
