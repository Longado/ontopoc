import { useEffect, useRef, useState } from "react";

/** A canvas you can pan (drag the background), zoom (wheel or buttons) and rearrange (drag an element marked
 *  data-node). A drag never counts as a click, so dragging a box does not also select it. */
export function PanZoom({ width, height, label, onNodeDrag, resetKey, children, minHeight = 420, minWidth = 980 }) {
  const svg = useRef(null);
  const drag = useRef(null);
  const dragged = useRef(false);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  useEffect(() => setView({ x: 0, y: 0, k: 1 }), [resetKey]);
  const scale = () => { const r = svg.current.getBoundingClientRect(); return { r, sx: Math.max(width, minWidth) / r.width, sy: Math.max(height, minHeight) / r.height }; };
  const zoomAt = (factor, px, py) => setView((v) => {
    const k = Math.min(4, Math.max(0.25, v.k * factor));
    return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
  });
  useEffect(() => {   // wheel zoom needs a listener that may cancel scrolling the page
    const el = svg.current;
    const wheel = (e) => { e.preventDefault(); const { r, sx, sy } = scale(); zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, (e.clientX - r.left) * sx, (e.clientY - r.top) * sy); };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  });
  function down(e) {
    if (e.button !== 0) return;
    const node = e.target.closest("[data-node]");
    drag.current = { id: node?.dataset.node || null, cx: e.clientX, cy: e.clientY, lx: e.clientX, ly: e.clientY, view, moved: false };
    dragged.current = false;
  }
  function move(e) {
    const d = drag.current;
    if (!d) return;
    if (!d.moved && Math.hypot(e.clientX - d.cx, e.clientY - d.cy) < 4) return;
    if (!d.moved) { d.moved = true; svg.current.setPointerCapture?.(e.pointerId); }
    const { sx, sy } = scale();
    if (d.id && onNodeDrag) onNodeDrag(d.id, ((e.clientX - d.lx) * sx) / view.k, ((e.clientY - d.ly) * sy) / view.k);
    else if (!d.id) setView({ ...d.view, x: d.view.x + (e.clientX - d.cx) * sx, y: d.view.y + (e.clientY - d.cy) * sy });
    d.lx = e.clientX; d.ly = e.clientY;
  }
  function up() { dragged.current = Boolean(drag.current?.moved); drag.current = null; }
  const h = Math.max(height, minHeight);
  const w = Math.max(width, minWidth);   // a small graph keeps a normal size instead of filling the screen with huge boxes
  const ox = (w - width) / 2, oy = (h - height) / 2;
  return <div className="pz">
    <svg ref={svg} viewBox={`0 0 ${w} ${h}`} role="group" aria-label={label} className={drag.current?.moved ? "is-dragging" : ""}
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up}
      onClickCapture={(e) => { if (dragged.current) { e.stopPropagation(); dragged.current = false; } }}>
      <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}><g transform={`translate(${ox},${oy})`}>{children}</g></g>
    </svg>
    <div className="pz-controls" role="group" aria-label="缩放">
      <button type="button" title="放大" onClick={() => zoomAt(1.25, w / 2, h / 2)}>+</button>
      <button type="button" title="缩小" onClick={() => zoomAt(0.8, w / 2, h / 2)}>−</button>
      <button type="button" title="回到原位" onClick={() => setView({ x: 0, y: 0, k: 1 })}>⤢</button>
    </div>
  </div>;
}
