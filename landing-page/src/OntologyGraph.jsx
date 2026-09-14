import { useState } from "react";
import { edgeStats, findingsByType, layoutGraph } from "./ontologyGraphModel.js";
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

function Inspector({ run, selected, findings }) {
  const { ontology } = run;
  const fit = run.evaluation.data_fit;
  if (selected.kind === "edge") {
    const r = ontology.relations.find((x) => x.key === selected.key);
    const stats = edgeStats(fit, r.key);
    return <div className="og-inspector-body">
      <span className="og-kicker">关系 · {r.key}</span>
      <h3>{typeLabel(ontology, r.from)} {r.label || "→"} {typeLabel(ontology, r.to)}</h3>
      <p>{r.meaning}</p>
      <dl className="og-kv"><div><dt>所在表</dt><dd>{r.source}</dd></div>
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
    <dl className="og-kv">
      <div><dt>来自</dt><dd>{typeSources(t)}</dd></div>
      {t.attributes.length > 0 && <div><dt>属性</dt><dd>{t.attributes.map((a) => a.path).join("、")}</dd></div>}
      {t.time_field && <div><dt>时间</dt><dd>{t.time_field.path}</dd></div>}
      {metrics && <div><dt>对象数</dt><dd>{metrics.instances[t.key]} 个{metrics.shared_across_sources[t.key] ? `，其中 ${metrics.shared_across_sources[t.key]} 个在多张表里出现` : ""}</dd></div>}
    </dl>
    <h4>数据检查</h4>
    {own.length ? <ul className="og-findings">{own.map((f, i) => <li key={i}>{FINDING[f.kind](f.detail)}</li>)}</ul> : <p className="og-ok">这个对象没有发现问题。</p>}
  </div>;
}

export function OntologyGraph({ run }) {
  const { ontology } = run;
  const graph = layoutGraph(ontology);
  const findings = findingsByType(run.evaluation.data_fit);
  const [selected, setSelected] = useState({ kind: "node", key: graph.nodes[0]?.key });
  const problemCount = Object.values(findings).reduce((n, list) => n + list.length, 0);
  const isSelected = (kind, key) => selected.kind === kind && selected.key === key;
  return <div className="og-wrap">
    <div className="og-canvas">
      <div className="og-bar"><span>本体 · {graph.nodes.length} 个对象 · {graph.edges.length} 条关系</span>
        <span>{run.evaluation.data_fit ? `数据检查发现 ${problemCount} 处问题` : "未评测"}</span></div>
      <div className="og-scroll">
        <svg viewBox={`0 0 ${graph.width} ${graph.height}`} style={{ width: "100%", minWidth: Math.min(graph.width, 560), maxWidth: graph.width }} role="group" aria-label="本体关系图">
          <defs><marker id="og-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="og-arrowhead" /></marker></defs>
          {graph.edges.map((e) => { const stats = edgeStats(run.evaluation.data_fit, e.key); const rel = ontology.relations.find((r) => r.key === e.key);
            return <g key={e.key} className={`og-edge${isSelected("edge", e.key) ? " is-selected" : ""}${stats && !stats.complete ? " is-partial" : ""}`}
              role="button" tabIndex={0} aria-label={`关系 ${typeLabel(ontology, e.from)} 到 ${typeLabel(ontology, e.to)}`} {...select(setSelected, { kind: "edge", key: e.key })}>
              <path d={e.path} markerEnd="url(#og-arrow)" />
              {rel.label && <text x={e.lx} y={e.ly - 6} textAnchor="middle">{rel.label}</text>}
            </g>; })}
          {graph.nodes.map((n) => { const count = (findings[n.key] || []).length;
            return <g key={n.key} className={`og-node${isSelected("node", n.key) ? " is-selected" : ""}`} transform={`translate(${n.x},${n.y})`}
              role="button" tabIndex={0} aria-label={`对象 ${n.label}${count ? `，${count} 处数据问题` : ""}`} {...select(setSelected, { kind: "node", key: n.key })}>
              <rect width={n.w} height={n.h} className="og-node-box" />
              <rect width={40} height={n.h} className="og-node-side" />
              <text x={54} y={26} className="og-node-key">{n.key.length > 18 ? `${n.key.slice(0, 18)}…` : n.key}</text>
              <text x={54} y={47} className="og-node-label">{n.label}</text>
              {count > 0 && <g transform={`translate(${n.w - 14},0)`}><circle r="11" className="og-badge" /><text textAnchor="middle" y="4" className="og-badge-text">{count}</text></g>}
            </g>; })}
        </svg>
      </div>
    </div>
    <aside className="og-inspector" aria-label="证据检查">
      <div className="og-inspector-head">证据检查 · 点图里的对象或关系</div>
      {selected.key && <Inspector run={run} selected={selected} findings={findings} />}
    </aside>
  </div>;
}
