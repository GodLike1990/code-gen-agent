import { List, Tag, Typography } from 'antd';
import { useSession } from '../store/session';

const colorByEvent: Record<string, string> = {
  'node:intent': 'blue',
  'node:clarify': 'gold',
  'node:decompose': 'cyan',
  'node:codegen': 'geekblue',
  'node:checks': 'purple',
  'node:repair': 'orange',
  'node:hitl': 'red',
  file_generated: 'green',
  check_report: 'magenta',
  repair: 'orange',
  done: 'green',
  error: 'red',
};

export default function EventTimeline() {
  const events = useSession((s) => s.events);
  return (
    <List
      size="small"
      bordered
      dataSource={[...events].reverse()}
      style={{ maxHeight: 360, overflow: 'auto', background: '#fff' }}
      renderItem={(e) => (
        <List.Item>
          <Tag color={colorByEvent[e.event] || 'default'}>{e.event}</Tag>
          <Typography.Text code style={{ fontSize: 12 }}>
            {JSON.stringify(e.data)}
          </Typography.Text>
        </List.Item>
      )}
    />
  );
}
