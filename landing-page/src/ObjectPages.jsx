import { useEffect, useState } from "react";

import { Verdict } from "./OntologyGraph.jsx";
import { focusOntology, layoutGraph } from "./ontologyGraphModel.js";
import { fieldNote, formOf } from "./ontologyHandoverModel.js";
import { objectCards, objectRelations } from "./workspaceModel.js";

const VERDICT_TEXT = { ok: "判对", wrong: "判错" };

/** 本体管理: one card per object, the way DIP lists its business ontologies. */
export function ObjectCards({ run, decisions, onOpen }) {
  const cards = objectCards(run, decisions);
  return <section className="os-objects" aria-labelledby="os-objects-title">
    <div className="os-objects-head"><h2 id="os-objects-title">业务对象 <small>({cards.length})</small></h2></div>
    <div className="os-object-grid">{cards.map((c) => <button key={c.key} type="button" className={`os-object-card${c.verdict ? ` is-${c.verdict}` : ""}`} onClick={() => onOpen(c.key)}>
      <span className="os-object-title"><i aria-hidden="true" /><b>{c.renamed || c.label}</b>{c.verdict && <em>{VERDICT_TEXT[c.verdict]}</em>}</span>
      <span className="os-object-note">{c.note || `按 ${c.identity.join(" + ")} 识别`}</span>
      <span className="os-object-meta">{c.count !== null && <>共 {c.count.toLocaleString("zh-CN")} 个<i aria-hidden="true">|</i></>}包含关系 {c.relations} 条</span>
      <span className="os-object-from">来自 {c.sources.join("、")}</span>
    </button>)}</div>
  </section>;
}

const SUBS = [["overview", "概览"], ["fields", "属性"], ["rows", "数据"], ["confirm", "确认"]];

/** One object's own page: 概览 / 属性 / 数据 / 确认, as DIP's object page has 概览 / 属性 / 对象. */
export function ObjectDetail({ run, typeKey, confirm, onBack, onOpen, onSaveConfirm }) {
  const [sub, setSub] = useState("overview");
  useEffect(() => setSub("overview"), [typeKey]);
  const card = objectCards(run, confirm?.decisions).find((c) => c.key === typeKey);
  const type = run.ontology.object_types.find((t) => t.key === typeKey);
  if (!card) return <p className="pr-muted">这份本体里没有这个对象。<button type="button" className="pr-link" onClick={onBack}>返回</button></p>;
  const relations = objectRelations(run, typeKey);
  return <div className="os-object-page">
    <nav className="os-object-side" aria-label={`${card.label} 的页面`}>
      <button type="button" className="os-back" onClick={onBack}>← 返回</button>
      <p className="os-object-name"><i aria-hidden="true" />{card.renamed || card.label}</p>
      {SUBS.map(([key, text]) => <button key={key} type="button" aria-current={sub === key ? "page" : undefined} disabled={key === "rows" && !run.saved_as} onClick={() => setSub(key)}>{text}</button>)}
    </nav>
    <div className="os-object-body">
      <header className="os-object-header"><h2>{card.renamed || card.label} <small>({typeKey})</small></h2>{card.note && <p className="pr-muted">{card.note}</p>}</header>
      {sub === "overview" && <div className="os-object-overview">
        <section className="pr-card"><h3>基本信息</h3><dl className="os-facts">
          <dt>来自表</dt><dd>{card.sources.join("、")}</dd>
          <dt>识别字段</dt><dd>{card.identity.join(" + ")}</dd>
          {card.count !== null && <><dt>数据里有</dt><dd>{card.count.toLocaleString("zh-CN")} 个</dd></>}
          <dt>包含关系</dt><dd>{card.relations} 条</dd>
          <dt>你的判断</dt><dd>{card.verdict ? VERDICT_TEXT[card.verdict] : "还没判"}</dd>
        </dl></section>
        <section className="pr-card"><h3>本体关系 <small>({relations.length})</small></h3>
          {relations.length ? <MiniGraph run={run} typeKey={typeKey} onOpen={onOpen} /> : <p className="pr-muted">它和别的对象没有关系。</p>}</section>
        <section className="pr-card os-span"><div className="pr-card-head"><h3>属性 <small>({fieldsOf(run, type).length})</small></h3><button type="button" className="pr-link" onClick={() => setSub("fields")}>看全部</button></div>
          <ul className="os-field-tags">{fieldsOf(run, type).slice(0, 8).map((f) => <li key={f.path}>{f.path}{f.identity && <em className="is-key">主键</em>}{f.type && <em>{f.type}</em>}</li>)}</ul></section>
      </div>}
      {sub === "fields" && <FieldsTable run={run} type={type} />}
      {sub === "rows" && <ObjectRows run={run} typeKey={typeKey} />}
      {sub === "confirm" && <section className="pr-card os-object-confirm">
        <h3>这个对象在业务上对不对</h3>
        {confirm ? <><Verdict confirm={confirm} kind="types" item={type} />
          {relations.length > 0 && <><h3>它的关系</h3><ul className="os-list">{relations.map((r) => { const rel = run.ontology.relations.find((x) => x.key === r.key);
            return <li key={r.key} className="os-object-relation"><span>{r.text}</span><Verdict confirm={confirm} kind="relations" item={rel} /></li>; })}</ul></>}
          <p className="pr-muted">判断先记在这一页上，回到"本体管理"首页底部一起保存。<button type="button" className="pr-link" onClick={onSaveConfirm}>去保存</button></p></>
          : <p className="pr-muted">这份结果不能确认。</p>}
      </section>}
    </div>
  </div>;
}

function fieldsOf(run, type) {
  const form = formOf(run)?.types.find((t) => t.type === type.key);
  if (form) return form.fields;
  const identity = new Set(type.populated_from.flatMap((p) => Object.values(p.identity)));
  return [...identity].map((path) => ({ path, identity: true })).concat(type.attributes.filter((a) => !identity.has(a.path)).map((a) => ({ path: a.path, identity: false })));
}

function FieldsTable({ run, type }) {
  const fields = fieldsOf(run, type);
  const form = formOf(run)?.types.find((t) => t.type === type.key);
  const profiled = Boolean(form);
  return <section className="pr-card"><div className="pr-card-head"><h3>属性列表</h3><span className="pr-muted">{fields.length} 个</span></div>
    {form?.needs_single_key && <p className="pr-note os-tone-warn">靠 {form.identity_fields.join(" + ")} 这几个字段一起识别。DIP 每张表只收一个主键，导入前要把它们合成一个，或者改建模。</p>}
    <div className="os-table-scroll"><table className="os-fields">
      <thead><tr><th scope="col">序号</th><th scope="col">字段</th>{profiled && <><th scope="col">类型</th><th scope="col">长度</th><th scope="col">空值</th></>}<th scope="col">来源</th></tr></thead>
      <tbody>{fields.map((f, i) => <tr key={f.path}><td>{i + 1}</td><td>{f.path}{f.identity && <em className="os-tag is-key">主键</em>}</td>
        {profiled && <><td>{f.type || "—"}</td><td>{f.length || "—"}</td><td>{fieldNote(f) || "—"}</td></>}<td>{(f.sources || []).join("、") || "数据导入"}</td></tr>)}</tbody>
    </table></div>
    {!profiled && <p className="pr-muted">这次运行保存得早，没有逐列的类型和长度。重新上传同一份文件就能看到。</p>}
    <p className="pr-muted">类型、长度、空值由代码拿每一行读出来；中文名、描述、展示字段只有人能写，导入 DIP 时再填。</p>
  </section>;
}

function ObjectRows({ run, typeKey }) {
  const [page, setPage] = useState(1);
  const [state, setState] = useState({ status: "loading" });
  useEffect(() => { setPage(1); }, [typeKey]);
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, status: "loading" }));
    fetch(`/api/ontology/runs/${run.saved_as}/objects/${encodeURIComponent(typeKey)}?page=${page}`, { cache: "no-store" })
      .then(async (r) => { const body = await r.json().catch(() => ({})); if (!r.ok) throw new Error(body.error || `服务返回 ${r.status}`); return body; })
      .then((data) => live && setState({ status: "ready", data }))
      .catch((e) => live && setState({ status: "error", error: e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message }));
    return () => { live = false; };
  }, [run.saved_as, typeKey, page]);
  const d = state.data;
  const pages = d ? Math.max(1, Math.ceil(d.total / d.size)) : 1;
  return <section className="pr-card"><div className="pr-card-head"><h3>数据列表</h3>{d && <span className="pr-muted">共 {d.total.toLocaleString("zh-CN")} 个</span>}</div>
    {state.status === "error" && <p role="alert" className="pr-error">{state.error}</p>}
    {d && <div className={`os-table-scroll${state.status === "loading" ? " is-loading" : ""}`}><table className="os-fields">
      <thead><tr><th scope="col">序号</th>{d.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
      <tbody>{d.rows.map((row, i) => <tr key={i}><td>{(d.page - 1) * d.size + i + 1}</td>{d.columns.map((c) => <td key={c}>{row[c] ?? "—"}</td>)}</tr>)}</tbody>
    </table></div>}
    {state.status === "loading" && !d && <p className="pr-muted">正在读取…</p>}
    {d && pages > 1 && <div className="os-pager"><button type="button" className="pr-link" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
      <span>第 {page} / {pages} 页</span><button type="button" className="pr-link" disabled={page >= pages} onClick={() => setPage(page + 1)}>下一页</button></div>}
    <p className="pr-muted">每一行是本体在数据里认出的一个{d?.label || "对象"}，同一个对象出现在几张表里时合成一行；几张表写得不一样时显示先读到的那个，差异看"数据体检"。</p>
  </section>;
}

/** The object and the ones it connects to; clicking another opens its page. */
function MiniGraph({ run, typeKey, onOpen }) {
  const graph = layoutGraph(focusOntology(run.ontology, typeKey));
  return <div className="os-mini-graph"><svg viewBox={`0 0 ${graph.width} ${graph.height}`} role="group" aria-label="和它相连的对象">
    <defs><marker id="os-mini-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" /></marker></defs>
    {graph.edges.map((e) => <path key={e.key} d={e.path} className="os-mini-edge" markerEnd="url(#os-mini-arrow)" />)}
    {graph.nodes.map((n) => <g key={n.key} transform={`translate(${n.x},${n.y})`} className={`os-mini-node${n.key === typeKey ? " is-self" : ""}`}
      role={n.key === typeKey ? undefined : "button"} tabIndex={n.key === typeKey ? undefined : 0} aria-label={n.key === typeKey ? undefined : `打开 ${n.label}`}
      onClick={() => n.key !== typeKey && onOpen(n.key)} onKeyDown={(e) => { if (n.key !== typeKey && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onOpen(n.key); } }}>
      <rect width={n.w} height={n.h} rx="8" /><rect width={n.w} height={14} rx="4" className="os-mini-cap" /><text x={n.w / 2} y={n.h / 2 + 12} textAnchor="middle">{n.label}</text>
    </g>)}
  </svg></div>;
}
