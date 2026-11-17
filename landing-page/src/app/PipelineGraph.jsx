import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { cardFlags, countsText, kindLine, layout, numberText, orphans, rowChangeText, stepTitle } from "./pipelineModel.js";
import { Icon } from "./ui/Icon.jsx";

const PAD = 16;
const MIN = 0.4;
const MAX = 1.6;

/** The pipeline as a left-to-right graph of cards, laid out by the steps (a click selects the step). It fits the pane when it opens and when the number of steps changes, and has
 * zoom in, zoom out and 适应 buttons; the cards are never cut off. Each card shows rows in → rows out, how many rows it added or dropped, a warning icon when something is off,
 * 待配置 while the step is not set up, and (after a run) the rows the run wrote there. `issues` is {step id: [what is missing]}, `results` {step id: {rows, warn}}. */
export function PipelineGraph({ steps, nodes, selected, onSelect, issues = {}, results = {} }) {
  const lay = layout(steps);
  const lost = new Set(orphans(steps));
  const { w, h } = lay.size;
  const at = (id) => lay.nodes[id];
  const pane = useRef(null);
  const [k, setK] = useState(1);
  const [fitted, setFitted] = useState(true);   // until the reader zooms, the picture follows the pane
  const full = { w: lay.width + PAD * 2, h: lay.height + PAD * 2 };
  const fit = useCallback(() => {
    const box = pane.current;
    if (!box || !full.w) return;
    setK(Math.max(MIN, Math.min(1, (box.clientWidth - 2) / full.w, (box.clientHeight - 2) / full.h)));
    setFitted(true);
  }, [full.w, full.h]);
  useLayoutEffect(() => {
    if (fitted) fit();
  }, [fit, fitted, steps.length]);
  useEffect(() => {
    const box = pane.current;
    if (!box || typeof ResizeObserver === "undefined") return undefined;
    const watch = new ResizeObserver(() => fitted && fit());
    watch.observe(box);
    return () => watch.disconnect();
  }, [fit, fitted]);
  const zoom = (factor) => {
    setFitted(false);
    setK((v) => Math.min(MAX, Math.max(MIN, Math.round(v * factor * 100) / 100)));
  };
  const chosen = useRef(null);
  const shown = useRef(selected);
  useEffect(() => {
    if (shown.current === selected) return;   // a step picked after the graph opened is brought into view
    shown.current = selected;
    const card = chosen.current;
    const box = pane.current;
    if (!card || !box) return;
    const a = card.getBoundingClientRect();
    const b = box.getBoundingClientRect();
    if (a.left < b.left) box.scrollLeft -= b.left - a.left + PAD;
    else if (a.right > b.right) box.scrollLeft += a.right - b.right + PAD;
    if (a.top < b.top) box.scrollTop -= b.top - a.top + PAD;
    else if (a.bottom > b.bottom) box.scrollTop += a.bottom - b.bottom + PAD;
  }, [selected]);
  return (
    <div className="graph-area">
      <div className="graph-zoom" role="group" aria-label="画布">
        <button className="secondary" onClick={() => zoom(0.8)} aria-label="缩小">−</button>
        <span className="muted small" aria-live="polite">{Math.round(k * 100)}%</span>
        <button className="secondary" onClick={() => zoom(1.25)} aria-label="放大">+</button>
        <button className="secondary" onClick={fit}>适应</button>
      </div>
      <div className="graph-pane" ref={pane}>
        <div className="graph-sizer" style={{ width: full.w * k, height: full.h * k }}>
          <div className="graph" style={{ width: full.w, height: full.h, transform: `scale(${k})`, transformOrigin: "0 0" }}>
            <svg width={full.w} height={full.h} aria-hidden="true">
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
              const todo = issues[s.id] ?? [];
              const result = results[s.id];
              const trouble = flags.some((f) => f.level !== "note");
              const change = rowChangeText(node);
              return (
                <button key={s.id} ref={selected === s.id ? chosen : null} type="button" className={`card-node${selected === s.id ? " on" : ""}${lost.has(s.id) ? " lost" : ""}${todo.length ? " todo" : ""}`} aria-pressed={selected === s.id}
                  style={{ left: at(s.id).x + PAD, top: at(s.id).y + PAD, width: w, height: h }} onClick={() => onSelect(s.id)}>
                  <span className="card-kind">{kindLine(s)}{lost.has(s.id) && "，不会运行"}{todo.length > 0 && <span className="card-todo">待配置</span>}{trouble && <span className="card-warn" title={flags.filter((f) => f.level !== "note").map((f) => f.text).join("；")}><Icon name="alert" size={14} /></span>}</span>
                  <span className="card-title">{stepTitle(s, steps)}</span>
                  <span className="card-counts">{node ? countsText(node) : "—"}{change && <span className="card-delta"> {change}</span>}</span>
                  {todo.length > 0 ? <span className="card-flag flag-todo">{todo[0]}</span> : flags.slice(0, 1).map((f, i) => <span key={i} className={`card-flag flag-${f.level}`}>{f.text}</span>)}
                  {result && <span className={`card-ran${result.warn ? " warn" : ""}`}><Icon name="check" size={12} /> 运行：{numberText(result.rows)} 行</span>}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
