import { Layout as AntLayout, Menu, Tooltip, theme } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  FormOutlined,
  NodeIndexOutlined,
  DashboardOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import { ReactNode, useEffect } from 'react';
import { useSession, RunStatus } from '../store/session';
import { api } from '../api/client';

const { Header, Content, Sider } = AntLayout;

const items = [
  { key: '/requirement', icon: <FormOutlined />, label: 'Requirement' },
  { key: '/graph', icon: <NodeIndexOutlined />, label: 'Graph' },
  { key: '/history', icon: <HistoryOutlined />, label: 'History' },
  { key: '/observability', icon: <DashboardOutlined />, label: 'Observability' },
];

const STATUS_COLOR: Record<RunStatus, string> = {
  idle: '#bbb',
  running: '#1677ff',
  done: '#52c41a',
  aborted: '#fa8c16',
  failed: '#ff4d4f',
  hitl: '#faad14',
  cancelled: '#9ca3af',
};

const STATUS_TEXT: Record<RunStatus, string> = {
  idle: 'Idle — no active run',
  running: 'Running — click to open Graph',
  done: 'Last run completed successfully',
  aborted: 'Run aborted by user',
  failed: 'Last run failed',
  hitl: 'Input needed — back to Requirement',
  cancelled: 'Last run cancelled (client disconnected)',
};

function StatusDot({ status, onClick }: { status: RunStatus; onClick: () => void }) {
  const color = STATUS_COLOR[status];
  const pulse = status === 'running' || status === 'hitl';
  return (
    <Tooltip title={STATUS_TEXT[status]}>
      <span
        onClick={onClick}
        style={{
          display: 'inline-block',
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: color,
          cursor: 'pointer',
          boxShadow: pulse ? `0 0 0 0 ${color}` : 'none',
          animation: pulse ? 'rg-pulse 1.4s infinite' : 'none',
        }}
      />
    </Tooltip>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const nav = useNavigate();
  const loc = useLocation();
  const { threadId, runStatus, hitlPayload, clarifyPayload, setHitl, setClarify, setRunStatus } =
    useSession();
  const { token } = theme.useToken();

  // ---- Global interrupt recovery ----
  // Whenever we have a threadId but no local payload, ask the backend whether
  // a clarify / HITL interrupt is pending. This runs on EVERY page (not just
  // Requirement), so a user browsing Graph/Observability/History who reloads
  // the tab — or whose SSE stream dropped — still gets pulled back to answer.
  // Polling interval is light (5s) and stops as soon as a payload is captured
  // or the run is clearly not running.
  useEffect(() => {
    if (!threadId) return;
    if (hitlPayload || clarifyPayload) return; // already have one
    if (runStatus === 'done' || runStatus === 'failed' || runStatus === 'aborted') return;

    let cancelled = false;
    const probe = async () => {
      try {
        const itp = await api.getInterrupt(threadId);
        if (cancelled) return;
        if (!itp.pending) return;
        if (itp.type === 'clarify') {
          setClarify({ questions: itp.questions });
        } else if (itp.type === 'hitl') {
          setHitl({ thread_id: itp.thread_id, type: 'hitl', summary: itp.summary });
          setRunStatus('hitl');
        }
      } catch (err) {
        // 404 (no thread / no pending interrupt) is expected and noisy to log.
        // Surface all other errors to devtools so a broken backend is visible.
        if (!cancelled) console.warn('interrupt poll failed', err);
      }
    };
    probe(); // immediate
    const id = setInterval(probe, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [threadId, runStatus, hitlPayload, clarifyPayload, setClarify, setHitl, setRunStatus]);

  // While the agent is waiting for human input, the composer is the only
  // place the user can act — so we pin them to /requirement. This also
  // covers the "reload on /graph" case (global interrupt recovery above
  // populates the payload; this effect then redirects).
  useEffect(() => {
    const isPending = !!clarifyPayload || runStatus === 'hitl';
    if (isPending && loc.pathname !== '/requirement' && loc.pathname !== '/') {
      nav('/requirement', { replace: false });
    }
  }, [clarifyPayload, runStatus, loc.pathname, nav]);

  // Page-title indicator so users in another browser tab notice input is needed.
  useEffect(() => {
    const isPending = !!clarifyPayload || runStatus === 'hitl';
    const original = 'Code Gen Agent';
    document.title = isPending ? `⚠ Input needed — ${original}` : original;
    return () => {
      document.title = original;
    };
  }, [clarifyPayload, runStatus]);

  const pendingInput = !!clarifyPayload || runStatus === 'hitl';

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <style>{`
        @keyframes rg-pulse {
          0% { box-shadow: 0 0 0 0 rgba(22,119,255,0.7); }
          70% { box-shadow: 0 0 0 8px rgba(22,119,255,0); }
          100% { box-shadow: 0 0 0 0 rgba(22,119,255,0); }
        }
      `}</style>
      <Header style={{ color: '#fff', display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ fontWeight: 600, fontSize: 18 }}>Code Gen Agent</div>
        <div
          style={{
            marginLeft: 'auto',
            fontSize: 12,
            opacity: 0.9,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <StatusDot
            status={runStatus}
            onClick={() => nav(pendingInput ? '/requirement' : '/graph')}
          />
          <span>thread: {threadId || '—'}</span>
        </div>
      </Header>
      <AntLayout>
        <Sider width={200} style={{ background: token.colorBgContainer }}>
          <Menu
            mode="inline"
            selectedKeys={[loc.pathname]}
            items={items}
            onClick={(e) => nav(e.key)}
            style={{ height: '100%', borderRight: 0 }}
          />
        </Sider>
        <Content style={{ padding: 24, background: '#f5f7fa' }}>{children}</Content>
      </AntLayout>
    </AntLayout>
  );
}
