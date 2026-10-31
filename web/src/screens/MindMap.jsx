import { useEffect, useMemo, useState } from "react";
import { ReactFlow, Background, Controls, MarkerType, Position, ReactFlowProvider } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { getMindmap } from "../api";

const PALETTE = ["#00a3dc", "#7c6cf0", "#20c997", "#f5a623", "#ef5da8", "#4cd9c0", "#ff8a5c"];
const ROW_H = 64;
const COL_W = 300;

function mkNode(id, label, depth, x, y, color, leaf) {
  return {
    id,
    position: { x, y },
    data: { label, depth, color, leaf },
    type: "mindNode",
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  };
}

function mkEdge(source, target, color) {
  return {
    id: `${source}->${target}`,
    source,
    target,
    type: "default",
    style: { stroke: color, strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, color },
  };
}

function layout(tree) {
  if (!tree) return { nodes: [], edges: [] };

  const nodes = [];
  const edges = [];
  const categories = tree.children || [];
  let cursorY = 0;
  const catCenters = [];

  categories.forEach((cat, ci) => {
    const leaves = cat.children || [];
    const color = PALETTE[ci % PALETTE.length];
    const bandStart = cursorY;

    if (leaves.length === 0) {
      catCenters.push(cursorY);
      cursorY += ROW_H;
    } else {
      leaves.forEach((leaf, li) => {
        const id = `cat-${ci}-leaf-${li}`;
        nodes.push(mkNode(id, leaf.name, 2, COL_W * 2, cursorY, color, leaf));
        edges.push(mkEdge(`cat-${ci}`, id, color));
        cursorY += ROW_H;
      });
      catCenters.push((bandStart + cursorY - ROW_H) / 2);
    }

    nodes.push(mkNode(`cat-${ci}`, cat.name, 1, COL_W, catCenters[ci], color));
    cursorY += 28;
  });

  const rootY = catCenters.length ? (catCenters[0] + catCenters[catCenters.length - 1]) / 2 : 0;
  nodes.push(mkNode("root", tree.name, 0, 0, rootY, PALETTE[0]));
  categories.forEach((_, ci) => edges.push(mkEdge("root", `cat-${ci}`, PALETTE[ci % PALETTE.length])));

  return { nodes, edges };
}

function MindNode({ data }) {
  const { label, depth, color, leaf } = data;
  return (
    <div
      className={`mind-node depth-${depth}`}
      style={{ borderColor: color, boxShadow: depth === 0 ? `0 0 0 2px ${color}` : undefined }}
    >
      <span className="mind-node-label">{label}</span>
      {leaf && (
        <span className="mind-node-meta">
          <span className="mind-pill" style={{ background: color }}>
            {leaf.count} call{leaf.count === 1 ? "" : "s"}
          </span>
          {leaf.reused_count > 0 && <span className="mind-pill reused">{leaf.reused_count} reused</span>}
        </span>
      )}
    </div>
  );
}

const nodeTypes = { mindNode: MindNode };

export default function MindMap() {
  const [tree, setTree] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    load();
  }, []);

  function load() {
    setError(null);
    getMindmap().then(setTree).catch((err) => setError(err.message));
  }

  const { nodes, edges } = useMemo(() => layout(tree), [tree]);

  if (error) return <div className="screen"><p className="status error">{error}</p></div>;
  if (!tree) return <div className="screen"><p className="status">Loading…</p></div>;

  return (
    <div className="screen">
      <div className="dashboard-header">
        <h2>Mind Map</h2>
        <button onClick={load}>Refresh</button>
      </div>
      <div className="card mindmap-canvas">
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
          >
            <Background gap={24} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </div>
  );
}