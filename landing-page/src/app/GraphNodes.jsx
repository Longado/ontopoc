import React from "react";
import { KIND_LABEL, SIZE, ageText, edgeLabel, fitText, leaves } from "./graphModel.js";
import { stateText } from "./typeModel.js";

const stateClass = (node) => `s-${node.model_draft ? "proposed" : node.state ?? "none"}`;

function secondLine(node) {
  if (node.stale) return { text: `需再看，${node.stale.label}`, cause: true };
  return { text: stateText(node), word: node.state };
}

function lines(node) {
  if (node.kind === "type") {
    const objects = node.objects == null ? "" : node.rows_limited ? `你能看到 ${node.objects} 个对象` : `${node.objects} 个对象`;
    return [{ text: objects }, secondLine(node)];
  }
  if (node.kind === "dataset") return [{ text: `第 ${node.version} 版` }, { text: `上传于 ${ageText(node.uploaded_at)}` }];
  return [node.stale ? { text: node.stale.label, cause: true } : { text: `${KIND_LABEL[node.kind]} ${stateText(node)}`, word: node.state }];
}

/** One node of either graph, at `box`: a type is a card with a header, a dataset a flat box, the rest small boxes. A click or Enter picks it. */
export function GraphNode({ node, box, picked, faded, onPick }) {
  const { w, h } = SIZE[node.kind];
  const inner = w - 24;
  const kindClass = node.kind === "dataset" ? "dataset" : "";
  const shown = lines(node);
  const hint = [KIND_LABEL[node.kind], node.name, node.stale ? `${node.stale.label}${node.stale.root ? `：${node.stale.root}` : ""}` : ""].filter(Boolean).join("，");
  return (
    <g className={`g-node ${stateClass(node)} ${kindClass}${picked ? " picked" : ""}${faded ? " faded" : ""}`} transform={`translate(${box.x} ${box.y})`} tabIndex={0} role="button" aria-label={hint} aria-pressed={picked}
      onClick={(e) => { e.stopPropagation(); onPick(); }} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}>
      <title>{hint}</title>
      <rect className="box" width={w} height={h} rx={node.kind === "dataset" ? 2 : 6} />
      {node.kind === "type" ? (
        <>
          <path className="head" d={`M0 24 V6 a6 6 0 0 1 6 -6 H${w - 6} a6 6 0 0 1 6 6 V24 Z`} />
          <text className="name" x="12" y="17">{fitText(node.name, inner, 14)}</text>
          {shown.map((l, i) => <text key={i} className={l.cause ? "cause" : `line${l.word ? ` word-${l.word}` : ""}`} x="12" y={41 + i * 15}>{fitText(l.text, inner, 12)}</text>)}
        </>
      ) : (
        <>
          <text className="name" x="12" y="21">{fitText(node.name, inner, 14)}</text>
          {shown.map((l, i) => <text key={i} className={l.cause ? "cause" : `line${l.word ? ` word-${l.word}` : ""}`} x="12" y={h - 12 - (shown.length - 1 - i) * 15}>{fitText(l.text, inner, 12)}</text>)}
        </>
      )}
    </g>
  );
}

const colour = (state) => (state === "needs_look" ? "amber" : state === "rejected" ? "red" : "grey");

/** A line between two types of the relation graph: the rows that connect on it, an arrow toward the "one" side, dashed when the cardinality does not hold. Several relations
 * between the same two types are one line with a count. */
export function RelationLine({ group, from, to, picked, faded, lit, onPick }) {
  const a = leaves(from, to);
  const b = leaves(to, from);
  const [first] = group.edges;
  const many = group.edges.length > 1;
  const failing = group.edges.some((e) => e.cardinality_ok === false);
  const state = group.edges.find((e) => e.state === "needs_look") ? "needs_look" : first.state;
  const label = many ? `${group.edges.length} 个关系` : edgeLabel(first);
  const width = Math.max(56, [...label].length * 12 + 16);
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const toward = !many && first.arrow_to ? (first.arrow_to === group.to ? "marker-end" : "marker-start") : null;
  const marker = lit ? "blue" : colour(state);
  return (
    <g className={`g-edge s-${state}${failing && !many ? " dashed" : ""}${lit ? " lit" : ""}${picked ? " picked" : ""}${faded ? " faded" : ""}`} tabIndex={0} role="button" aria-label={`${first.from_name} 和 ${first.to_name}：${label}`}
      onClick={(e) => { e.stopPropagation(); onPick(); }} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}>
      <line className="line" x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...(toward ? { [toward === "marker-end" ? "markerEnd" : "markerStart"]: `url(#arrow-${marker})` } : {})} />
      <line className="hit" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
      <rect className="pill" x={mx - width / 2} y={my - 11} width={width} height="22" rx="4" />
      <text x={mx} y={my + 4} textAnchor="middle">{label}</text>
    </g>
  );
}

/** A line of the lineage: from the right side of what is read to the left side of what reads it. */
export function FlowLine({ from, to, lit, faded }) {
  const x1 = from.x + from.w;
  const y1 = from.y + from.h / 2;
  const x2 = to.x;
  const y2 = to.y + to.h / 2;
  const bend = Math.max(30, (x2 - x1) / 2);
  return (
    <g className={`g-edge${lit ? " lit" : ""}${faded ? " faded" : ""}`}>
      <path className="line" d={`M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}`} markerEnd={`url(#arrow-${lit ? "blue" : "grey"})`} />
    </g>
  );
}
