import Editor from '@monaco-editor/react';

export default function CodeViewer({
  path,
  value,
  onChange,
}: {
  path: string;
  value: string;
  onChange?: (v: string) => void;
}) {
  const ext = path.split('.').pop() || '';
  const langMap: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    jsx: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    go: 'go',
    json: 'json',
    md: 'markdown',
    yaml: 'yaml',
    yml: 'yaml',
  };
  return (
    <Editor
      height="500px"
      language={langMap[ext] || 'plaintext'}
      value={value}
      onChange={(v) => onChange?.(v || '')}
      options={{ readOnly: !onChange, minimap: { enabled: false }, fontSize: 13 }}
    />
  );
}
