import React, { useMemo, useState } from "react";
import { getRelationGraph } from "./api.js";
import { NodeDrawer } from "./GraphDrawer.jsx";
import { GraphCanvas } from "./GraphCanvas.jsx";
import { GraphNode, RelationLine } from "./GraphNodes.jsx";
import { LEGEND, connectedMeaning, forceLayout, groupEdges, labelWidth, neighbours, placeLabels, verdictText } from "./graphModel.js";
import { CARDINALITY_LABEL, keyPairText, lineLabel, matchRateText, sentBackLine } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { useLoad } from "./useLoad.js";
import { Drawer } from "./ui/Drawer.jsx";

/** What the colours and the numbers on the graph mean. */
function Legend({ example }) {
  return (
    <div className="graph-legend" aria-label="图例">
      <ul>
        {LEGEND.map((l) => (
          <li key={l.key}><span className="swatch" style={{ background: l.colour }} aria-hidden="true" /><strong>{l.word}</strong> <span className="muted">{l.text}</span></li>
        ))}
      </ul>
      <p className="muted small"><strong>点一条线</strong>（或线上的名字），在右边看这个关系连上了多少行。{example ? `例如${connectedMeaning(example)}。` : ""}数的是“多”的一端；箭头指向“一”的一端；虚线表示基数不成立。</p>
    </div>
  );
}

/** The drawer a picked line opens: each relation between the two types, what it connects, whether its cardinality holds, and the way to its page. */
function EdgeDrawer({ group, onClose }) {
  const [first] = group.edges;
  return (
    <Drawer open title={`${first.from_name} 和 ${first.to_name}`} onClose={onClose} width={440}>
      {group.edges.map((e) => (
        <section key={e.id} className="edge-card">
          <h3><a href={hrefFor({ page: "relation", id: e.key })}>{e.name}</a> <State item={e} /></h3>
          <p className="muted">{e.from_name} → {e.to_name}，{CARDINALITY_LABEL[e.cardinality] ?? e.cardinality_label}</p>
          <p className="muted small">{keyPairText(e)}</p>
          <p><strong>{matchRateText(e)}</strong></p>
          <p className="muted small">{connectedMeaning(e)}</p>
          {verdictText(e) && <p className={e.cardinality_ok === false ? "warn" : "muted small"}>{verdictText(e)}</p>}
          {sentBackLine(e) && <p className="warn">{sentBackLine(e)}</p>}
          {e.stale && <div className="reason"><strong>{e.stale.label}{e.stale.root ? `：${e.stale.root}` : ""}</strong><p>{e.stale.text ?? e.stale.text_hidden}</p></div>}
          <p><a className="button secondary" href={hrefFor({ page: "relation", id: e.key })}>{e.state === "confirmed" ? "看明细" : "去看，再确认"}</a></p>
        </section>
      ))}
    </Drawer>
  );
}

/** The relation graph: the types as cards coloured by state, the relations as lines saying how many rows connect. Picking a type lights it and what it touches and opens its panel;
 * picking a line opens its drawer. A legend says what the colours and the numbers mean. */
export function RelationGraph() {
  const [state] = useLoad(getRelationGraph, []);
  const [picked, setPicked] = useState(null);   // {kind: "node" | "edge", id}
  const graph = state.data;
  const layout = useMemo(() => (graph ? forceLayout(graph.nodes, graph.edges) : null), [graph]);
  const groups = useMemo(() => (graph ? groupEdges(graph.edges.filter((e) => e.from !== e.to)) : []), [graph]);   // a relation from a type to itself has no line: its drawer lists it
  const labels = useMemo(() => (layout ? placeLabels(groups, layout.positions, (g) => labelWidth(lineLabel(g))) : {}), [layout, groups]);
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!graph) return <p className="muted">加载中</p>;
  if (!graph.nodes.length && graph.hidden_types > 0) return <p className="muted">有 {graph.hidden_types} 个对象类型没有开放给你，找管理员。</p>;
  if (!graph.nodes.length) return <p className="muted">还没有对象类型，画不出图。<a href={hrefFor({ page: "types" })}>去对象类型</a></p>;
  const group = picked?.kind === "edge" ? groups.find((g) => g.key === picked.id) : null;
  const node = picked?.kind === "node" ? graph.nodes.find((n) => n.id === picked.id) : null;
  const lit = group ? new Set([group.from, group.to]) : node ? neighbours(node.id, graph.edges) : null;
  return (
    <>
      <div className={`graph-layout rel-graph${node ? " with-drawer" : ""}`}>
        <GraphCanvas width={layout.width} height={layout.height} label="对象类型和它们之间的关系" fileName="关系图.png" onBlank={() => setPicked(null)}>
          {["line", "label"].map((part) => groups.map((g) => (
            <RelationLine key={`${part}-${g.key}`} part={part} group={g} from={layout.positions[g.from]} to={layout.positions[g.to]} picked={group?.key === g.key} labelAt={labels[g.key]}
              lit={Boolean(node) && (g.from === node.id || g.to === node.id)} faded={Boolean(lit) && !(lit.has(g.from) && lit.has(g.to) && (group || g.from === node?.id || g.to === node?.id))}
              onPick={() => setPicked({ kind: "edge", id: g.key })} />
          )))}
          {graph.nodes.map((n) => (
            <GraphNode key={n.id} node={n} box={layout.positions[n.id]} picked={node?.id === n.id} faded={Boolean(lit) && !lit.has(n.id)} onPick={() => setPicked({ kind: "node", id: n.id })} />
          ))}
        </GraphCanvas>
        {node && <NodeDrawer key={node.id} node={node} onClose={() => setPicked(null)} />}
      </div>
      <Legend example={graph.edges.find((e) => e.connected != null && e.of > e.connected) ?? graph.edges.find((e) => e.connected != null)} />
      {group && <EdgeDrawer key={group.key} group={group} onClose={() => setPicked(null)} />}
    </>
  );
}
