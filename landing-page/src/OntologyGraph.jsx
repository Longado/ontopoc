import { useEffect, useMemo, useRef, useState } from "react";
import { edgeStats, findingsByType, focusOntology, neighboursOf, rankByDegree, unsteady } from "./ontologyGraphModel.js";
import { edgePath, forceLayout, moveNode } from "./forceLayoutModel.js";
import { PanZoom } from "./PanZoom.jsx";
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

/** "对 / 不对" for one object or relation, plus a rename box for objects that are judged right. */
export function Verdict({ confirm, kind, item }) {
  if (!confirm) return null;
  const d = confirm.decisions[kind][item.key];
  const name = (item.label || item.key);
  return <div className="og-verdict" role="group" aria-label={`你的判断：${name}`}>
    <span>你的判断</span>
    {[["ok", "对"], ["wrong", "不对"]].map(([v, text]) => <button key={v} type="button" aria-pressed={d?.verdict === v} className={`og-v-${v}`} onClick={() => confirm.onVerdict(kind, item.key, v)}>{text}</button>)}
    {kind === "types" && d?.verdict === "ok" && <input aria-label={`${name} 改名为`} placeholder="改名（可选）" maxLength={40} defaultValue={d.label || ""} key={`${item.key}-${d.label || ""}`}
      onBlur={(e) => confirm.onRename(item.key, e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />}
  </div>;
}

function PathInspector({ ontology, path, onClearPath }) {
  const relation = (key) => ontology.relations.find((r) => r.key === key);
  return <div className="og-inspector-body">
    <span className="og-kicker">查询路径</span>
    <h3>{path.text || path.nodes.map((k) => typeLabel(ontology, k)).join(" → ")}</h3>
    {(path.walks || [path]).map((walk, w) => <div key={w} className="og-walk">
      {(path.walks || []).length > 1 && <h4>第 {w + 1} 条路</h4>}
      <ol className="og-steps">{walk.nodes.map((k, i) => <li key={`${k}-${i}`}>{i === 0 ? `从“${typeLabel(ontology, k)}”出发` : `经关系“${relation(walk.edges[i - 1])?.label || relation(walk.edges[i - 1])?.meaning || walk.edges[i - 1]}”到“${typeLabel(ontology, k)}”`}</li>)}</ol>
    </div>)}
    <p>图上高亮的就是{(path.walks || []).length > 1 ? "这几条路" : "这条路"}；数字由代码沿着它在数据里一行行数出来。</p>
    <button type="button" className="pr-link og-inline" onClick={onClearPath}>清除路径，看“{typeLabel(ontology, path.nodes[path.nodes.length - 1])}”的数据检查</button>
  </div>;
}

function Inspector({ run, selected, findings, confirm }) {
  const { ontology } = run;
  const stability = run.evaluation.stability;
  const fit = run.evaluation.data_fit;
  if (selected.kind === "edge") {
    const r = ontology.relations.find((x) => x.key === selected.key);
    const stats = edgeStats(fit, r.key);
    return <div className="og-inspector-body">
      <span className="og-kicker">关系 · {r.key}</span>
      <h3>{typeLabel(ontology, r.from)} {r.label || "→"} {typeLabel(ontology, r.to)}</h3>
      <Verdict confirm={confirm} kind="relations" item={r} />
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
    <Verdict confirm={confirm} kind="types" item={t} />
    {t.rationale && <p>{t.rationale}</p>}
    {t.definition && <p>{t.definition}</p>}
    {t.evidence?.length > 0 && <div className="og-quotes">{t.evidence.map((q, i) => <blockquote key={i}>原文：{q}</blockquote>)}</div>}
    <dl className="og-kv">
      {t.populated_from.length > 0 && <div><dt>来自</dt><dd>{typeSources(t)}</dd></div>}
      {t.attributes.length > 0 && <div><dt>属性</dt><dd>{t.attributes.map((a) => a.path).join("、")}</dd></div>}
      {t.time_field && <div><dt>时间</dt><dd>{t.time_field.path}</dd></div>}
      {stability && stability.types[t.key] !== undefined && <div><dt>{stability.runs} 次建模</dt><dd className={unsteady(stability, "types", t.key) ? "og-warn" : ""}>{unsteady(stability, "types", t.key) ? `只有 ${stability.types[t.key]} 次有它：模型对要不要单独建这个对象拿不准，可以按你的业务决定` : "每次都有"}</dd></div>}
      {metrics && <div><dt>对象数</dt><dd>{metrics.instances[t.key]} 个（按编号去重）{metrics.shared_across_sources[t.key] ? `，其中 ${metrics.shared_across_sources[t.key]} 个在多张表里出现` : ""}{(fit?.missing_across_sources || []).filter((m) => m.type === t.key).map((m) => `；${m.count} 个只在别的表里被引用、在“${m.source}”表里找不到`).join("")}</dd></div>}
    </dl>
    {fit && <h4>数据检查</h4>}
    {!fit ? null : own.length ? <ul className="og-findings">{own.map((f, i) => <li key={i} className={f.severity === "note" ? "og-note" : ""}>{f.severity === "note" ? "提示：" : ""}{FINDING[f.kind](f.detail)}</li>)}</ul> : <p className="og-ok">这个对象没有发现问题。</p>}
  </div>;
}

export function OntologyGraph({ run, onAsk, selected: chosen, onSelect: setSelected, path, onClearPath, reveal, confirm, suggestions = [] }) {
  const { ontology } = run;
  const findings = findingsByType(run.evaluation.data_fit);
  const wrap = useRef(null);
  const canvas = useRef(null);
  const [mode, setMode] = useState("full");   // full, or "focus": the selected object and its neighbours only
  const focusing = mode === "focus";   // the whole graph by default: it can be zoomed and dragged now
  const hub = rankByDegree(ontology)[0]?.key;
  const selected = chosen && (chosen.kind === "edge" ? ontology.relations : ontology.object_types).some((x) => x.key === chosen.key) ? chosen
    : { kind: "node", key: focusing ? hub : ontology.object_types[0]?.key };
  const edge = selected.kind === "edge" && ontology.relations.find((r) => r.key === selected.key);
  const center = edge ? edge.from : selected.key;
  const shown = focusing ? focusOntology(ontology, center, path ? path.nodes : null) : ontology;
  const shownKey = shown.object_types.map((t) => t.key).join("|") + "#" + shown.relations.map((r) => r.key).join("|");
  const base = useMemo(() => forceLayout(shown.object_types.map((t) => ({ id: t.key, label: t.label || t.key, sub: t.key })),
    [...shown.relations, ...suggestions].map((r) => ({ from: r.from, to: r.to }))), [shownKey, suggestions.length]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [moved, setMoved] = useState(null);   // the layout after the person dragged boxes about
  useEffect(() => setMoved(null), [base]);
  const graph = moved || base;
  const at = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
  const lines = shown.relations.filter((r) => at[r.from] && at[r.to]).map((r, _, all) => {
    const twin = all.filter((o) => (o.from === r.from && o.to === r.to) || (o.from === r.to && o.to === r.from)).indexOf(r);
    return { key: r.key, from: r.from, to: r.to, ...edgePath(at[r.from], at[r.to], twin) };
  });
  const hinted = suggestions.filter((x) => at[x.from] && at[x.to]).map((x, i) => ({ key: `hint-${i}`, hint: x, ...edgePath(at[x.from], at[x.to], 0) }));
  const focus = path ? { nodes: new Set(path.nodes), edges: new Set(path.edges) }
    : focusing || selected !== chosen ? null : edge ? { nodes: new Set([edge.from, edge.to]), edges: new Set([edge.key]) } : neighboursOf(ontology, selected.key);
  const dim = (kind, key) => focus && (kind === "node" ? !focus.nodes.has(key) : !focus.edges.has(key)) ? " is-dim" : "";
  const find = (e) => {
    const t = ontology.object_types.find((x) => (x.label || x.key) === e.target.value);
    if (t) { setSelected({ kind: "node", key: t.key }); e.target.value = ""; }
  };
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
    <div className="og-canvas" ref={canvas}>
      <div className="og-bar"><span>{ontology.object_types.length} 个对象 · {ontology.relations.length} 条关系{!focusing && ontology.object_types.length > 2 && <button type="button" className="pr-link og-focus-link" onClick={() => setMode("focus")}>只看选中的周围</button>}</span>
        <span>{run.evaluation.data_fit ? `数据检查：${problemCount} 处问题${noteCount ? `，${noteCount} 处提示` : ""}` : run.evaluation.document_fit ? `${run.evaluation.document_fit.kept} 项都有原文引用` : "未评测"}</span></div>
      {focusing && <div className="og-focusbar">
        <span>{path ? "只显示查询经过的对象" : <>只显示“{typeLabel(ontology, center)}”和相连的 {graph.nodes.length - 1} 个</>}</span>
        {focusing && <label htmlFor="og-find" className="og-find">找对象<input id="og-find" list="og-concepts" placeholder="输入名字" onChange={find} /></label>}
        <datalist id="og-concepts">{rankByDegree(ontology).map((t) => <option key={t.key} value={t.label || t.key} />)}</datalist>
        <button type="button" className="pr-link" onClick={() => setMode("full")}>看全图</button>
      </div>}
      {path && <div className="og-path" role="status"><span>查询路径：{path.text || path.nodes.map((k) => typeLabel(ontology, k)).join(" → ")}</span><button type="button" className="pr-link" onClick={onClearPath}>清除</button></div>}
      <PanZoom width={graph.width} height={graph.height} label="本体关系图" resetKey={shownKey} onNodeDrag={(id, dx, dy) => setMoved((g) => moveNode(g || base, id, dx, dy))}>
          <defs><marker id="og-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="og-arrowhead" /></marker></defs>
          {hinted.map((e) => <g key={e.key} className="og-edge is-suggest"><title>{`代码建议：${e.hint.via.source} 的「${e.hint.via.field}」，${e.hint.linked} / ${e.hint.rows} 行`}</title>
            <path d={e.path} /><text x={e.lx} y={e.ly} textAnchor="middle">建议</text></g>)}
          {lines.map((e) => { const stats = edgeStats(run.evaluation.data_fit, e.key); const rel = ontology.relations.find((r) => r.key === e.key);
            return <g key={e.key} className={`og-edge${isSelected("edge", e.key) ? " is-selected" : ""}${path?.edges.includes(e.key) ? " is-path" : ""}${stats && !stats.complete ? " is-partial" : ""}${unsteady(run.evaluation.stability, "relations", e.key) ? " is-unsteady" : ""}${dim("edge", e.key)}`}
              role="button" tabIndex={0} aria-label={`关系 ${typeLabel(ontology, e.from)} 到 ${typeLabel(ontology, e.to)}`} {...select(setSelected, { kind: "edge", key: e.key })}>
              <path d={e.path} className="og-edge-hit" />
              <path d={e.path} markerEnd="url(#og-arrow)" />
              {rel.label && <text x={e.lx} y={e.ly} textAnchor="middle">{rel.label}</text>}
            </g>; })}
          {graph.nodes.map((n) => { const own = findings[n.id] || []; const count = own.length; const onlyNotes = own.every((f) => f.severity === "note");
            return <g key={n.id} data-key={n.id} data-node={n.id} className={`og-node${isSelected("node", n.id) ? " is-selected" : ""}${path?.nodes.includes(n.id) ? " is-path" : ""}${unsteady(run.evaluation.stability, "types", n.id) ? " is-unsteady" : ""}${confirm?.decisions.types[n.id] ? ` is-${confirm.decisions.types[n.id].verdict}` : ""}${dim("node", n.id)}`} transform={`translate(${n.x},${n.y})`}
              role="button" tabIndex={0} aria-label={`对象 ${n.label}${count ? `，${count} 处数据问题` : ""}`} {...select(setSelected, { kind: "node", key: n.id })}>
              <title>{n.sub}</title>
              <rect width={n.w} height={n.h} rx="10" className="og-node-box" />
              <rect width={n.w} height={5} rx="2" className="og-node-cap" />
              <text x={n.w / 2} y={n.h / 2 + 7} textAnchor="middle" className="og-node-label">{n.label}</text>
              {confirm?.decisions.types[n.id] && <text x={n.w - 8} y={n.h - 6} textAnchor="end" className="og-mark">{confirm.decisions.types[n.id].verdict === "ok" ? "✓" : "✕"}</text>}
              {count > 0 && <g transform={`translate(${n.w - 4},2)`}><title>{`${count} 处${onlyNotes ? "提示" : "数据问题"}，点开看`}</title><circle r="10" className={`og-badge${onlyNotes ? " og-badge-note" : ""}`} /><text textAnchor="middle" y="4" className="og-badge-text">{count}</text></g>}
            </g>; })}
      </PanZoom>
      <ul className="og-legend" aria-label="图例">
        {run.evaluation.data_fit && <><li><i className="og-legend-badge" />红圈里的数字：这个对象有几处数据问题</li><li><i className="og-legend-badge og-badge-note" />提示</li><li><i className="og-legend-dash" />有行没连上的关系</li></>}
        {(ontology.object_types.some((t) => unsteady(run.evaluation.stability, "types", t.key)) || ontology.relations.some((r) => unsteady(run.evaluation.stability, "relations", r.key)))
          && <li><i className="og-legend-unsteady" />虚线框、点线：不是每次建模都有</li>}
        {hinted.length > 0 && <li><i className="og-legend-hint" />虚线"建议"：代码在数据里看到、本体里没有的关系</li>}
        <li>拖动空白处平移，滚轮缩放，拖动方框调整位置</li>
      </ul>
    </div>
    <aside className="og-inspector" aria-label="证据检查">
      <div className="og-inspector-head">证据检查 · 点图里的对象或关系</div>
      {path ? <PathInspector ontology={ontology} path={path} onClearPath={onClearPath} /> : selected.key && <Inspector run={run} selected={selected} findings={findings} confirm={confirm} />}
      {onAsk && <button type="button" className="og-ask" onClick={onAsk}>询问这个本体：用数据回答业务问题 →</button>}
    </aside>
  </div>;
}
