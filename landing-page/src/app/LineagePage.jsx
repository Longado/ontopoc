import React, { useMemo, useState } from "react";
import { getLineageGraph } from "./api.js";
import { NodeDrawer } from "./GraphDrawer.jsx";
import { GraphCanvas } from "./GraphCanvas.jsx";
import { FlowLine, GraphNode } from "./GraphNodes.jsx";
import { layeredLayout, lit, shown } from "./graphModel.js";
import { useLoad } from "./useLoad.js";

const FILTERS = [["", "全部"], ["data", "数据变了"], ["definition", "定义改了"]];

/** 血缘: from the datasets on the left to the types, relations, views and actions that stand on them and the answers saved from them. Picking a node lights what it reads and what reads it. */
export function LineagePage() {
  const [state] = useLoad(getLineageGraph, []);
  const [picked, setPicked] = useState(null);
  const [mode, setMode] = useState("both");
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const graph = state.data;
  const layout = useMemo(() => (graph ? layeredLayout(graph.nodes, graph.edges) : null), [graph]);
  const node = graph?.nodes.find((n) => n.id === picked) ?? null;
  const reach = useMemo(() => (node ? lit(node.id, graph.edges, mode) : null), [node, graph, mode]);
  const narrowed = Boolean(filter || query.trim());
  const stale = graph ? graph.nodes.filter((n) => n.stale).length : 0;
  const pick = (id) => { setPicked(id); setMode("both"); };
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>血缘</h1>
      </div>
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !graph && <p className="muted">加载中</p>}
      {graph && !graph.nodes.length && <p className="muted">还没有数据集和对象类型。</p>}
      {graph && graph.nodes.length > 0 && (
        <>
          <div className="graph-bar">
            <div className="seg" role="group" aria-label="按原因筛选">
              {FILTERS.map(([key, label]) => <button key={key} className={filter === key ? "on" : ""} aria-pressed={filter === key} onClick={() => setFilter(key)}>{label}</button>)}
            </div>
            <input type="search" placeholder="按名称找" aria-label="按名称找" value={query} onChange={(e) => setQuery(e.target.value)} />
            {stale > 0 && <span className="warn small">{stale} 个需再看</span>}
            {node && (
              <div className="seg" role="group" aria-label={`${node.name}的上下游`}>
                <button className={mode === "up" ? "on" : ""} aria-pressed={mode === "up"} onClick={() => setMode("up")}>只看上游</button>
                <button className={mode === "down" ? "on" : ""} aria-pressed={mode === "down"} onClick={() => setMode("down")}>只看下游</button>
                <button onClick={() => setPicked(null)}>清除</button>
              </div>
            )}
          </div>
          <div className={`graph-layout${node ? " with-drawer" : ""}`}>
            <GraphCanvas width={layout.width} height={layout.height} label="从数据集到回答的血缘" fileName="血缘.png" onBlank={() => setPicked(null)}>
              {graph.edges.map((e) => (
                <FlowLine key={`${e.from}>${e.to}`} from={layout.positions[e.from]} to={layout.positions[e.to]}
                  lit={Boolean(reach) && reach.has(e.from) && reach.has(e.to)} faded={Boolean(reach) && !(reach.has(e.from) && reach.has(e.to))} />
              ))}
              {graph.nodes.map((n) => (
                <GraphNode key={n.id} node={n} box={layout.positions[n.id]} picked={picked === n.id}
                  faded={(Boolean(reach) && !reach.has(n.id)) || (narrowed && !shown(n, filter, query))} onPick={() => pick(n.id)} />
              ))}
            </GraphCanvas>
            {node && <NodeDrawer key={node.id} node={node} onClose={() => setPicked(null)} />}
          </div>
        </>
      )}
    </main>
  );
}
