import { useEffect, useState } from "react";
import { getMindmap } from "../api";

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

  if (error) return <div className="screen"><p className="status error">{error}</p></div>;
  if (!tree) return <div className="screen"><p className="status">Loading…</p></div>;

  return (
    <div className="screen">
      <div className="dashboard-header">
        <h2>Mind Map</h2>
        <button onClick={load}>Refresh</button>
      </div>
      <div className="card mindmap">
        <MindMapNode node={tree} depth={0} />
      </div>
    </div>
  );
}

function MindMapNode({ node, depth }) {
  const isLeaf = !node.children;
  return (
    <div className={`mindmap-node depth-${depth}`}>
      <div className="mindmap-label">
        {node.name}
        {isLeaf && (
          <>
            {" "}
            <span className="badge">{node.count} call{node.count === 1 ? "" : "s"}</span>
            {node.reused_count > 0 && (
              <span className="badge cache">{node.reused_count} reused</span>
            )}
          </>
        )}
      </div>
      {node.children && node.children.length > 0 && (
        <div className="mindmap-children">
          {node.children.map((child) => (
            <MindMapNode node={child} depth={depth + 1} key={child.name} />
          ))}
        </div>
      )}
    </div>
  );
}