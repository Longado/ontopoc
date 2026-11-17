import React, { useMemo, useState } from "react";
import { getLineageGraph } from "./api.js";
import { NodeDrawer } from "./GraphDrawer.jsx";
import { GraphCanvas } from "./GraphCanvas.jsx";
import { FlowLine, GraphNode } from "./GraphNodes.jsx";
import { lineageColumns, litDepth, shown } from "./graphModel.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

const FILTERS = [["", "全部"], ["data", "数据变了"], ["definition", "定义改了"]];
const DEPTHS = [[1, "1 层"], [2, "2 层"], [3, "3 层"], [null, "全部"]];

const KEY_SHAPES = [
  ["圆角框", "数据源", <rect key="s" x="1" y="3" width="22" height="12" rx="6" />],
  ["平的方框", "数据集", <rect key="d" x="1" y="3" width="22" height="12" rx="1" />],
  ["六边形", "管道（做加工的）", <path key="p" d="M5 3 H19 L23 9 L19 15 H5 L1 9 Z" />],
  ["带标题的卡片", "对象类型", <g key="t"><rect x="1" y="1" width="22" height="16" rx="3" /><path d="M1 6 H23" /></g>],
  ["小方框", "关系、行为、视图、派生属性、回答", <rect key="o" x="1" y="4" width="22" height="10" rx="3" />],
];
const KEY_COLOURS = [["green", "已确认"], ["amber", "需再看"], ["red", "已退回"], ["grey", "草稿、未确认，或没有状态"]];

/** What the shapes and colours of the graph mean. */
function Legend() {
  return (
    <details className="legend" open>
      <summary>图例</summary>
      <div className="legend-body">
        <ul aria-label="形状">
          {KEY_SHAPES.map(([shape, text, mark]) => <li key={text}><svg width="26" height="18" viewBox="0 0 24 18" className="legend-shape" role="img" aria-label={shape}>{mark}</svg>{text}</li>)}
        </ul>
        <ul aria-label="颜色和状态">
          {KEY_COLOURS.map(([tone, text]) => <li key={tone}><span className={`legend-dot tone-${tone}`} aria-hidden="true" />{text}</li>)}
          <li><span className="legend-line" aria-hidden="true" />读取：从左边读到右边</li>
          <li><span className="legend-line lit" aria-hidden="true" />选中的节点和它读、被读到的</li>
        </ul>
      </div>
    </details>
  );
}

/** 血缘: from the sources and datasets on the left, through the pipelines, to the types, relations, views and actions that stand on them and the answers saved from them, in
 * fixed columns with a header over each. Picking a node lights what it reads and what reads it, as far as `展开 N 层` says. */
export function LineagePage() {
  const [state] = useLoad(getLineageGraph, []);
  const [picked, setPicked] = useState(null);
  const [mode, setMode] = useState("both");
  const [depth, setDepth] = useState(null);
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const graph = state.data;
  const layout = useMemo(() => (graph ? lineageColumns(graph.nodes, graph.edges) : null), [graph]);
  const node = graph?.nodes.find((n) => n.id === picked) ?? null;
  const reach = useMemo(() => (node ? litDepth(node.id, graph.edges, mode, depth) : null), [node, graph, mode, depth]);
  const narrowed = Boolean(filter || query.trim());
  const stale = graph ? graph.nodes.filter((n) => n.stale).length : 0;
  const pick = (id) => { setPicked(id); setMode("both"); };
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: "数据" }, { label: "血缘" }]} title="血缘" sub="数据从哪来、被谁用：从左到右是数据源、数据集、管道、数据集、对象类型，再到关系、行为、视图和派生。" />
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !graph && <p className="muted">加载中</p>}
      {graph && !graph.nodes.length && (graph.hidden_types > 0
        ? <EmptyState icon="lineage" title="没有能看的血缘" text={`有 ${graph.hidden_types} 个对象类型没有开放给你，找管理员。`} />
        : <EmptyState icon="lineage" title="还没有血缘" text="有了数据集和对象类型，这里会画出它们之间怎么连。" action={{ label: "去看数据集", href: "#/datasets" }} />)}
      {graph && graph.nodes.length > 0 && (
        <>
          <div className="graph-bar">
            <div className="seg" role="group" aria-label="按原因筛选">
              {FILTERS.map(([key, label]) => <button key={key} className={filter === key ? "on" : ""} aria-pressed={filter === key} onClick={() => setFilter(key)}>{label}</button>)}
            </div>
            <input type="search" placeholder="按名称找" aria-label="按名称找" value={query} onChange={(e) => setQuery(e.target.value)} />
            {stale > 0 && <span className="warn small">{stale} 个需再看</span>}
            {node && (
              <>
                <div className="seg" role="group" aria-label={`${node.name}的上下游`}>
                  <button className={mode === "both" ? "on" : ""} aria-pressed={mode === "both"} onClick={() => setMode("both")}>上下游</button>
                  <button className={mode === "up" ? "on" : ""} aria-pressed={mode === "up"} onClick={() => setMode("up")}>只看上游</button>
                  <button className={mode === "down" ? "on" : ""} aria-pressed={mode === "down"} onClick={() => setMode("down")}>只看下游</button>
                </div>
                <div className="seg" role="group" aria-label="展开几层">
                  <span className="seg-label">展开</span>
                  {DEPTHS.map(([n, label]) => <button key={label} className={depth === n ? "on" : ""} aria-pressed={depth === n} onClick={() => setDepth(n)}>{label}</button>)}
                </div>
                <button className="secondary" onClick={() => setPicked(null)}>清除选择</button>
              </>
            )}
          </div>
          <div className={`graph-layout${node ? " with-drawer" : ""}`}>
            <GraphCanvas width={layout.width} height={layout.height} label="从数据源到回答的血缘，按列分层" fileName="血缘.png" onBlank={() => setPicked(null)}>
              {layout.columns.map((c) => (
                <g key={c.key + c.x} aria-hidden="true">
                  <rect className="col-band" x={c.x - 12} y="0" width={c.w - 8} height={layout.height} rx="6" />
                  <text className="col-head" x={c.x} y="30">{c.label}</text>
                  <text className="col-count" x={c.x + c.w - 36} y="30" textAnchor="end">{c.count}</text>
                  <path className="col-rule" d={`M${c.x} 40 H${c.x + c.w - 28}`} />
                </g>
              ))}
              {graph.edges.map((e) => layout.positions[e.from] && layout.positions[e.to] && (
                <FlowLine key={`${e.from}>${e.to}`} from={layout.positions[e.from]} to={layout.positions[e.to]}
                  lit={Boolean(reach) && reach.has(e.from) && reach.has(e.to)} faded={Boolean(reach) && !(reach.has(e.from) && reach.has(e.to))} />
              ))}
              {graph.nodes.map((n) => (
                <GraphNode key={n.id} node={n} box={layout.positions[n.id]} picked={picked === n.id}
                  faded={(Boolean(reach) && !reach.has(n.id)) || (narrowed && !shown(n, filter, query))} onPick={() => pick(n.id)} />
              ))}
            </GraphCanvas>
            {node && <NodeDrawer key={node.id} node={node} onClose={() => setPicked(null)} />}
          </div>
          <Legend />
        </>
      )}
    </main>
  );
}
