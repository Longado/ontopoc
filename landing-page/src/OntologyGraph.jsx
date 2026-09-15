import { useEffect, useRef } from "react";
import { edgeStats, findingsByType, layoutGraph, neighboursOf, unsteady } from "./ontologyGraphModel.js";
import { typeLabel, typeSources } from "./ontologyStudioModel.js";
import "./OntologyGraph.css";

const FINDING = {
  identity_conflict: (d) => `${d.identity} 的“${d.field}”有 ${d.values.join(" / ")}`,
  identity_spelling: (d) => `${d.identity} 有几种写法：${d.variants.map((v) => `“${v}”`).join("、")}`,
  suspected_duplicate: (d) => `${d.identities.join(" 和 ")} 疑似是同一个`,
  missing_reference: (d) => `${d.count} 个在“${d.source}”表里找不到，例如 ${d.examples.join("、")}`,
  orphans: (d) => `${d.count} 个没有任何关系，例如 ${d.examples.join("、")}`,
};

function select(setSelected, value) {
  return { onClick: () => setSelected(value), onKeyDown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelected(value); } } };
}

function PathInspector({ ontology, path, onClearPath }) {
  const relation = (key) => ontology.relations.find((r) => r.key === key);
  return <div className="og-inspector-body">
    <span className="og-kicker">查询路径</span>
    <h3>{path.text || path.nodes.map((k) => typeLabel(ontology, k)).join(" → ")}</h3>
    <ol className="og-steps">{path.nodes.map((k, i) => <li key={`${k}-${i}`}>{i === 0 ? `从“${typeLabel(ontology, k)}”出发` : `经关系“${relation(path.edges[i - 1])?.label || relation(path.edges[i - 1])?.meaning || path.edges[i - 1]}”到“${typeLabel(ontology, k)}”`}</li>)}</ol>
    <p>图上高亮的就是这条路；数字由代码沿着它在数据里一行行数出来。</p>
    <button type="button" className="pr-link og-inline" onClick={onClearPath}>清除路径，看“{typeLabel(ontology, path.nodes[path.nodes.length - 1])}”的数据检查</button>
  </div>;
}

function Inspector({ run, selected, findings }) {
  const { ontology } = run;
  const stability = run.evaluation.stability;
  const fit = run.evaluation.data_fit;
  if (selected.kind === "edge") {
    const r = ontology.relations.find((x) => x.key === selected.key);
    const stats = edgeStats(fit, r.key);
    return <div className="og-inspector-body">
      <span className="og-kicker">关系 · {r.key}</span>
      <h3>{typeLabel(ontology, r.from)} {r.label || "→"} {typeLabel(ontology, r.to)}</h3>
      <p>{r.meaning}</p>
      {r.evidence?.length > 0 && <div className="og-quotes">{r.evidence.map((q, i) => <blockquote key={i}>原文：{q}</blockquote>)}</div>}
      <dl className="og-kv"><div><dt>{r.evidence ? "出自" : "所在表"}</dt><dd>{r.source}</dd></div>
        {stability && stability.relations[r.key] !== undefined && <div><dt>{stability.runs} 次建模</dt><dd className={unsteady(stability, "relations", r.key) ? "og-warn" : ""}>{unsteady(stability, "relations", r.key) ? `只有 ${stability.relations[r.key]} 次有这条关系` : "每次都有"}</dd></div>}
        {stats && <div><dt>连上的行</dt><dd className={stats.complete ? "" : "og-warn"}>{stats.linked_rows} / {stats.rows}{stats.complete ? "" : "（有行没连上）"}</dd></div>}</dl>
    </div>;
  }
  const t = ontology.object_types.find((x) => x.key === selected.key);
  const metrics = ontology.verification?.metrics;
  const own = findings[t.key] || [];
  return <div className="og-inspector-body">
    <span className="og-kicker">对象 · {t.key}</span>
    <h3>{t.label || t.key}</h3>
    {t.rationale && <p>{t.rationale}</p>}
    {t.definition && <p>{t.definition}</p>}
    {t.evidence?.length > 0 && <div className="og-quotes">{t.evidence.map((q, i) => <blockquote key={i}>原文：{q}</blockquote>)}</div>}
    <dl className="og-kv">
      {t.populated_from.length > 0 && <div><dt>来自</dt><dd>{typeSources(t)}</dd></div>}
      {t.attributes.length > 0 && <div><dt>属性</dt><dd>{t.attributes.map((a) => a.path).join("、")}</dd></div>}
      {t.time_field && <div><dt>时间</dt><dd>{t.time_field.path}</dd></div>}
      {stability && stability.types[t.key] !== undefined && <div><dt>{stability.runs} 次建模</dt><dd className={unsteady(stability, "types", t.key) ? "og-warn" : ""}>{unsteady(stability, "types", t.key) ? `只有 ${stability.types[t.key]} 次有它：模型对要不要单独建这个对象拿不准，可以按你的业务决定` : "每次都有"}</dd></div>}
      {metrics && <div><dt>对象数</dt><dd>{metrics.instances[t.key]} 个{metrics.shared_across_sources[t.key] ? `，其中 ${metrics.shared_across_sources[t.key]} 个在多张表里出现` : ""}</dd></div>}
    </dl>
    {fit && <h4>数据检查</h4>}
    {!fit ? null : own.length ? <ul className="og-findings">{own.map((f, i) => <li key={i} className={f.severity === "note" ? "og-note" : ""}>{f.severity === "note" ? "提示：" : ""}{FINDING[f.kind](f.detail)}</li>)}</ul> : <p className="og-ok">这个对象没有发现问题。</p>}
  </div>;
}

export function OntologyGraph({ run, onAsk, selected: chosen, onSelect: setSelected, path, onClearPath, reveal }) {
  const { ontology } = run;
  const graph = layoutGraph(ontology);
  const findings = findingsByType(run.evaluation.data_fit);
  const selected = chosen && (chosen.kind === "edge" ? ontology.relations : ontology.object_types).some((x) => x.key === chosen.key) ? chosen : { kind: "node", key: graph.nodes[0]?.key };
  const edge = selected.kind === "edge" && ontology.relations.find((r) => r.key === selected.key);
  const focus = path ? { nodes: new Set(path.nodes), edges: new Set(path.edges) }
    : selected !== chosen ? null : edge ? { nodes: new Set([edge.from, edge.to]), edges: new Set([edge.key]) } : neighboursOf(ontology, selected.key);
  const dim = (kind, key) => focus && (kind === "node" ? !focus.nodes.has(key) : !focus.edges.has(key)) ? " is-dim" : "";
  const wrap = useRef(null);
  useEffect(() => {   // arriving from an evaluation link: bring the graph and the chosen node into view
    if (!reveal) return;
    wrap.current?.scrollIntoView({ block: "start" });
    wrap.current?.querySelector(".og-node.is-selected")?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [reveal]);
  const all = Object.values(findings).flat();
  const problemCount = all.filter((f) => f.severity === "problem").length;
  const noteCount = all.length - problemCount;
  const isSelected = (kind, key) => selected.kind === kind && selected.key === key;
  return <div className="og-wrap" ref={wrap}>
    <div className="og-canvas">
      <div className="og-bar"><span>本体 · {graph.nodes.length} 个对象 · {graph.edges.length} 条关系<span className="og-swipe"> · 左右滑动看全图</span></span>
        <span>{run.evaluation.data_fit ? `数据检查：${problemCount} 处问题${noteCount ? `，${noteCount} 处提示` : ""}` : run.evaluation.document_fit ? `${run.evaluation.document_fit.kept} 项都有原文引用` : "未评测"}</span></div>
      {path && <div className="og-path" role="status"><span>查询路径：{path.text || path.nodes.map((k) => typeLabel(ontology, k)).join(" → ")}</span><button type="button" className="pr-link" onClick={onClearPath}>清除</button></div>}
      <div className="og-scroll">
        <svg viewBox={`0 0 ${graph.width} ${graph.height}`} style={{ width: "100%", minWidth: Math.max(Math.min(graph.width, 560), Math.round(graph.width * 0.7)), maxWidth: graph.width }} role="group" aria-label="本体关系图">
          <defs><marker id="og-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="og-arrowhead" /></marker></defs>
          {graph.edges.map((e) => { const stats = edgeStats(run.evaluation.data_fit, e.key); const rel = ontology.relations.find((r) => r.key === e.key);
            return <g key={e.key} className={`og-edge${isSelected("edge", e.key) ? " is-selected" : ""}${path?.edges.includes(e.key) ? " is-path" : ""}${stats && !stats.complete ? " is-partial" : ""}${unsteady(run.evaluation.stability, "relations", e.key) ? " is-unsteady" : ""}${dim("edge", e.key)}`}
              role="button" tabIndex={0} aria-label={`关系 ${typeLabel(ontology, e.from)} 到 ${typeLabel(ontology, e.to)}`} {...select(setSelected, { kind: "edge", key: e.key })}>
              <path d={e.path} markerEnd="url(#og-arrow)" />
              {rel.label && <text x={e.lx} y={e.ly - 6} textAnchor="middle">{rel.label}</text>}
            </g>; })}
          {graph.nodes.map((n) => { const own = findings[n.key] || []; const count = own.length; const onlyNotes = own.every((f) => f.severity === "note");
            return <g key={n.key} className={`og-node${isSelected("node", n.key) ? " is-selected" : ""}${path?.nodes.includes(n.key) ? " is-path" : ""}${unsteady(run.evaluation.stability, "types", n.key) ? " is-unsteady" : ""}${dim("node", n.key)}`} transform={`translate(${n.x},${n.y})`}
              role="button" tabIndex={0} aria-label={`对象 ${n.label}${count ? `，${count} 处数据问题` : ""}`} {...select(setSelected, { kind: "node", key: n.key })}>
              <rect width={n.w} height={n.h} className="og-node-box" />
              <rect width={40} height={n.h} className="og-node-side" />
              <text x={54} y={26} className="og-node-key">{n.key.length > 18 ? `${n.key.slice(0, 18)}…` : n.key}</text>
              <text x={54} y={47} className="og-node-label">{n.label}</text>
              {count > 0 && <g transform={`translate(${n.w - 14},0)`}><circle r="11" className={`og-badge${onlyNotes ? " og-badge-note" : ""}`} /><text textAnchor="middle" y="4" className="og-badge-text">{count}</text></g>}
            </g>; })}
        </svg>
      </div>
      <ul className="og-legend" aria-label="图例">
        {run.evaluation.data_fit && <><li><i className="og-legend-badge" />数据问题</li><li><i className="og-legend-badge og-badge-note" />提示</li><li><i className="og-legend-dash" />有行没连上的关系</li></>}
        {run.evaluation.stability && <li><i className="og-legend-unsteady" />虚线框、点线：不是每次建模都有</li>}
        <li>点对象，只看它和相连的对象</li>
      </ul>
    </div>
    <aside className="og-inspector" aria-label="证据检查">
      <div className="og-inspector-head">证据检查 · 点图里的对象或关系</div>
      {path ? <PathInspector ontology={ontology} path={path} onClearPath={onClearPath} /> : selected.key && <Inspector run={run} selected={selected} findings={findings} />}
      {onAsk && <button type="button" className="og-ask" onClick={onAsk}>询问这个本体：用数据回答业务问题 →</button>}
    </aside>
  </div>;
}
