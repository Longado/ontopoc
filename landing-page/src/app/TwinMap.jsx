import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { fitView, fitText, STATE_COLOUR } from "./graphModel.js";
import { CARD, GROUP, TWIN_STYLE, cardFacts, centreOn, minimapScale } from "./lineageModel.js";
import { useT } from "./i18n/index.js";
import { stepTitle } from "./pipelineModel.js";

// The map's styles live inside the SVG, so the picture exported from it looks like the one on the page (a stand-alone SVG has no page CSS and no custom properties).
export const STYLE = `
text { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; fill: #1c2127; }
[data-export-only] { display: none; }
.tw-node { cursor: pointer; }
.tw-node.inert { cursor: grab; }
.tw-node .card { fill: #fff; stroke: #d3d8de; stroke-width: 1; }
.tw-node:hover .card { stroke: #abb3bf; }
.tw-node.s-needs_look .card { stroke: #c87619; stroke-width: 1.5; }
.tw-node.s-rejected .card { stroke: #cd4246; stroke-width: 1.5; }
.tw-node.picked .card, .tw-node.picked .box { stroke: #2d72d2; stroke-width: 2; }
.tw-node .ring { fill: none; stroke: rgba(45, 114, 210, 0.28); stroke-width: 4; }
.tw-node .tint { fill: #fdf1e0; }
.tw-node .glyph { fill: none; stroke: #fff; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
.tw-node .name { font-size: 12px; font-weight: 600; fill: #fff; }
.tw-node .stat { font-size: 11px; fill: #1c2127; font-variant-numeric: tabular-nums; }
.tw-node .stat-icon { fill: none; stroke: #8f99a8; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.tw-node .sub { font-size: 11px; fill: #5f6b7c; }
.tw-node .note { font-size: 11px; font-weight: 600; fill: #77450d; }
.tw-node .dot { stroke: #fff; stroke-width: 1.5; }
.tw-node .box { fill: #e6f6f4; stroke: #9fd8d2; stroke-width: 1; }
.tw-node.s-needs_look .box { stroke: #c87619; stroke-width: 1.5; }
.tw-node .box-name { font-size: 12px; font-weight: 600; fill: #00706a; }
.tw-node .step { fill: #fff; stroke: #cfe7e4; stroke-width: 1; }
.tw-node .step-text { font-size: 11px; fill: #1c2127; }
.tw-node:focus { outline: none; }
.tw-node:focus-visible .card, .tw-node:focus-visible .box { stroke: #2d72d2; stroke-width: 2; }
.tw-node.faded { opacity: 0.22; }
.tw-edge .line { fill: none; stroke: #b4bcc7; stroke-width: 1.4; }
.tw-edge.s-needs_look .line { stroke: #c87619; stroke-dasharray: 6 4; }
.tw-edge.s-rejected .line { stroke: #cd4246; stroke-dasharray: 6 4; }
.tw-edge.lit .line { stroke: #2d72d2; stroke-width: 2; stroke-dasharray: none; }
.tw-edge.faded { opacity: 0.12; }
.tw-colhead { font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; fill: #5f6b7c; }
.tw-colcount { font-size: 11px; fill: #8f99a8; }
.tw-colrule { stroke: #edeff2; stroke-width: 1; }
`;

const MARKERS = { grey: "#b4bcc7", amber: "#c87619", red: "#cd4246", blue: "#2d72d2" };
const STEP_COLOUR = { input: "#2d72d2", join: "#7961db", transform: "#5f6b7c", filter: "#00a396", llm: "#d33d17", union: "#9d3f9d", split: "#db2c6f", output: "#238551", branch: "#db2c6f" };
const STAT_ICON = {
  columns: "M4 5h16v14H4zM10 5v14M16 5v14",
  rows: "M4 7h16M4 12h16M4 17h16",
  objects: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
  properties: "M4 6h16M4 12h10M4 18h6",
  tables: "M4 5h16v14H4zM4 10h16M10 5v14",
};
const ICONS = {
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  fit: "M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4",
  pointer: "M5 3l14 8-6 2-3 6z",
  hand: "M8 13V5.5a1.5 1.5 0 013 0V11M11 11V4a1.5 1.5 0 013 0v7M14 11V5.5a1.5 1.5 0 013 0V13M17 9.5a1.5 1.5 0 013 0V15a6 6 0 01-6 6h-1.5a6 6 0 01-4.7-2.3L4.5 15a1.6 1.6 0 012.4-2.1L8 14",
  curve: "M3 18c6 0 4-12 9-12s3 12 9 12",
  straight: "M4 19L20 5",
  expand: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  collapse: "M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5",
  download: "M12 4v11M7 11l5 5 5-5M5 20h14",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
  eyeoff: "M3 3l18 18M10.6 5.1A9.7 9.7 0 0112 5c6 0 10 7 10 7a17 17 0 01-3.2 3.9M6.6 6.7C3.8 8.5 2 12 2 12s4 7 10 7c1.6 0 3-.4 4.3-1M9.9 9.9a3 3 0 004.2 4.2",
  trace: "M4 6h5v5H4zM15 13h5v5h-5zM9 8.5h3a2 2 0 012 2V13",
  close: "M6 6l12 12M18 6L6 18",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  map: "M9 4L3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14",
};
export const Icon = ({ name, size = 16 }) => <svg className="tw-icon" viewBox="0 0 24 24" width={size} height={size} aria-hidden="true"><path d={ICONS[name]} /></svg>;

/** The pan and zoom of a map: `content` is {width, height}. The map is fitted (readable: not below 70%, not above 100%) when it arrives and when its frame changes, until the reader moves it. */
export function useViewport(content) {
  const [el, setEl] = useState(null);
  const [size, setSize] = useState({ w: 900, h: 560 });
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const touched = useRef(false);
  useLayoutEffect(() => {
    if (!el) return undefined;
    const watch = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }));
    watch.observe(el);
    return () => watch.disconnect();
  }, [el]);
  const fit = useCallback(() => {
    touched.current = false;
    const v = fitView({ w: size.w, h: size.h }, { width: content.width, height: content.height, top: 0 }, "readable");
    setView({ ...v, y: 8 });
  }, [size.w, size.h, content.width, content.height]);
  useEffect(() => { if (!touched.current) fit(); }, [fit]);   // eslint-disable-line react-hooks/exhaustive-deps -- fitted again by a new map or frame, never over the reader's own zoom
  const zoom = useCallback((factor, cx = size.w / 2, cy = size.h / 2) => {
    touched.current = true;
    setView((v) => {
      const k = Math.min(2, Math.max(0.2, v.k * factor));
      return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
    });
  }, [size.w, size.h]);
  const move = useCallback((next) => { touched.current = true; setView(next); }, []);
  const centre = useCallback((box, k) => move(centreOn(size, box, k ?? Math.max(view.k, 0.8))), [size, view.k, move]);
  /** Brings a box into view (without moving the picture when it is already in the frame). */
  const reveal = useCallback((box) => {
    setView((v) => {
      const left = v.x + box.x * v.k;
      const top = v.y + box.y * v.k;
      const inside = left >= 8 && top >= 8 && left + box.w * v.k <= size.w - 8 && top + box.h * v.k <= size.h - 8;
      if (inside) return v;
      touched.current = true;
      return centreOn(size, box, v.k);
    });
  }, [size]);
  return { setEl, size, view, fit, zoom, move, centre, reveal, percent: Math.round(view.k * 100) };
}

/** The drawing surface: an SVG in a frame the viewport measures, with the wheel moving the picture (Ctrl or Cmd zooms) and the background (or, in hand mode, anything) dragging it. */
export function TwinSvg({ viewport, content, mode, onBlank, svgRef, label, children, overlay }) {
  const { view, move, zoom, setEl } = viewport;
  const drag = useRef(null);
  const swallow = useRef(false);
  const local = useRef(null);
  const ref = svgRef ?? local;
  useEffect(() => {
    const el = ref.current;
    const wheel = (e) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        const r = el.getBoundingClientRect();
        zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top);
      } else move({ ...view, x: view.x - e.deltaX, y: view.y - e.deltaY });
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [zoom, move, view, ref]);
  const down = (e) => {
    if (e.button !== 0 || (!e.target.hasAttribute("data-bg") && mode !== "hand")) return;
    drag.current = { x: e.clientX, y: e.clientY, view, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const moveTo = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    if (d.moved) move({ ...d.view, x: d.view.x + dx, y: d.view.y + dy });
  };
  const up = () => {
    const d = drag.current;
    if (d && !d.moved) onBlank?.();
    swallow.current = Boolean(d?.moved);
    drag.current = null;
  };
  return (
    <div className={`tw-canvas${mode === "hand" ? " hand" : ""}`} ref={setEl}>
      <svg ref={ref} width="100%" height="100%" role="group" aria-label={label} onPointerDown={down} onPointerMove={moveTo} onPointerUp={up} onPointerCancel={() => { drag.current = null; }}
        onClickCapture={(e) => { if (swallow.current) { e.stopPropagation(); swallow.current = false; } }}>
        <style>{STYLE}</style>
        <defs>
          {Object.entries(MARKERS).map(([name, colour]) => (
            <marker key={name} id={`tw-arrow-${name}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto" markerUnits="userSpaceOnUse"><path d="M1 1L9 5L1 9z" fill={colour} /></marker>
          ))}
        </defs>
        <rect data-bg width="100%" height="100%" fill="#f6f7f9" />
        <g data-view transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>{children}</g>
      </svg>
      {overlay}
    </div>
  );
}

/** The column headings and the faint rule between columns, drawn in the map's own space. */
export function Columns({ layout }) {
  return (
    <g aria-hidden="true">
      {layout.columns.map((c, i) => (
        <g key={c.key + c.x}>
          <text className="tw-colhead" x={c.x} y={24}>{c.label}</text>
          <text className="tw-colcount" x={c.x + c.w} y={24} textAnchor="end">{c.count}</text>
          {i > 0 && <path className="tw-colrule" d={`M${c.x - 38} 10 V${layout.height - 10}`} />}
        </g>
      ))}
    </g>
  );
}

/** A link from the right of one box to the left of the next, curved or straight; amber or red when a node at either end needs a look, blue when it lies on the picked path. */
export function TwinEdge({ from, to, tone, lit, faded, curved }) {
  const x1 = from.x + from.w;
  const y1 = from.y + from.h / 2;
  const x2 = to.x;
  const y2 = to.y + to.h / 2;
  const bend = Math.max(28, (x2 - x1) / 2);
  const d = curved ? `M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}` : `M${x1} ${y1} L${x2} ${y2}`;
  const marker = lit ? "blue" : tone === "needs_look" ? "amber" : tone === "rejected" ? "red" : "grey";
  return (
    <g className={`tw-edge s-${tone}${lit ? " lit" : ""}${faded ? " faded" : ""}`}>
      <path className="line" d={d} markerEnd={`url(#tw-arrow-${marker})`} />
    </g>
  );
}

function Stat({ stat, x, y, max }) {
  const t = useT();
  return (
    <g>
      <g transform={`translate(${x} ${y - 9}) scale(0.5)`}><path className="stat-icon" d={STAT_ICON[stat.key]} /></g>
      <text className="stat" x={x + 16} y={y}>{fitText(t(`lineage.twin.stat.${stat.key}`, { count: stat.n, value: stat.value }), max, 11)}</text>
    </g>
  );
}

/** One node of the map. A pipeline is a tinted group box holding a row for each step; everything else is a compact card: a coloured header with the kind's icon and the name, the numbers
 * that matter (columns and rows of a dataset, objects of a type), and a line that says when it needs another look. The dot on the header is its state. */
export function TwinNode({ node, box, picked, faded, interactive = true, onPick }) {
  const t = useT();
  const { w, h } = box;
  const style = TWIN_STYLE[node.kind] ?? TWIN_STYLE.view;
  const facts = cardFacts(node);
  const colour = STATE_COLOUR[facts.tone];
  const hint = [t(`lineage.kind.${node.kind}`), node.name, facts.note, node.stale?.root ? t("lineage.cause", { label: node.stale.label, root: node.stale.root }) : ""].filter(Boolean).join(", ");
  const group = node.kind === "pipeline" && node.steps?.length;
  const act = (e) => { e.stopPropagation(); if (interactive) onPick(); };
  return (
    <g className={`tw-node s-${facts.tone}${picked ? " picked" : ""}${faded ? " faded" : ""}${interactive ? "" : " inert"}`} data-node={node.id} transform={`translate(${box.x} ${box.y})`} tabIndex={0} role="button" aria-label={hint} aria-pressed={picked}
      onClick={act} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}>
      <title>{hint}</title>
      {picked && <rect className="ring" x="-3" y="-3" width={w + 6} height={h + 6} rx={group ? 11 : 9} />}
      {group ? (
        <>
          <rect className="box" width={w} height={h} rx="8" />
          <g transform="translate(10 8) scale(0.58)"><path className="glyph" style={{ stroke: "#00706a" }} d={style.icon} /></g>
          <text className="box-name" x="28" y="19">{fitText(node.name, w - 28 - 24, 12)}</text>
          <circle className="dot" cx={w - 14} cy="15" r="4.5" fill={colour} />
          {node.steps.map((s, i) => {
            const y = GROUP.head + i * GROUP.step;
            return (
              <g key={s.id} transform={`translate(8 ${y})`}>
                <rect className="step" width={w - 16} height="20" rx="4" />
                <rect x="0" y="0" width="4" height="20" rx="2" fill={STEP_COLOUR[s.type] ?? STEP_COLOUR.transform} />
                <text className="step-text" x="12" y="14">{fitText(stepTitle(s, node.steps.filter((x) => x !== s)), w - 16 - 20, 11)}</text>
              </g>
            );
          })}
        </>
      ) : (
        <>
          <rect className="card" width={w} height={h} rx="6" />
          {facts.note && facts.tone === "needs_look" && <path className="tint" d={`M1 26 H${w - 1} V${h - 6} A5 5 0 0 1 ${w - 6} ${h - 1} H6 A5 5 0 0 1 1 ${h - 6} Z`} />}
          <path d={`M0 6 A6 6 0 0 1 6 0 H${w - 6} A6 6 0 0 1 ${w} 6 V26 H0 Z`} fill={style.colour} />
          <g transform="translate(9 6) scale(0.58)"><path className="glyph" d={style.icon} /></g>
          <text className="name" x="28" y="17">{fitText(node.name, w - 28 - 22, 12)}</text>
          <circle className="dot" cx={w - 13} cy="13" r="4.5" fill={colour} />
          {facts.stats.map((s, i) => <Stat key={s.key} stat={s} x={i ? 102 : 10} y={43} max={i ? w - 102 - 22 : 72} />)}
          {facts.sub && <text className="sub" x="10" y={facts.stats.length ? 57 : 44}>{fitText(facts.sub, w - 20, 11)}</text>}
          {facts.note && <text className="note" x="10" y={facts.stats.length || facts.sub ? 57 : 44}>{fitText(facts.note, w - 20, 11)}</text>}
        </>
      )}
    </g>
  );
}

/** The whole map in a small box, with the part in view outlined; a press or a drag on it moves the view there. */
export function Minimap({ layout, nodes, viewport, width = 188, height = 116 }) {
  const t = useT();
  const { view, size, move } = viewport;
  const { k } = minimapScale(layout, { w: width - 16, h: height - 16 });
  const kindOf = Object.fromEntries(nodes.map((n) => [n.id, n.kind]));
  const at = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const mx = (e.clientX - r.left - 8) / k;
    const my = (e.clientY - r.top - 8) / k;
    move({ ...view, x: size.w / 2 - mx * view.k, y: size.h / 2 - my * view.k });
  };
  const seen = { x: -view.x / view.k, y: -view.y / view.k, w: size.w / view.k, h: size.h / view.k };
  return (
    <div className="tw-minimap" style={{ width, height }}>
      <svg width={width} height={height} role="img" aria-label={t("lineage.twin.minimap")} onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); at(e); }} onPointerMove={(e) => { if (e.buttons === 1) at(e); }}>
        <g transform={`translate(8 8) scale(${k})`}>
          {Object.entries(layout.positions).map(([id, p]) => <rect key={id} x={p.x} y={p.y} width={p.w} height={p.h} rx="8" fill={(TWIN_STYLE[kindOf[id]] ?? TWIN_STYLE.view).colour} opacity="0.85" />)}
          <rect x={Math.max(-40, Math.min(seen.x, layout.width))} y={Math.max(-40, Math.min(seen.y, layout.height))} width={Math.min(seen.w, layout.width * 2)} height={Math.min(seen.h, layout.height * 2)} fill="rgba(45,114,210,0.08)" stroke="#2d72d2" strokeWidth={1.5 / k} />
        </g>
      </svg>
    </div>
  );
}
