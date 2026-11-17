import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { t } from "./i18n/index.js";
import { KindChip, PIcon, kindOf } from "./PipelineIcons.jsx";
import { branchOwners, cardFlags, countsShort, kindLine, layout, numberText, orphans, placed, rowChangeText, rowsText, snap, stepTitle } from "./pipelineModel.js";

export const NODE = { w: 200, h: 64, gx: 72, gy: 24 };   // the card: 200 x 64, a gap of 72 between columns and 24 between rows
const PAD = 24;
const MIN = 0.25;
const MAX = 2;
const FIT_FLOOR = 0.7;   // opening the graph fits it, but never below 70%: the text stays readable and a wider graph scrolls
const RADIUS = 8;

/** A line from an out-port to an in-port with right-angled bends, each bend rounded by `RADIUS`. */
export function edgePath(x1, y1, x2, y2, r = RADIUS) {
  const dy = y2 - y1;
  if (Math.abs(dy) < 1) return `M${x1} ${y1} H${x2}`;
  const mx = x1 + (x2 - x1) / 2;
  const rr = Math.max(0, Math.min(r, Math.abs(dy) / 2, Math.abs(x2 - x1) / 4));
  const d = dy > 0 ? 1 : -1;
  return `M${x1} ${y1} H${mx - rr} Q${mx} ${y1} ${mx} ${y1 + d * rr} V${y2 - d * rr} Q${mx} ${y2} ${mx + rr} ${y2} H${x2}`;
}

/** What a card says about its step, from what is known: the dot, the bar and the badges. level: ok | warn | bad | idle. */
function stateOf({ node, flags, todo, lost, result }) {
  if (flags.some((f) => f.level === "bad")) return "bad";
  if (flags.some((f) => f.level === "warn") || result?.warn) return "warn";
  if (todo.length || lost) return "idle";
  if (result) return "ok";
  return "idle";
}

/** The pipeline as a left-to-right graph of 200 x 64 cards, laid out by the steps (a click selects the step). It fits the pane when it opens and when the number of steps changes (never
 * zoomed in beyond 100%, never out beyond 70% on its own), and has a zoom pill (zoom out, the level, zoom in, fit); the cards are never cut off. A card shows the step's kind (icon chip), its
 * title, a dot for its state, the rows in and out, how many rows it added or dropped, a count of warnings, "Unconfigured" while the step is not set up, and (after a run) the rows the run
 * wrote there. `issues` is {step id: [what is missing]}, `results` {step id: {rows, warn}}. */
const DRAG_START = 4;   // a press that moves less than this is a click
const placesKey = (place) => `ontopoc.pipeline.places.${place}`;
function readPlaces(place) {
  if (!place) return {};
  try {
    return JSON.parse(window.localStorage.getItem(placesKey(place)) ?? "{}") ?? {};
  } catch {
    return {};
  }
}

export function PipelineGraph({ steps, nodes, selected, onSelect, issues = {}, results = {}, place = null }) {
  // `place` names the pipeline: given, the cards can be dragged and their places are kept in this browser for that pipeline
  const [moved, setMoved] = useState(() => readPlaces(place));
  useEffect(() => setMoved(readPlaces(place)), [place]);
  const keep = (next) => {
    setMoved(next);
    try {
      if (Object.keys(next).length) window.localStorage.setItem(placesKey(place), JSON.stringify(next));
      else window.localStorage.removeItem(placesKey(place));
    } catch { /* storage may be off: the places last for this visit */ }
  };
  const drag = useRef(null);
  const latest = useRef(moved);
  latest.current = moved;
  const lay = placed(layout(steps, NODE), moved);
  const lost = new Set(orphans(steps));
  const owners = branchOwners(steps);
  const { w, h } = lay.size;
  const at = (id) => lay.nodes[id];
  const pane = useRef(null);
  const [k, setK] = useState(1);
  const [fitted, setFitted] = useState(true);   // until the reader zooms, the picture follows the pane
  const full = { w: lay.width + PAD * 2, h: lay.height + PAD * 2 };
  // a movable graph sits in open space a pane wide on every side, so the view can be dragged anywhere and a card can go above or left of the rest
  const [slack, setSlack] = useState({ x: 0, y: 0 });
  const center = useRef(false);
  const fit = useCallback(() => {
    const box = pane.current;
    if (!box || !full.w) return;
    setK(Math.max(FIT_FLOOR, Math.min(1, (box.clientWidth - 2) / full.w, (box.clientHeight - 2) / full.h)));
    if (place) setSlack({ x: box.clientWidth, y: box.clientHeight });
    center.current = true;
    setFitted(true);
  }, [full.w, full.h, place]);
  useLayoutEffect(() => {
    const box = pane.current;
    if (!center.current || !box || !place) return;
    center.current = false;   // after a fit: the picture in the middle of the view (or its left and top edge, when it is bigger)
    box.scrollLeft = slack.x - Math.max(0, (box.clientWidth - full.w * k) / 2);
    box.scrollTop = slack.y - Math.max(0, (box.clientHeight - full.h * k) / 2);
  });
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
  const press = (e, id) => {
    if (!place || e.button !== 0) return;
    const sh = lay.shift ?? { x: 0, y: 0 };   // drag in layout coordinates, before the picture shifts to hold cards above or left of the rest
    drag.current = { id, x0: e.clientX, y0: e.clientY, nx: at(id).x - sh.x, ny: at(id).y - sh.y, moving: false };
    e.stopPropagation();
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const move = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = (e.clientX - d.x0) / k;
    const dy = (e.clientY - d.y0) / k;
    if (!d.moving && Math.hypot(dx, dy) * k < DRAG_START) return;
    if (!d.moving) setFitted(false);   // the zoom holds still while a card is dragged, so the card stays under the pointer
    d.moving = true;
    setMoved((m) => ({ ...m, [d.id]: { x: snap(d.nx + dx), y: snap(d.ny + dy) } }));
  };
  const release = () => {
    const d = drag.current;
    if (d?.moving) {
      d.done = true;
      keep(latest.current);
    }
    if (d && !d.moving) drag.current = null;
  };
  const click = (id) => {
    if (drag.current?.done) {   // the click that ends a drag does not select
      drag.current = null;
      return;
    }
    drag.current = null;
    onSelect(id);
  };
  // when a card goes above or left of the rest the picture grows that way; scroll by as much, so nothing jumps under the pointer
  const sx = lay.shift?.x ?? 0;
  const sy = lay.shift?.y ?? 0;
  const lastShift = useRef({ x: sx, y: sy });
  useLayoutEffect(() => {
    const box = pane.current;
    const prev = lastShift.current;
    lastShift.current = { x: sx, y: sy };
    if (!box || (prev.x === sx && prev.y === sy)) return;
    box.scrollLeft += (sx - prev.x) * k;
    box.scrollTop += (sy - prev.y) * k;
  }, [sx, sy, k]);
  // pressing on the empty canvas and dragging moves the view (the camera); the wheel and the scrollbars still scroll
  const pan = useRef(null);
  const [panning, setPanning] = useState(false);
  const panStart = (e) => {
    if (e.button !== 0 || e.target.closest?.(".pl-node")) return;
    const box = pane.current;
    pan.current = { x0: e.clientX, y0: e.clientY, sl: box.scrollLeft, st: box.scrollTop };
    box.setPointerCapture?.(e.pointerId);
    setPanning(true);
  };
  const panMove = (e) => {
    const p = pan.current;
    if (!p) return;
    pane.current.scrollLeft = p.sl - (e.clientX - p.x0);
    pane.current.scrollTop = p.st - (e.clientY - p.y0);
  };
  const panEnd = () => {
    pan.current = null;
    setPanning(false);
  };
  const anyMoved = Object.keys(moved).some((id) => steps.some((s) => s.id === id));
  const zoom = (factor) => {
    setFitted(false);
    setK((v) => Math.min(MAX, Math.max(MIN, Math.round(v * factor * 100) / 100)));
  };
  const chosen = useRef(null);
  const reveal = useCallback(() => {
    const card = chosen.current;
    const box = pane.current;
    if (!card || !box) return;
    const a = card.getBoundingClientRect();
    const b = box.getBoundingClientRect();
    if (a.left < b.left) box.scrollLeft -= b.left - a.left + PAD;
    else if (a.right > b.right) box.scrollLeft += a.right - b.right + PAD;
    if (a.top < b.top) box.scrollTop -= b.top - a.top + PAD;
    else if (a.bottom > b.bottom) box.scrollTop += a.bottom - b.bottom + PAD;
  }, []);
  const shown = useRef(null);
  useEffect(() => {
    if (shown.current === selected) return undefined;   // a step picked after the graph opened (or the one it opened on) is brought into view
    const first = shown.current === null;
    shown.current = selected;
    if (!first) {
      reveal();
      return undefined;
    }
    const frame = requestAnimationFrame(reveal);   // on opening: after the first fit has been drawn
    return () => cancelAnimationFrame(frame);
  }, [selected, reveal]);
  const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
  const portY = (edge) => {
    const step = byId[edge.to];
    if (step?.type !== "join") return at(edge.to).y + h / 2 + PAD;
    const leftOwner = owners[step.left] ?? step.left;
    return at(edge.to).y + h * (edge.from === leftOwner ? 0.33 : 0.67) + PAD;
  };
  return (
    <div className="graph-area">
      <div className="graph-zoom" role="group" aria-label={t("pipeline.graph.canvas")}>
        <button type="button" onClick={() => zoom(0.8)} aria-label={t("pipeline.graph.zoomOut")} title={t("pipeline.graph.zoomOut")}><PIcon name="minus" /></button>
        <span className="graph-zoom-level" aria-live="polite">{Math.round(k * 100)}%</span>
        <button type="button" onClick={() => zoom(1.25)} aria-label={t("pipeline.graph.zoomIn")} title={t("pipeline.graph.zoomIn")}><PIcon name="plus" /></button>
        <span className="graph-zoom-sep" aria-hidden="true" />
        <button type="button" onClick={fit} aria-label={t("pipeline.graph.fit")} title={t("pipeline.graph.fit")}><PIcon name="fit" /></button>
        {place && anyMoved && <><span className="graph-zoom-sep" aria-hidden="true" /><button type="button" className="graph-reset" onClick={() => keep({})} title={t("pipeline.graph.resetLayoutHint")}>{t("pipeline.graph.resetLayout")}</button></>}
      </div>
      <div className={`graph-pane pannable${panning ? " panning" : ""}`} ref={pane} onPointerDown={panStart} onPointerMove={panMove} onPointerUp={panEnd} onPointerCancel={panEnd} title={t("pipeline.graph.panHint")}>
        <div className="graph-sizer" style={{ width: full.w * k + slack.x * 2, height: full.h * k + slack.y * 2 }}>
          <div className="graph" style={{ width: full.w, height: full.h, transform: `scale(${k})`, transformOrigin: "0 0", left: slack.x, top: slack.y }}>
            <svg width={full.w} height={full.h} aria-hidden="true">
              <defs>
                {[["", "pl-arrow"], ["-on", "pl-arrow pl-arrow-on"]].map(([id, cls]) => (
                  <marker key={id} id={`pl-arrow${id}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto"><path className={cls} d="M0.5 0.5 L7 4 L0.5 7.5 z" /></marker>
                ))}
              </defs>
              {lay.edges.map((e) => {
                const x1 = at(e.from).x + w + PAD;
                const y1 = at(e.from).y + h / 2 + PAD;
                const x2 = at(e.to).x + PAD - 1;
                const y2 = portY(e);
                const on = selected != null && (e.from === selected || e.to === selected);
                const d = edgePath(x1, y1, x2, y2);
                return (
                  <g key={`${e.from}-${e.to}`} className={`pl-edge${on ? " on" : ""}`}>
                    <path className="pl-edge-hit" d={d} />
                    <path className="pl-edge-line" d={d} markerEnd={`url(#pl-arrow${on ? "-on" : ""})`} />
                  </g>
                );
              })}
            </svg>
            {k >= 0.75 && lay.edges.map((e) => {
              const rows = nodes[e.from]?.rows_out;
              if (rows == null) return null;
              const x1 = at(e.from).x + w + PAD;
              const x2 = at(e.to).x + PAD;
              return <span key={`${e.from}-${e.to}`} className="pl-edge-label" style={{ left: (x1 + x2) / 2, top: (at(e.from).y + at(e.to).y) / 2 + h / 2 + PAD }}>{rowsText(rows)}</span>;
            })}
            {steps.map((s) => {
              const node = nodes[s.id];
              const flags = cardFlags(node);
              const todo = issues[s.id] ?? [];
              const result = results[s.id];
              const trouble = flags.filter((f) => f.level !== "note");
              const changed = node?.rows_in?.length > 0 && node.rows_out != null && node.rows_out !== node.rows_in[0];
              const delta = changed ? node.rows_out - node.rows_in[0] : 0;   // "No change" is not worth a badge
              const state = stateOf({ node, flags, todo, lost: lost.has(s.id), result });
              const kind = kindOf(s);
              const isLost = lost.has(s.id);
              const tip = [trouble.map((f) => f.text).join("; "), todo.length ? todo.join("; ") : ""].filter(Boolean).join(" · ");
              return (
                <button key={s.id} ref={selected === s.id ? chosen : null} type="button" title={tip || undefined}
                  className={`pl-node k-${kind} st-${state}${selected === s.id ? " on" : ""}${isLost ? " lost" : ""}${todo.length ? " todo" : ""}${s.type === "input" ? " no-in" : ""}${s.type === "output" ? " no-out" : ""}`}
                  aria-pressed={selected === s.id} style={{ left: at(s.id).x + PAD, top: at(s.id).y + PAD, width: w, height: h, cursor: place ? "grab" : undefined, touchAction: place ? "none" : undefined }}
                  onClick={() => click(s.id)} onPointerDown={(e) => press(e, s.id)} onPointerMove={move} onPointerUp={release} onPointerCancel={release}>
                  {s.type !== "input" && (s.type === "join" ? <><i className="pl-port in" style={{ top: "33%" }} /><i className="pl-port in" style={{ top: "67%" }} /></> : <i className="pl-port in" />)}
                  {s.type !== "output" && <i className="pl-port out" />}
                  <span className="pl-node-top">
                    <KindChip step={s} />
                    <span className="pl-node-text">
                      <span className="pl-node-name">{stepTitle(s, steps)}</span>
                      <span className="pl-node-sub">{kindLine(s)}{isLost && ` · ${t("pipeline.graph.wontRun")}`}</span>
                    </span>
                    <span className={`pl-dot st-${state}`} aria-hidden="true" />
                  </span>
                  <span className="pl-node-foot">
                    <span className="pl-counts">{node ? countsShort(node) : "—"}</span>
                    {delta !== 0 && <span className={`pl-badge ${delta > 0 ? "warn" : "neutral"}`} title={rowChangeText(node)}>{delta > 0 ? "+" : "\u2212"}{numberText(Math.abs(delta))}</span>}
                    {todo.length > 0 && <span className="pl-badge neutral">{t("pipeline.graph.unconfigured")}</span>}
                    {trouble.length > 0 && <span className={`pl-badge ${trouble.some((f) => f.level === "bad") ? "bad" : "warn"}`}><PIcon name="alert" size={11} />{trouble.length}</span>}
                    {result && <span className={`pl-badge ${result.warn ? "warn" : "ok"}`} title={t("pipeline.graph.ranRows", { rows: rowsText(result.rows) })}><PIcon name="check" size={11} />{numberText(result.rows)}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
