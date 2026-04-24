import { Alert, Collapse, Tag } from 'antd';
import { CheckResult } from '../api/types';

export default function CheckReport({ results }: { results: Record<string, CheckResult> }) {
  const items = Object.entries(results).map(([name, r]) => ({
    key: name,
    label: (
      <span>
        <Tag color={r.passed ? 'green' : 'red'}>{r.passed ? 'PASS' : 'FAIL'}</Tag>
        {name} <span style={{ color: '#999', fontSize: 12 }}>({r.issues.length} issues)</span>
      </span>
    ),
    children: (
      <>
        {r.issues.map((i, idx) => (
          <Alert
            key={idx}
            type={i.severity === 'error' ? 'error' : i.severity === 'warn' ? 'warning' : 'info'}
            message={`${i.file}:${i.line} ${i.code || ''}`}
            description={i.message}
            style={{ marginBottom: 4 }}
            showIcon
          />
        ))}
        {r.raw_output && (
          <pre style={{ background: '#fafafa', padding: 8, fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
            {r.raw_output}
          </pre>
        )}
      </>
    ),
  }));
  return <Collapse items={items} />;
}
