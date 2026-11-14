import React, { useMemo, useState } from "react";
import { getRelationGraph } from "./api.js";
import { EdgeDrawer, NodeDrawer } from "./GraphDrawer.jsx";
import { GraphCanvas } from "./GraphCanvas.jsx";
import { GraphNode, RelationLine } from "./GraphNodes.jsx";
import { forceLayout, groupEdges, neighbours } from "./graphModel.js";
import { hrefFor } from "./routeModel.js";
import { useLoad } from "./useLoad.js";

/** The relation graph: the types as cards coloured by state, the relations as lines saying how many rows connect. Picking a type or a line lights it and what it touches and opens its drawer. */
export function RelationGraph() {
  const [state] = useLoad(getRelationGraph, []);
  const [picked, setPicked] = useState(null);   // {kind: "node" | "edge", id}
  const graph = state.data;
  const layout = useMemo(() => (graph ? forceLayout(graph.nodes, graph.edges) : null), [graph]);
  const groups = useMemo(() => (graph ? groupEdges(graph.edges.filter((e) => e.from !== e.to)) : []), [graph]);   // a relation from a type to itself has no line: its drawer lists it
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!graph) return <p className="muted">加载中</p>;
  if (!graph.nodes.length) return <p className="muted">还没有对象类型，画不出图。<a href={hrefFor({ page: "types" })}>去对象类型</a></p>;
  const group = picked?.kind === "edge" ? groups.find((g) => g.key === picked.id) : null;
  const node = picked?.kind === "node" ? graph.nodes.find((n) => n.id === picked.id) : null;
  const lit = group ? new Set([group.from, group.to]) : node ? neighbours(node.id, graph.edges) : null;
  return (
    <div className={`graph-layout${picked ? " with-drawer" : ""}`}>
      <GraphCanvas width={layout.width} height={layout.height} label="对象类型和它们之间的关系" fileName="关系图.png" onBlank={() => setPicked(null)}>
        {groups.map((g) => (
          <RelationLine key={g.key} group={g} from={layout.positions[g.from]} to={layout.positions[g.to]} picked={group?.key === g.key}
            lit={Boolean(node) && (g.from === node.id || g.to === node.id)} faded={Boolean(lit) && !(lit.has(g.from) && lit.has(g.to) && (group || g.from === node?.id || g.to === node?.id))}
            onPick={() => setPicked({ kind: "edge", id: g.key })} />
        ))}
        {graph.nodes.map((n) => (
          <GraphNode key={n.id} node={n} box={layout.positions[n.id]} picked={node?.id === n.id} faded={Boolean(lit) && !lit.has(n.id)} onPick={() => setPicked({ kind: "node", id: n.id })} />
        ))}
      </GraphCanvas>
      {node && <NodeDrawer key={node.id} node={node} onClose={() => setPicked(null)} />}
      {group && <EdgeDrawer key={group.key} group={group} onClose={() => setPicked(null)} />}
    </div>
  );
}
