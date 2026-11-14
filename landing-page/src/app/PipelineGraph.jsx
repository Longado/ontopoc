import React, { useEffect, useRef } from "react";
import { cardFlags, countsText, kindLine, layout, orphans, stepTitle } from "./pipelineModel.js";

const PAD = 16;

/** The pipeline as a left-to-right graph of cards, laid out by the steps (read-only: a click selects the step). Each card shows rows in → rows out and what went wrong in it. */
export function PipelineGraph({ steps, nodes, selected, onSelect }) {
  const lay = layout(steps);
  const lost = new Set(orphans(steps));
  const { w, h } = lay.size;
  const at = (id) => lay.nodes[id];
  const chosen = useRef(null);
  const shown = useRef(selected);
  useEffect(() => {
    if (shown.current === selected) return;   // the graph opens at its left edge, with the first card whole; only a step picked afterwards is brought into view
    shown.current = selected;
    const card = chosen.current;
    const pane = card?.closest(".pl-graph");
    if (!card || !pane) return;
    const left = card.offsetLeft;
    const right = left + card.offsetWidth;
    if (left < pane.scrollLeft) pane.scrollLeft = Math.max(0, left - PAD);
    else if (right > pane.scrollLeft + pane.clientWidth) pane.scrollLeft = right - pane.clientWidth + PAD;
  }, [selected]);
  return (
    <div className="graph-scroll">
      <div className="graph" style={{ width: lay.width + PAD * 2, height: lay.height + PAD * 2 }}>
        <svg width={lay.width + PAD * 2} height={lay.height + PAD * 2} aria-hidden="true">
          {lay.edges.map((e) => {
            const x1 = at(e.from).x + w + PAD;
            const y1 = at(e.from).y + h / 2 + PAD;
            const x2 = at(e.to).x + PAD;
            const y2 = at(e.to).y + h / 2 + PAD;
            const mid = (x1 + x2) / 2;
            return <path key={`${e.from}-${e.to}`} d={`M${x1} ${y1} C${mid} ${y1} ${mid} ${y2} ${x2} ${y2}`} />;
          })}
        </svg>
        {steps.map((s) => {
          const node = nodes[s.id];
          const flags = cardFlags(node);
          return (
            <button key={s.id} ref={selected === s.id ? chosen : null} type="button" className={`card-node${selected === s.id ? " on" : ""}${lost.has(s.id) ? " lost" : ""}`} aria-pressed={selected === s.id}
              style={{ left: at(s.id).x + PAD, top: at(s.id).y + PAD, width: w, height: h }} onClick={() => onSelect(s.id)}>
              <span className="card-kind">{kindLine(s)}{lost.has(s.id) && "，不会运行"}</span>
              <span className="card-title">{stepTitle(s, steps)}</span>
              <span className="card-counts">{node ? countsText(node) : "—"}</span>
              {flags.slice(0, 2).map((f, i) => <span key={i} className={`card-flag flag-${f.level}`}>{f.text}</span>)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
