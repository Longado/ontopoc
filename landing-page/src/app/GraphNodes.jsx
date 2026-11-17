import React from "react";
import { t } from "./i18n/index.js";
import { KIND_LABEL, KIND_STYLE, STATE_COLOUR, ageText, fitText, labelWidth, leaves, sourceLines, stateTone } from "./graphModel.js";
import { lineLabel, matchRateText } from "./relationModel.js";
import { statusOf } from "./statusModel.js";

const DOT = " · ";
const stateWord = (node) => statusOf(node.state, { modelDraft: node.model_draft }).label;

/** The lines under a node's name: the kind first, then what is worth knowing at a glance. `cause` marks a line that says something needs another look. */
function lines(node) {
  const kind = KIND_LABEL[node.kind];
  if (node.kind === "type") {
    const objects = node.objects == null ? "" : t(node.rows_limited ? "lineage.node.objects_limited" : "lineage.node.objects", { count: node.objects });
    const more = node.stale ? [{ text: t("lineage.node.needs_look", { label: node.stale.label }), cause: true }] : node.state && node.state !== "confirmed" ? [{ text: stateWord(node) }] : [];
    return [{ text: [kind, objects].filter(Boolean).join(DOT) }, ...more];
  }
  if (node.kind === "source") {
    const [first, second] = sourceLines(node);
    return [{ text: `${kind}${DOT}${first.text}`, cause: first.cause }, ...(second ? [{ text: second.text }] : [])];
  }
  if (node.kind === "dataset") {
    return [{ text: [kind, t("lineage.node.version", { version: node.version }), node.uploaded_at ? ageText(node.uploaded_at) : ""].filter(Boolean).join(DOT) }];   // a dataset this person may not open does not say when it came
  }
  if (node.stale) return [{ text: kind }, { text: t("lineage.node.needs_look", { label: node.stale.label }), cause: true }];
  return [{ text: node.state && node.state !== "confirmed" ? `${kind}${DOT}${stateWord(node)}` : kind }];   // an answer is nobody's confirmation: it has no state word
}

/** The words of a node's state, for its tooltip and screen-reader label: the colours of the dot and the bar are never the only sign. */
function stateName(node) {
  if (node.status === "failed") return t("status.failed");
  if (node.stale) return t("lineage.node.needs_look", { label: node.stale.label });
  return node.state || node.model_draft ? stateWord(node) : "";
}

/** One node of either graph, at `box`, as a card: a coloured chip with the kind's icon, the name, a line or two of what matters, and a dot and a bar on the left in the state's colour.
 * A click or Enter picks it. The card is as big as `box` says (the lineage's cards are all one size, the relation graph's types are taller). */
export function GraphNode({ node, box, picked, faded, onPick }) {
  const { w, h } = box;
  const style = KIND_STYLE[node.kind] ?? KIND_STYLE.view;
  const tone = stateTone(node);
  const colour = STATE_COLOUR[tone];
  const shown = lines(node);
  const hint = [KIND_LABEL[node.kind], node.name, stateName(node), node.stale?.root ? t("lineage.cause", { label: node.stale.label, root: node.stale.root }) : ""].filter(Boolean).join(", ");
  const two = shown.length > 1;
  const x = 46;
  const nameY = two ? h / 2 - 6 : h / 2 - 1;
  const metaY = nameY + 15;
  return (
    <g className={`g-node s-${tone}${picked ? " picked" : ""}${faded ? " faded" : ""}`} transform={`translate(${box.x} ${box.y})`} tabIndex={0} role="button" aria-label={hint} aria-pressed={picked}
      onClick={(e) => { e.stopPropagation(); onPick(); }} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}>
      <title>{hint}</title>
      {picked && <rect className="ring" x="-3" y="-3" width={w + 6} height={h + 6} rx="9" />}
      <rect className="card" width={w} height={h} rx="6" />
      <path className="bar" d={`M0 6 A6 6 0 0 1 6 0 H8 V${h} H6 A6 6 0 0 1 0 ${h - 6} Z`} fill={colour} />
      <rect x="16" y={h / 2 - 12} width="24" height="24" rx="5" fill={style.colour} />
      <path className="glyph" d={style.icon} transform={`translate(${16 + 5} ${h / 2 - 12 + 5}) scale(0.58)`} />
      <circle cx={w - 14} cy="14" r="4" fill={colour} />
      <text className="name" x={x} y={nameY}>{fitText(node.name, w - x - 28, 13)}</text>
      {shown.map((l, i) => <text key={i} className={`meta${l.cause ? " cause" : ""}`} x={x} y={metaY + i * 14}>{fitText(l.text, w - x - 10, 11)}</text>)}
    </g>
  );
}

const colour = (state) => (state === "needs_look" ? "amber" : state === "rejected" ? "red" : "grey");

/** A line between two types of the relation graph (`part` "line" or "label" draws only that half, so a graph can draw every label above every line): the rows that connect on it, an arrow toward the "one" side, dashed when the cardinality does not hold. Several relations
 * between the same two types are one line with a count. */
export function RelationLine({ group, from, to, picked, faded, lit, onPick, labelAt, part }) {
  const a = leaves(from, to);
  const b = leaves(to, from);
  const [first] = group.edges;
  const many = group.edges.length > 1;
  const failing = group.edges.some((e) => e.cardinality_ok === false);
  const state = group.edges.find((e) => e.state === "needs_look") ? "needs_look" : first.state;
  const label = lineLabel(group);   // the relation's short name; the match rate is in the drawer and the tooltip
  const width = labelWidth(label);
  const mx = labelAt?.x ?? (a.x + b.x) / 2;   // the relation graph places labels clear of the boxes; the lineage has none
  const my = labelAt?.y ?? (a.y + b.y) / 2;
  const toward = !many && first.arrow_to ? (first.arrow_to === group.to ? "marker-end" : "marker-start") : null;
  const marker = lit ? "blue" : colour(state);
  return (
    <g className={`g-edge s-${state}${failing && !many ? " dashed" : ""}${lit ? " lit" : ""}${picked ? " picked" : ""}${faded ? " faded" : ""}`} tabIndex={0} role="button" aria-label={t("lineage.line.aria", { from: first.from_name, to: first.to_name, label })}
      onClick={(e) => { e.stopPropagation(); onPick(); }} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}>
      {part !== "label" && <line className="line" x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...(toward ? { [toward === "marker-end" ? "markerEnd" : "markerStart"]: `url(#arrow-${marker})` } : {})} />}
      {part !== "label" && <line className="hit" x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth="20" pointerEvents="stroke" style={{ cursor: "pointer" }} />}
      <title>{many ? label : t("lineage.line.title", { name: first.name, rate: matchRateText(first) })}</title>
      {part !== "line" && <rect className="pill" x={mx - width / 2} y={my - 11} width={width} height="22" rx="4" />}
      {part !== "line" && <text x={mx} y={my + 4} textAnchor="middle">{label}</text>}
    </g>
  );
}

/** A line of the lineage: from the right side of what is read to the left side of what reads it. */
export function FlowLine({ from, to, lit, faded }) {
  const x1 = from.x + from.w;
  const y1 = from.y + from.h / 2;
  const x2 = to.x;
  const y2 = to.y + to.h / 2;
  const bend = Math.max(24, (x2 - x1) / 2);
  return (
    <g className={`g-edge flow${lit ? " lit" : ""}${faded ? " faded" : ""}`}>
      <path className="line" d={`M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}`} markerEnd={`url(#arrow-${lit ? "blue" : "grey"})`} />
    </g>
  );
}
