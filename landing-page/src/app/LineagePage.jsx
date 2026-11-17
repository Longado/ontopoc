import React, { useEffect, useMemo, useRef, useState } from "react";
import { getDatasets, getLineageGraph, getPipeline, getPipelines } from "./api.js";
import { NodeDrawer } from "./GraphDrawer.jsx";
import { exportPng } from "./GraphCanvas.jsx";
import { KIND_LABEL, litDepth, shown } from "./graphModel.js";
import { useT } from "./i18n/index.js";
import { edgeTone, enrichNodes, mapLayout, searchMatches } from "./lineageModel.js";
import { IconButton, Search, Segmented, SelectionBar, TraceDialog, TypesPopover } from "./TwinControls.jsx";
import { Columns, Minimap, TwinEdge, TwinNode, TwinSvg, useViewport } from "./TwinMap.jsx";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

const DEPTHS = [1, 2, 3, null];
const MODES = ["both", "up", "down"];

/** What the map adds to the graph: how many columns and rows each dataset has, and the steps of each pipeline. Whatever this person may not read is simply missing. */
async function loadExtras() {
  const [datasets, list] = await Promise.all([getDatasets().catch(() => []), getPipelines().catch(() => [])]);
  const details = await Promise.all(list.map((p) => getPipeline(p.id ?? p.name).then((d) => [p.name, d]).catch(() => null)));
  return { datasets, pipelines: Object.fromEntries(details.filter(Boolean)) };
}

/** Data lineage as one twin-view map of the whole workspace, left to right: sources, datasets, pipelines (a box with its steps), the datasets they write, object types, then relations,
 * views, derived properties and actions. Cards carry a few numbers and the state of the node; a link is amber when something at either end needs another look. Picking a node lights what it
 * reads and what reads it, offers Hide, Trace path and Cancel over it, and opens its panel on the right. */
export function LineagePage() {
  const t = useT();
  const [state] = useLoad(getLineageGraph, []);
  const [extra] = useLoad(loadExtras, []);
  const [picked, setPicked] = useState(null);
  const [mode, setMode] = useState("both");
  const [depth, setDepth] = useState(null);
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const [off, setOff] = useState(() => new Set());
  const [hidden, setHidden] = useState(() => new Set());
  const [curved, setCurved] = useState(true);
  const [tool, setTool] = useState("select");
  const [full, setFull] = useState(false);
  const [tracing, setTracing] = useState(null);
  const [mini, setMini] = useState(null);   // null: shown only while part of the map is out of view
  const svg = useRef(null);
  const graph = state.data;
  const all = useMemo(() => (graph ? enrichNodes(graph.nodes, extra.data?.datasets, extra.data?.pipelines) : []), [graph, extra.data]);
  const nodes = useMemo(() => all.filter((n) => !hidden.has(n.id)), [all, hidden]);
  const edges = useMemo(() => (graph ? graph.edges.filter((e) => !hidden.has(e.from) && !hidden.has(e.to)) : []), [graph, hidden]);
  const layout = useMemo(() => mapLayout(nodes, edges), [nodes, edges]);
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const viewport = useViewport(layout);
  const { view, size } = viewport;
  const node = byId[picked] ?? null;
  const rawNode = graph?.nodes.find((n) => n.id === picked) ?? null;
  const reach = useMemo(() => (node ? litDepth(node.id, edges, mode, depth) : null), [node, edges, mode, depth]);
  const found = useMemo(() => (query.trim() ? new Set(searchMatches(nodes, query, (n) => KIND_LABEL[n.kind], Infinity).map((n) => n.id)) : null), [nodes, query]);
  const stale = nodes.filter((n) => n.stale).length;
  const fade = (n) => (Boolean(reach) && !reach.has(n.id)) || off.has(n.kind) || (filter && !shown(n, filter, "")) || (found && !found.has(n.id));
  const lit = (e) => Boolean(reach) && reach.has(e.from) && reach.has(e.to);
  const pick = (id) => { setPicked(id); setMode("both"); };
  const go = (n) => { setQuery(""); pick(n.id); const box = layout.positions[n.id]; if (box) viewport.centre(box); };
  const hide = (id) => { setHidden((h) => new Set(h).add(id)); setPicked(null); };
  const toggleKind = (kind) => setOff((s) => { const next = new Set(s); if (!next.delete(kind)) next.add(kind); return next; });
  const box = node ? layout.positions[node.id] : null;
  useEffect(() => { if (box) viewport.reveal(box); }, [picked, size.w]);   // eslint-disable-line react-hooks/exhaustive-deps -- a picked node is brought into view once, not on every move
  useEffect(() => {
    if (!full) return undefined;
    const esc = (e) => { if (e.key === "Escape" && !tracing) setFull(false); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [full, tracing]);
  const whole = view.x >= -2 && view.y >= -2 && view.x + layout.width * view.k <= size.w + 2 && view.y + layout.height * view.k <= size.h + 2;
  const showMini = mini ?? !whole;
  const bar = box && !tracing ? (() => {
    const x = Math.min(size.w - 135, Math.max(135, view.x + (box.x + box.w / 2) * view.k));
    const top = view.y + box.y * view.k;
    return top < 56 ? { x, y: view.y + (box.y + box.h) * view.k + 10, below: true } : { x, y: top - 10 };
  })() : null;
  return (
    <main className={`page ln-page tw-page${full ? " full" : ""}`}>
      {!full && <PageHeader crumbs={[{ label: t("lineage.crumb") }, { label: t("lineage.title") }]} title={t("lineage.title")} sub={t("lineage.sub")} />}
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !graph && <p className="muted">{t("lineage.loading")}</p>}
      {graph && !graph.nodes.length && (graph.hidden_types > 0
        ? <EmptyState icon="lineage" title={t("lineage.hidden.title")} text={t("lineage.hidden.text", { count: graph.hidden_types })} />
        : <EmptyState icon="lineage" title={t("lineage.empty.title")} text={t("lineage.empty.text")} action={{ label: t("lineage.empty.action"), href: "#/datasets" }} />)}
      {graph && graph.nodes.length > 0 && (
        <div className="tw-shell">
          <div className="tw-toolbar" role="toolbar" aria-label={t("lineage.toolbar.aria")}>
            <div className="tw-group">
              <IconButton icon="fit" label={t("lineage.tools.fit")} onClick={viewport.fit} />
              <IconButton icon="minus" label={t("lineage.tools.zoom_out")} onClick={() => viewport.zoom(0.8)} />
              <span className="tw-zoom" aria-live="polite" title={t("lineage.twin.zoom")}>{viewport.percent}%</span>
              <IconButton icon="plus" label={t("lineage.tools.zoom_in")} onClick={() => viewport.zoom(1.25)} />
            </div>
            <div className="tw-group">
              <IconButton icon="pointer" label={t("lineage.twin.select")} on={tool === "select"} onClick={() => setTool("select")} />
              <IconButton icon="hand" label={t("lineage.twin.pan")} on={tool === "hand"} onClick={() => setTool("hand")} />
            </div>
            <div className="tw-group">
              <IconButton icon="curve" label={t("lineage.twin.curved")} on={curved} onClick={() => setCurved(true)} />
              <IconButton icon="straight" label={t("lineage.twin.straight")} on={!curved} onClick={() => setCurved(false)} />
            </div>
            <div className="tw-group">
              <IconButton icon={full ? "collapse" : "expand"} label={full ? t("lineage.twin.exit_fullscreen") : t("lineage.twin.fullscreen")} onClick={() => setFull((v) => !v)} />
              <IconButton icon="map" label={t("lineage.twin.minimap_toggle")} on={showMini} onClick={() => setMini(!showMini)} />
              <IconButton icon="download" label={t("lineage.tools.export")} onClick={() => exportPng(svg.current, layout.width, layout.height, t("lineage.file"), 0)} />
            </div>
            {stale > 0 && <span className="tw-chip-warn" title={t("lineage.stale", { count: stale })}>{t("lineage.stale", { count: stale })}</span>}
            {hidden.size > 0 && <button type="button" className="tw-chip-btn" onClick={() => setHidden(new Set())}>{t("lineage.twin.hidden", { count: hidden.size })} · {t("lineage.twin.show_all")}</button>}
            <span className="tw-spacer" />
            <Search nodes={nodes} query={query} onQuery={setQuery} onGo={go} />
            <TypesPopover nodes={nodes} off={off} onToggle={toggleKind} filter={filter} onFilter={setFilter} />
          </div>
          {node && (
            <div className="tw-context">
              <span className="tw-context-name">{node.name}</span>
              <Segmented label={t("lineage.direction.aria", { name: node.name })} value={mode} onChange={setMode} options={MODES.map((m) => [m, t(`lineage.direction.${m}`)])} />
              <Segmented label={t("lineage.depth.aria")} value={depth} onChange={setDepth} lead={t("lineage.depth.lead")} options={DEPTHS.map((n) => [n, n == null ? t("lineage.depth.all") : String(n)])} />
              <button type="button" className="tw-link" title={t("lineage.clear_title")} onClick={() => setPicked(null)}>{t("lineage.clear")}</button>
            </div>
          )}
          <div className={`tw-body${rawNode ? " with-panel" : ""}`}>
            <div className="tw-stage">
              <TwinSvg viewport={viewport} content={layout} mode={tool} svgRef={svg} label={t("lineage.canvas.aria")} onBlank={() => setPicked(null)}
                overlay={(
                  <>
                    {bar && <SelectionBar at={bar} onHide={() => hide(node.id)} onTrace={() => setTracing(node.id)} onCancel={() => setPicked(null)} />}
                    {showMini && <Minimap layout={layout} nodes={nodes} viewport={viewport} />}
                  </>
                )}>
                <Columns layout={layout} />
                {[...edges].filter((e) => layout.positions[e.from] && layout.positions[e.to]).sort((a, b) => Number(lit(a)) - Number(lit(b))).map((e) => (
                  <TwinEdge key={`${e.from}>${e.to}`} from={layout.positions[e.from]} to={layout.positions[e.to]} tone={edgeTone(e, byId)} lit={lit(e)} faded={Boolean(reach) && !lit(e)} curved={curved} />
                ))}
                {nodes.map((n) => <TwinNode key={n.id} node={n} box={layout.positions[n.id]} picked={picked === n.id} faded={Boolean(fade(n))} interactive={tool === "select"} onPick={() => pick(n.id)} />)}
              </TwinSvg>
            </div>
            {rawNode && <NodeDrawer key={rawNode.id} node={rawNode} onClose={() => setPicked(null)} />}
          </div>
        </div>
      )}
      {tracing && byId[tracing] && <TraceDialog node={byId[tracing]} nodes={nodes} edges={edges} curved={curved} onClose={() => setTracing(null)} />}
    </main>
  );
}
