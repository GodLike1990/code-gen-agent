import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, Edge, Node, Position } from 'reactflow';
import { GraphSchema } from '../api/types';

interface Props {
  schema: GraphSchema;
  activeNode: string | null;
  nodeStatus: Record<string, 'pending' | 'running' | 'success' | 'failed' | 'interrupted'>;
  onSelect: (id: string | null) => void;
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#d9d9d9',
  running: '#1677ff',
  success: '#52c41a',
  failed: '#ff4d4f',
  interrupted: '#faad14',
};

function columnFor(id: string): number {
  const order = ['intent', 'clarify', 'decompose', 'codegen', 'checks', 'repair', 'hitl'];
  return order.indexOf(id);
}

export default function GraphCanvas({ schema, activeNode, nodeStatus, onSelect }: Props) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  useEffect(() => {
    const ns: Node[] = schema.nodes.map((n, i) => {
      const col = columnFor(n.id);
      const status = nodeStatus[n.id] || 'pending';
      const isActive = activeNode === n.id;
      return {
        id: n.id,
        position: { x: (col >= 0 ? col : i) * 160, y: n.id === 'clarify' || n.id === 'hitl' ? 120 : 0 },
        data: { label: `${n.label}\n(${status})` },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          padding: 10,
          border: `2px solid ${isActive ? '#722ed1' : STATUS_COLORS[status]}`,
          background: STATUS_COLORS[status] + '22',
          whiteSpace: 'pre-wrap',
          textAlign: 'center',
          borderRadius: 8,
          width: 140,
        },
      };
    });
    const es: Edge[] = schema.edges
      .filter((e) => e.source !== '__start__' && e.target !== '__end__')
      .map((e, i) => ({
        id: `e${i}`,
        source: e.source,
        target: e.target,
        label: e.label,
        animated: activeNode === e.source,
      }));
    setNodes(ns);
    setEdges(es);
  }, [schema, activeNode, nodeStatus]);

  const onNodeClick = useCallback((_: unknown, n: Node) => onSelect(n.id), [onSelect]);

  const style = useMemo(() => ({ height: 500, background: '#fff', borderRadius: 8 }), []);

  return (
    <div style={style}>
      <ReactFlow nodes={nodes} edges={edges} onNodeClick={onNodeClick} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
