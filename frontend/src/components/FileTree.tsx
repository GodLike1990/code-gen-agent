import { Tree } from 'antd';
import { useMemo } from 'react';

interface Node {
  title: string;
  key: string;
  children?: Node[];
  isLeaf?: boolean;
}

function buildTree(paths: string[]): Node[] {
  const root: Record<string, any> = {};
  for (const p of paths) {
    const parts = p.split('/');
    let cur = root;
    parts.forEach((part, i) => {
      cur[part] = cur[part] || { __children: {}, __leaf: i === parts.length - 1, __path: parts.slice(0, i + 1).join('/') };
      cur = cur[part].__children;
    });
  }
  const toTree = (obj: Record<string, any>): Node[] =>
    Object.entries(obj).map(([name, val]) => ({
      title: name,
      key: val.__path,
      isLeaf: val.__leaf && Object.keys(val.__children).length === 0,
      children: Object.keys(val.__children).length ? toTree(val.__children) : undefined,
    }));
  return toTree(root);
}

export default function FileTree({
  files,
  onSelect,
}: {
  files: string[];
  onSelect: (path: string) => void;
}) {
  const data = useMemo(() => buildTree(files), [files]);
  return (
    <Tree
      treeData={data}
      defaultExpandAll
      onSelect={(keys) => keys[0] && onSelect(String(keys[0]))}
    />
  );
}
