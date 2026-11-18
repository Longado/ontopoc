import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { fitView } from "./graphModel.js";
import { useT } from "./i18n/index.js";

// The graph's own styles live inside the SVG, so a picture exported from it looks like the one on the page (a stand-alone SVG has no page CSS and no custom properties).
const STYLE = `
text { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; fill: #1c2127; }
[data-export-only] { display: none; }
.g-node { cursor: pointer; }
.g-node .card { fill: #fff; stroke: #d3d8de; stroke-width: 1; }
.g-node:hover .card { stroke: #abb3bf; }
.g-node .ring { fill: none; stroke: rgba(45, 114, 210, 0.28); stroke-width: 3; }
.g-node.picked .card { stroke: #2d72d2; stroke-width: 1.5; }
.g-node .glyph { fill: none; stroke: #fff; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
.g-node .name { font-size: 13px; font-weight: 600; }
.g-node .meta { font-size: 11px; fill: #5f6b7c; }
.g-node .meta.cause { fill: #77450d; font-weight: 600; }
.g-node:focus { outline: none; }
.g-node:focus-visible .card { stroke: #2d72d2; stroke-width: 2; }
.g-edge .line { fill: none; stroke: #8f99a8; stroke-width: 1.5; }
.g-edge.flow .line { stroke: #b4bcc7; stroke-width: 1.25; }
.g-edge.s-needs_look .line { stroke: #c87619; }
.g-edge.s-rejected .line { stroke: #cd4246; }
.g-edge.dashed .line { stroke-dasharray: 7 5; }
.g-edge.lit .line { stroke: #2d72d2; stroke-width: 2; }
.g-edge .pill { fill: #fff; stroke: #dce0e5; }
.g-edge text { font-size: 12px; fill: #1c2127; }
.g-edge.s-needs_look text { fill: #77450d; }
.g-edge .hit { fill: none; stroke: transparent; stroke-width: 14; cursor: pointer; }
.g-edge.picked .pill { stroke: #2d72d2; stroke-width: 1.5; }
.g-edge:focus { outline: none; }
.g-edge:focus-visible .pill { stroke: #2d72d2; stroke-width: 1.5; }
.g-node.faded { opacity: 0.4; }
.g-edge.faded { opacity: 0.2; }
.g-edge.flow.faded { opacity: 0.15; }
.col-band { fill: #fff; }
.col-band.alt { fill: #f6f7f9; }
.col-rule { stroke: #dce0e5; stroke-width: 1; }
.col-head { font-size: 12px; font-weight: 600; fill: #5f6b7c; }
.col-count { font-size: 12px; fill: #8f99a8; }
.strip { fill: #fff; }
.strip-rule { stroke: #dce0e5; stroke-width: 1; }
`;

const MARKERS = { grey: "#b4bcc7", amber: "#c87619", red: "#cd4246", blue: "#2d72d2" };
const MIN = 0.25;
const MAX = 3;

/** Saves the picture as a PNG at twice its size: the SVG without the zoom and pan, drawn onto a white canvas. `top` is room kept above the picture for the column headings, which
 * the page draws for the file as part of the graph (`data-export-only`) instead of as the sticky strip (`data-live`). */
export function exportPng(svg, width, height, fileName, top) {
  const clone = svg.cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", width);
  clone.setAttribute("height", height + top);
  clone.setAttribute("viewBox", `0 ${-top} ${width} ${height + top}`);
  clone.querySelector("[data-view]").removeAttribute("transform");
  clone.querySelectorAll("[data-live]").forEach((el) => el.remove());
  clone.querySelectorAll("[data-export-only]").forEach((el) => el.setAttribute("style", "display: inline"));
  const image = new Image();
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = width * 2;
    canvas.height = (height + top) * 2;
    const context = canvas.getContext("2d");
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(link.href);
    }, "image/png");
  };
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(clone))}`;
}

const ICONS = {
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  fit: "M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4",
  download: "M12 4v11M7 11l5 5 5-5M5 20h14",
};
const Glyph = ({ name }) => <svg className="gt-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d={ICONS[name]} /></svg>;

/** Zoom out, the zoom level, zoom in, fit and export: one icon pill. */
function Tools({ zoom, fit, exportIt, percent }) {
  const t = useT();
  return (
    <div className="graph-tools" role="group" aria-label={t("lineage.tools.aria")}>
      <button type="button" className="gt-btn" onClick={() => zoom(0.8)} aria-label={t("lineage.tools.zoom_out")} title={t("lineage.tools.zoom_out")}><Glyph name="minus" /></button>
      <span className="gt-level" aria-live="polite">{percent}%</span>
      <button type="button" className="gt-btn" onClick={() => zoom(1.25)} aria-label={t("lineage.tools.zoom_in")} title={t("lineage.tools.zoom_in")}><Glyph name="plus" /></button>
      <button type="button" className="gt-btn gt-text" onClick={fit} aria-label={t("lineage.tools.fit")} title={t("lineage.tools.fit")}><Glyph name="fit" /><span>{t("lineage.tools.fit")}</span></button>
      <button type="button" className="gt-btn gt-text" onClick={exportIt} aria-label={t("lineage.tools.export")} title={t("lineage.tools.export")}><Glyph name="download" /><span>{t("lineage.tools.export")}</span></button>
    </div>
  );
}

/**
 * The drawing surface of both graphs: an SVG of `width` x `height` units with zoom in and out, fit, drag to move and export as PNG. A press on the empty background calls `onBlank`.
 * `fit="readable"` (the lineage) never fits smaller than 70% or larger than 100%, leaving `top` px clear for a sticky header; the default shows the whole picture. `label` is what a
 * screen reader hears; `fileName` the name of the exported picture.
 * The lineage also passes: `tools` (an element in its toolbar to put the zoom controls in; without it they float over the corner), `sticky(view)` (SVG drawn over the picture at a fixed
 * place that follows only its zoom and its sideways move: the column headings), `wheel="pan"` (the wheel moves the picture; with Ctrl or Cmd it zooms), `inset` (px of the right edge
 * a panel covers) and `reveal` (a box in picture units to keep in view, moved clear of that panel) and `exportTop`.
 */
export function GraphCanvas({ width, height, label, fileName, onBlank, fit: fitMode = "all", top = 0, tools = null, sticky, wheel: wheelMode = "scroll", inset = 0, reveal = null, exportTop = 0, children }) {
  const holder = useRef(null);
  const svg = useRef(null);
  const [size, setSize] = useState({ w: 900, h: 520 });
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const drag = useRef(null);
  useEffect(() => {
    const watch = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }));
    watch.observe(holder.current);
    return () => watch.disconnect();
  }, []);
  const fit = useCallback(() => {
    setView(fitView({ w: size.w, h: size.h }, { width, height, top }, fitMode));
  }, [size.w, size.h, width, height, top, fitMode]);
  useEffect(fit, [width, height, size.w]);   // a new picture, or a window of another width, is fitted again; zooming and moving are the reader's until then
  const zoom = useCallback((factor, cx = size.w / 2, cy = size.h / 2) => {
    setView((v) => {
      const k = Math.min(MAX, Math.max(MIN, v.k * factor));
      return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
    });
  }, [size.w, size.h]);
  useEffect(() => {
    const el = svg.current;
    const wheel = (e) => {
      const zooming = e.ctrlKey || e.metaKey;
      if (!zooming && wheelMode !== "pan") return;   // a plain wheel still scrolls the page, unless the graph fills the page
      e.preventDefault();
      if (zooming) {
        const r = el.getBoundingClientRect();
        zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top);
      } else {
        setView((v) => ({ ...v, x: v.x - e.deltaX, y: v.y - e.deltaY }));
      }
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [zoom, wheelMode]);
  useEffect(() => {   // a picked node and what is lit with it stay in sight: zoomed out (not below 70%) if need be, and moved clear of the panel that covers the right edge and of the header strip
    if (!reveal) return;
    setView((v) => {
      const room = size.w - inset - 32;
      const k = reveal.w * v.k > room ? Math.min(v.k, Math.max(0.7, room / reveal.w)) : v.k;
      const cx = 0;
      const cy = top;   // zoomed out about the top left, so the picture stays under the header strip
      let x = k === v.k ? v.x : cx - ((cx - v.x) * k) / v.k;
      let y = k === v.k ? v.y : cy - ((cy - v.y) * k) / v.k;
      const right = x + (reveal.x + reveal.w) * k;
      if (right > size.w - inset - 16) x -= right - (size.w - inset - 16);
      const left = x + reveal.x * k;
      if (left < 16) x += 16 - left;
      const bottom = y + (reveal.y + reveal.h) * k;
      if (bottom > size.h - 16) y -= bottom - (size.h - 16);
      const above = y + reveal.y * k;
      if (above < top + 8) y += top + 8 - above;
      return x === v.x && y === v.y && k === v.k ? v : { k, x, y };
    });
  }, [reveal?.x, reveal?.y, reveal?.w, reveal?.h, size.w, size.h, inset]);   // eslint-disable-line react-hooks/exhaustive-deps -- a new box, or a frame of another size (which fits again first), moves the picture
  const down = (e) => {
    if (!e.target.hasAttribute("data-bg")) return;
    drag.current = { x: e.clientX, y: e.clientY, view, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const move = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    if (d.moved) setView({ ...d.view, x: d.view.x + dx, y: d.view.y + dy });
  };
  const up = () => {
    if (drag.current && !drag.current.moved) onBlank?.();
    drag.current = null;
  };
  const controls = <Tools zoom={zoom} fit={fit} exportIt={() => exportPng(svg.current, width, height, fileName, exportTop)} percent={Math.round(view.k * 100)} />;
  return (
    <div className="canvas" ref={holder}>
      {tools ? createPortal(controls, tools) : controls}
      <svg ref={svg} width="100%" height="100%" role="group" aria-label={label} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { drag.current = null; }}>
        <style>{STYLE}</style>
        <defs>
          {Object.entries(MARKERS).map(([name, color]) => (
            <marker key={name} id={`arrow-${name}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
              <path d="M1 1 L9 5 L1 9 Z" fill={color} />
            </marker>
          ))}
        </defs>
        <rect data-bg width="100%" height="100%" fill="#fff" />
        <g data-view transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>{children}</g>
        {sticky && <g data-live>{sticky(view, size)}</g>}
      </svg>
    </div>
  );
}
