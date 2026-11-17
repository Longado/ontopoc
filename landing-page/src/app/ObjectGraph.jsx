import React, { useMemo, useState } from "react";
import { useT } from "./i18n/index.js";
import { GraphCanvas } from "./GraphCanvas.jsx";
import { nodeLines, objectGraphLayout } from "./objectGraphModel.js";

/** A SELECT GRAPH answer: the start objects on the left, what they reach to the right, each edge named by its relation. Picking an object lights its edges. */
export function ObjectGraph({ graph }) {
  const t = useT();
  const layout = useMemo(() => objectGraphLayout(graph), [graph]);
  const [picked, setPicked] = useState(null);
  const touches = (e) => picked && (e.from === picked || e.to === picked);
  const near = picked ? new Set(graph.edges.filter(touches).flatMap((e) => [e.from, e.to])) : null;
  return (
    <div className="object-graph">
      <GraphCanvas width={layout.width} height={layout.height} label={t("ask.graph.label")} fileName={t("ask.graph.file")} onBlank={() => setPicked(null)}>
        {graph.edges.map((e) => {
          const a = layout.boxes[e.from];
          const b = layout.boxes[e.to];
          if (!a || !b) return null;
          const forward = a.x <= b.x;   // drawn left to right; the arrow still points the way the relation does
          const [l, r] = forward ? [a, b] : [b, a];
          const x1 = l.x + l.w;
          const y1 = l.y + l.h / 2;
          const x2 = r.x;
          const y2 = r.y + r.h / 2;
          const bend = Math.max(30, (x2 - x1) / 2);
          const lit = touches(e);
          const marker = `url(#arrow-${lit ? "blue" : "grey"})`;
          return (
            <g key={`${e.from}>${e.to}>${e.relation}`} className={`g-edge${lit ? " lit" : ""}${picked && !lit ? " faded" : ""}`}>
              <title>{e.name}</title>
              <path className="line" d={`M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}`} {...(forward ? { markerEnd: marker } : { markerStart: marker })} />
            </g>
          );
        })}
        {graph.nodes.map((n) => {
          const box = layout.boxes[n.id];
          const [first, second] = nodeLines(n);
          return (
            <g key={n.id} className={`g-node${n.start ? " s-confirmed" : ""}${picked === n.id ? " picked" : ""}${near && !near.has(n.id) ? " faded" : ""}`}
              transform={`translate(${box.x} ${box.y})`} tabIndex={0} role="button" aria-label={`${first}, ${second}`}
              onClick={() => setPicked(picked === n.id ? null : n.id)} onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setPicked(picked === n.id ? null : n.id); } }}>
              <title>{`${n.type_name} ${n.key}${n.name ? `: ${n.name}` : ""}`}</title>
              <rect className="box" width={box.w} height={box.h} rx="6" />
              <text className="name" x="10" y="20">{first.length > 12 ? `${first.slice(0, 11)}…` : first}</text>
              <text className="line" x="10" y="38">{second.length > 16 ? `${second.slice(0, 15)}…` : second}</text>
            </g>
          );
        })}
      </GraphCanvas>
    </div>
  );
}
