import React, { useLayoutEffect, useMemo, useState } from "react";
import { getLineageGraph } from "./api.js";
import { NodeDrawer } from "./GraphDrawer.jsx";
import { GraphCanvas } from "./GraphCanvas.jsx";
import { FlowLine, GraphNode } from "./GraphNodes.jsx";
import { KIND_LABEL, KIND_STYLE, STATE_COLOUR, lineageColumns, litDepth, shown, stateTone } from "./graphModel.js";
import { useT } from "./i18n/index.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

const DEPTHS = [1, 2, 3, null];
const MODES = ["both", "up", "down"];
const KINDS = ["source", "dataset", "pipeline", "type", "relation", "view", "action", "derived", "answer"];
const TONES = ["confirmed", "needs_look", "rejected", "none"];
const STRIP = 28;   // the sticky column header
const LEGEND_W = 240;
const PANEL_W = 360;
const PUSH_FROM = 900;   // a panel pushes the graph aside only when what is left is at least this wide; otherwise it floats over it

/** What the chips, the dots and the lines of the graph mean, with how many of each the graph holds. */
function Legend({ nodes }) {
  const t = useT();
  const kinds = KINDS.map((kind) => [kind, nodes.filter((n) => n.kind === kind).length]).filter(([, n]) => n);
  const tones = TONES.map((tone) => [tone, nodes.filter((n) => stateTone(n) === tone).length]);
  return (
    <aside className="ln-legend" aria-label={t("lineage.legend.aria")}>
      <section>
        <h2>{t("lineage.legend.kinds")}</h2>
        <ul>
          {kinds.map(([kind, n]) => (
            <li key={kind}>
              <span className="ln-swatch kind" style={{ background: KIND_STYLE[kind].colour }} aria-hidden="true"><svg viewBox="0 0 24 24" width="11" height="11"><path d={KIND_STYLE[kind].icon} /></svg></span>
              <span className="ln-legend-name">{KIND_LABEL[kind]}</span>
              <span className="ln-legend-count">{n}</span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>{t("lineage.legend.states")}</h2>
        <ul>
          {tones.map(([tone, n]) => (
            <li key={tone} className={n ? "" : "zero"}>
              <span className="ln-swatch dot" style={{ background: STATE_COLOUR[tone] }} aria-hidden="true" />
              <span className="ln-legend-name">{t(`lineage.legend.tone.${tone}`)}</span>
              <span className="ln-legend-count">{n}</span>
            </li>
          ))}
        </ul>
        <p className="ln-legend-note">{t("lineage.legend.bar_note")}</p>
      </section>
      <section>
        <h2>{t("lineage.legend.lines")}</h2>
        <ul>
          <li><span className="ln-swatch line" aria-hidden="true" /><span className="ln-legend-name">{t("lineage.legend.flow")}</span></li>
          <li><span className="ln-swatch line lit" aria-hidden="true" /><span className="ln-legend-name">{t("lineage.legend.path")}</span></li>
          <li><span className="ln-swatch faded" aria-hidden="true" /><span className="ln-legend-name">{t("lineage.legend.dimmed")}</span></li>
        </ul>
      </section>
    </aside>
  );
}

/** A group of buttons of which one is on. */
function Segmented({ label, value, options, onChange, lead }) {
  return (
    <div className="ln-seg" role="group" aria-label={label}>
      {lead && <span className="ln-seg-lead">{lead}</span>}
      {options.map(([key, text]) => <button key={String(key)} type="button" className={value === key ? "on" : ""} aria-pressed={value === key} onClick={() => onChange(key)}>{text}</button>)}
    </div>
  );
}

/** The width of an element (given to the returned callback as its `ref`), kept up to date. */
function useWidth() {
  const [el, setEl] = useState(null);
  const [width, setWidth] = useState(1200);
  useLayoutEffect(() => {
    if (!el) return undefined;
    const watch = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    watch.observe(el);
    return () => watch.disconnect();
  }, [el]);
  return [setEl, width];
}

/** Data lineage: from the sources and datasets on the left, through the pipelines, to the types, relations, views and actions that stand on them and the answers saved from them, in
 * fixed columns with a sticky header over each. Picking a node lights what it reads and what reads it, as far as the depth says, and opens its panel on the right. */
export function LineagePage() {
  const t = useT();
  const [state] = useLoad(getLineageGraph, []);
  const [picked, setPicked] = useState(null);
  const [mode, setMode] = useState("both");
  const [depth, setDepth] = useState(null);
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const [legendOpen, setLegendOpen] = useState(true);
  const [tools, setTools] = useState(null);
  const [bodyRef, bodyWidth] = useWidth();
  const graph = state.data;
  const layout = useMemo(() => (graph ? lineageColumns(graph.nodes, graph.edges) : null), [graph]);
  const node = graph?.nodes.find((n) => n.id === picked) ?? null;
  const reach = useMemo(() => (node ? litDepth(node.id, graph.edges, mode, depth) : null), [node, graph, mode, depth]);
  const narrowed = Boolean(filter || query.trim());
  const stale = graph ? graph.nodes.filter((n) => n.stale).length : 0;
  const pick = (id) => { setPicked(id); setMode("both"); };
  const showLegend = legendOpen && !(node && bodyWidth - LEGEND_W - PANEL_W < PUSH_FROM);   // a panel that would cover the graph sends the legend away until it is closed
  const push = bodyWidth - (showLegend ? LEGEND_W : 0) - PANEL_W >= PUSH_FROM;   // push the graph aside, or float over it
  const covered = node && !push ? PANEL_W : 0;
  const reveal = useMemo(() => {   // the picked node and everything lit with it, kept in sight and clear of the panel
    if (!node || !reach) return null;
    const boxes = [...reach].map((id) => layout.positions[id]).filter(Boolean);
    if (!boxes.length) return null;
    const x = Math.min(...boxes.map((b) => b.x));
    const y = Math.min(...boxes.map((b) => b.y));
    return { x, y, w: Math.max(...boxes.map((b) => b.x + b.w)) - x, h: Math.max(...boxes.map((b) => b.y + b.h)) - y };
  }, [node, reach, layout]);
  const filters = [["", t("lineage.filter.all")], ["data", t("lineage.filter.data")], ["definition", t("lineage.filter.definition")]];
  const lit = (e) => Boolean(reach) && reach.has(e.from) && reach.has(e.to);
  const edges = graph ? graph.edges.filter((e) => layout.positions[e.from] && layout.positions[e.to]) : [];
  return (
    <main className="page ln-page">
      <PageHeader crumbs={[{ label: t("lineage.crumb") }, { label: t("lineage.title") }]} title={t("lineage.title")} sub={t("lineage.sub")} />
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !graph && <p className="muted">{t("lineage.loading")}</p>}
      {graph && !graph.nodes.length && (graph.hidden_types > 0
        ? <EmptyState icon="lineage" title={t("lineage.hidden.title")} text={t("lineage.hidden.text", { count: graph.hidden_types })} />
        : <EmptyState icon="lineage" title={t("lineage.empty.title")} text={t("lineage.empty.text")} action={{ label: t("lineage.empty.action"), href: "#/datasets" }} />)}
      {graph && graph.nodes.length > 0 && (
        <div className="ln-shell">
          <div className="ln-toolbar" role="toolbar" aria-label={t("lineage.toolbar.aria")}>
            <button type="button" className={`ln-icon${showLegend ? " on" : ""}`} aria-pressed={showLegend} aria-label={t("lineage.legend.toggle")} title={t("lineage.legend.toggle")} onClick={() => setLegendOpen((v) => !v)}>
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 5h16v14H4zM9 5v14" /></svg>
            </button>
            <label className="ln-search">
              <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4" /></svg>
              <input type="search" placeholder={t("lineage.search")} aria-label={t("lineage.search")} value={query} onChange={(e) => setQuery(e.target.value)} />
            </label>
            <Segmented label={t("lineage.filter.aria")} value={filter} options={filters} onChange={setFilter} />
            {stale > 0 && <span className="ln-stale" title={t("lineage.stale", { count: stale })}>{t("lineage.stale", { count: stale })}</span>}
            {node && (
              <>
                <Segmented label={t("lineage.direction.aria", { name: node.name })} value={mode} onChange={setMode} options={MODES.map((m) => [m, t(`lineage.direction.${m}`)])} />
                <Segmented label={t("lineage.depth.aria")} value={depth} onChange={setDepth} lead={t("lineage.depth.lead")} options={DEPTHS.map((n) => [n, n == null ? t("lineage.depth.all") : String(n)])} />
                <button type="button" className="ln-clear" title={t("lineage.clear_title")} onClick={() => setPicked(null)}>{t("lineage.clear")}</button>
              </>
            )}
            <div className="ln-tools" ref={setTools} />
          </div>
          <div className={`ln-body${showLegend ? "" : " no-legend"}${node && push ? " push" : ""}`} ref={bodyRef}>
            {showLegend && <Legend nodes={graph.nodes} />}
            <div className="ln-stage">
              <GraphCanvas width={layout.width} height={layout.height} label={t("lineage.canvas.aria")} fileName={t("lineage.file")} onBlank={() => setPicked(null)} fit="readable" top={STRIP} wheel="pan" tools={tools}
                inset={covered} reveal={reveal} exportTop={STRIP}
                sticky={(view) => (
                  <g className="strip-layer" aria-hidden="true">
                    <rect className="strip" width="100%" height={STRIP} />
                    {layout.columns.map((c) => (
                      <g key={c.key + c.x}>
                        <text className="col-head" x={view.x + c.x * view.k + 12} y="18">{c.label}</text>
                        <text className="col-count" x={view.x + (c.x + c.w) * view.k - 12} y="18" textAnchor="end">{c.count}</text>
                        <path className="col-rule" d={`M${view.x + c.x * view.k} 0 V${STRIP}`} />
                      </g>
                    ))}
                    <path className="strip-rule" d={`M0 ${STRIP - 0.5} H4000`} />
                  </g>
                )}>
                {layout.columns.map((c, i) => (
                  <g key={c.key + c.x} aria-hidden="true">
                    <rect data-bg className={`col-band${i % 2 ? " alt" : ""}`} x={i === 0 ? -6000 : c.x} y="-6000" width={c.w + (i === 0 ? 6000 : 0) + (i === layout.columns.length - 1 ? 6000 : 0)} height={layout.height + 12000} />
                    {i > 0 && <path className="col-rule" d={`M${c.x} -6000 V${layout.height + 6000}`} />}
                    <g data-export-only>
                      <text className="col-head" x={c.x + 12} y={-10}>{c.label}</text>
                      <text className="col-count" x={c.x + c.w - 12} y={-10} textAnchor="end">{c.count}</text>
                    </g>
                  </g>
                ))}
                {[...edges].sort((a, b) => Number(lit(a)) - Number(lit(b))).map((e) => (
                  <FlowLine key={`${e.from}>${e.to}`} from={layout.positions[e.from]} to={layout.positions[e.to]} lit={lit(e)} faded={Boolean(reach) && !lit(e)} />
                ))}
                {graph.nodes.map((n) => (
                  <GraphNode key={n.id} node={n} box={layout.positions[n.id]} picked={picked === n.id}
                    faded={(Boolean(reach) && !reach.has(n.id)) || (narrowed && !shown(n, filter, query))} onPick={() => pick(n.id)} />
                ))}
              </GraphCanvas>
              {node && !push && <div className="ln-overlay"><NodeDrawer key={node.id} node={node} onClose={() => setPicked(null)} /></div>}
            </div>
            {node && push && <NodeDrawer key={node.id} node={node} onClose={() => setPicked(null)} />}
          </div>
        </div>
      )}
    </main>
  );
}
