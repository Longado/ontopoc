import React, { useMemo, useState } from "react";
import { getRelationGraph } from "./api.js";
import { NodeDrawer } from "./GraphDrawer.jsx";
import { GraphCanvas } from "./GraphCanvas.jsx";
import { GraphNode, RelationLine } from "./GraphNodes.jsx";
import { LEGEND, connectedMeaning, forceLayout, groupEdges, labelWidth, neighbours, placeLabels, verdictText } from "./graphModel.js";
import { t } from "./i18n/index.js";
import { CARDINALITY_LABEL, keyPairText, lineLabel, matchRateText, sentBackLine } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { useLoad } from "./useLoad.js";
import { Drawer } from "./ui/Drawer.jsx";

/** What the colours and the numbers on the graph mean. */
function Legend({ example }) {
  return (
    <div className="graph-legend" aria-label={t("relations.graph.legend")}>
      <h2 className="rel-legend-title">{t("relations.graph.title")}</h2>
      <p className="muted small">{t("relations.graph.legendBoxes")}</p>
      <ul>
        {LEGEND.map((l) => (
          <li key={l.key}><span className="swatch" style={{ background: l.colour }} aria-hidden="true" /><strong>{l.word}</strong> <span className="muted">{l.text}</span></li>
        ))}
      </ul>
      <p className="muted small">{t("relations.graph.legendLines")}</p>
      <p className="muted small"><strong>{t("relations.graph.clickLine")}</strong>{t("relations.graph.legendRest")}{example ? t("relations.graph.example", { text: connectedMeaning(example) }) : ""}{t("relations.graph.legendEnd")}</p>
    </div>
  );
}

/** The drawer a picked line opens: each relation between the two types, what it connects, whether its cardinality holds, and the way to its page. */
function EdgeDrawer({ group, onClose }) {
  const [first] = group.edges;
  return (
    <Drawer open title={t("relations.graph.edgeTitle", { from: first.from_name, to: first.to_name })} onClose={onClose} width={440}>
      {group.edges.map((e) => (
        <section key={e.id} className="edge-card">
          <h3><a href={hrefFor({ page: "relation", id: e.key })}>{e.name}</a> <State item={e} /></h3>
          <p className="muted">{t("relations.graph.edgeEnds", { from: e.from_name, to: e.to_name, cardinality: CARDINALITY_LABEL[e.cardinality] ?? e.cardinality_label })}</p>
          <p className="muted small">{keyPairText(e)}</p>
          <p><strong>{matchRateText(e)}</strong></p>
          <p className="muted small">{connectedMeaning(e)}</p>
          {verdictText(e) && <p className={e.cardinality_ok === false ? "warn" : "muted small"}>{verdictText(e)}</p>}
          {sentBackLine(e) && <p className="warn">{sentBackLine(e)}</p>}
          {e.stale && <div className="reason"><strong>{e.stale.label}{e.stale.root ? `${t("types.colon")} ${e.stale.root}` : ""}</strong><p>{e.stale.text ?? e.stale.text_hidden}</p></div>}
          <p><a className="button secondary" href={hrefFor({ page: "relation", id: e.key })}>{e.state === "confirmed" ? t("relations.graph.details") : t("relations.graph.review")}</a></p>
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
  if (!graph) return <p className="muted">{t("common.loading")}</p>;
  if (!graph.nodes.length && graph.hidden_types > 0) return <p className="muted">{t("relations.graph.hidden", { count: graph.hidden_types })}</p>;
  if (!graph.nodes.length) return <p className="muted">{t("relations.graph.none")} <a href={hrefFor({ page: "types" })}>{t("relations.graph.toTypes")}</a></p>;
  const group = picked?.kind === "edge" ? groups.find((g) => g.key === picked.id) : null;
  const node = picked?.kind === "node" ? graph.nodes.find((n) => n.id === picked.id) : null;
  const lit = group ? new Set([group.from, group.to]) : node ? neighbours(node.id, graph.edges) : null;
  return (
    <>
      <p className="muted rel-intro">{t("relations.graph.intro")}</p>
      <div className={`graph-layout rel-graph${node ? " with-drawer" : ""}`}>
        <GraphCanvas width={layout.width} height={layout.height} label={t("relations.graph.canvas")} fileName={t("relations.graph.file")} onBlank={() => setPicked(null)}>
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
