import React, { useCallback, useEffect, useRef, useState } from "react";

// The graph's own styles live inside the SVG, so a picture exported from it looks like the one on the page (a stand-alone SVG has no page CSS and no custom properties).
const STYLE = `
text { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; fill: #1c1c1a; }
.g-node { cursor: pointer; }
.g-node .box { fill: #fff; stroke: #a3a39d; stroke-width: 1; }
.g-node .head { fill: #e6e6e0; }
.g-node.s-confirmed .box { fill: #eef6f0; stroke: #2b7a4b; }
.g-node.s-confirmed .head { fill: #d9ebdf; }
.g-node.s-needs_look .box { fill: #fcf3e1; stroke: #a35f00; }
.g-node.s-needs_look .head { fill: #f7e3bd; }
.g-node.s-rejected .box { fill: #fbebe8; stroke: #a8271a; }
.g-node.s-rejected .head { fill: #f4d3ce; }
.g-node.dataset .box { fill: #f5f5f2; stroke: #a3a39d; }
.g-node.picked .box { stroke: #1757dc; stroke-width: 2.5; }
.g-node .name { font-size: 14px; font-weight: 600; }
.g-node .line { font-size: 12px; fill: #6b6b66; }
.g-node .cause { font-size: 12px; fill: #a35f00; font-weight: 600; }
.g-node .word-confirmed { fill: #2b7a4b; font-weight: 600; }
.g-node .word-rejected { fill: #a8271a; font-weight: 600; }
.g-edge .line { fill: none; stroke: #6b6b66; stroke-width: 1.5; }
.g-edge.s-needs_look .line { stroke: #a35f00; }
.g-edge.s-rejected .line { stroke: #a8271a; }
.g-edge.dashed .line { stroke-dasharray: 7 5; }
.g-edge.lit .line { stroke: #1757dc; stroke-width: 2; }
.g-edge .pill { fill: #fff; }
.g-edge text { font-size: 12px; fill: #1c1c1a; }
.g-edge.s-needs_look text { fill: #a35f00; }
.g-edge .hit { fill: none; stroke: transparent; stroke-width: 14; cursor: pointer; }
.g-edge.picked .pill { stroke: #1757dc; stroke-width: 1.5; }
.g-edge:focus { outline: none; }
.g-edge:focus-visible .pill { stroke: #1757dc; stroke-width: 1.5; }
.faded { opacity: 0.22; }
.g-node:focus-visible .box { stroke: #1757dc; stroke-width: 2.5; }
.g-node:focus { outline: none; }
`;

const MARKERS = { grey: "#6b6b66", amber: "#a35f00", red: "#a8271a", blue: "#1757dc" };
const MIN = 0.25;
const MAX = 3;

/** Saves the picture as a PNG at twice its size: the SVG without the zoom and pan, drawn onto a white canvas. */
function exportPng(svg, width, height, fileName) {
  const clone = svg.cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", width);
  clone.setAttribute("height", height);
  clone.setAttribute("viewBox", `0 0 ${width} ${height}`);
  clone.querySelector("[data-view]").removeAttribute("transform");
  const image = new Image();
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = width * 2;
    canvas.height = height * 2;
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

/**
 * The drawing surface of both graphs: an SVG of `width` x `height` units with zoom in and out, fit, drag to move and export as PNG. A press on the empty background calls `onBlank`.
 * `label` is what a screen reader hears; `fileName` the name of the exported picture.
 */
export function GraphCanvas({ width, height, label, fileName, onBlank, children }) {
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
    const k = Math.min(size.w / width, size.h / height, 1);
    setView({ k, x: (size.w - width * k) / 2, y: (size.h - height * k) / 2 });
  }, [size.w, size.h, width, height]);
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
      if (!e.ctrlKey && !e.metaKey) return;   // a plain wheel still scrolls the page
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [zoom]);
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
  return (
    <div className="canvas" ref={holder}>
      <div className="graph-tools">
        <button className="secondary" onClick={() => zoom(1.25)}>放大</button>
        <button className="secondary" onClick={() => zoom(0.8)}>缩小</button>
        <button className="secondary" onClick={fit}>适应</button>
        <button className="secondary" onClick={() => exportPng(svg.current, width, height, fileName)}>导出 PNG</button>
      </div>
      <svg ref={svg} width="100%" height="100%" role="group" aria-label={label} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { drag.current = null; }}>
        <style>{STYLE}</style>
        <defs>
          {Object.entries(MARKERS).map(([name, color]) => (
            <marker key={name} id={`arrow-${name}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
              <path d="M1 1 L9 5 L1 9 Z" fill={color} />
            </marker>
          ))}
        </defs>
        <rect data-bg width="100%" height="100%" fill="#fff" />
        <g data-view transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>{children}</g>
      </svg>
    </div>
  );
}
