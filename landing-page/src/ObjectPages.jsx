import { useEffect, useState } from "react";

import { Verdict } from "./OntologyGraph.jsx";
import { focusOntology, layoutGraph } from "./ontologyGraphModel.js";
import { formOf as formOfRun } from "./ontologyHandoverModel.js";
import { objectCards, objectRelations } from "./workspaceModel.js";
import { filled, filterCards, rowsCsv } from "./visualModel.js";
import { editForm, formOf } from "./formModel.js";

const VERDICT_TEXT = { ok: "判对", wrong: "判错" };

/** 本体管理: one card per object, the way DIP lists its business ontologies. */
const VERDICT_FILTERS = [["all", "全部"], ["ok", "判对"], ["wrong", "判错"], ["none", "没判"]];

export function ObjectCards({ run, decisions, onOpen }) {
  const [query, setQuery] = useState("");
  const [verdict, setVerdict] = useState("all");
  const [layout, setLayout] = useState("cards");
  const all = objectCards(run, decisions);
  const cards = filterCards(all, query, verdict);
  const meta = (c) => <>{c.count !== null && <>共 {c.count.toLocaleString("zh-CN")} 个<i aria-hidden="true">|</i></>}关系 {c.relations} 条</>;
  return <section className="os-objects" aria-labelledby="os-objects-title">
    <div className="os-objects-head"><h2 id="os-objects-title">业务对象 <small>({all.length})</small></h2>
      <div className="os-toolbar">
        <label className="os-search"><span className="sr-only">按名称找对象</span><input id="os-object-search" value={query} placeholder="输入名称搜索" onChange={(e) => setQuery(e.target.value)} /></label>
        <div className="og-toggle" role="group" aria-label="按判断筛选">{VERDICT_FILTERS.map(([k, t]) => <button key={k} type="button" aria-pressed={verdict === k} onClick={() => setVerdict(k)}>{t}</button>)}</div>
        <div className="og-toggle" role="group" aria-label="显示方式">{[["cards", "卡片"], ["list", "列表"]].map(([k, t]) => <button key={k} type="button" aria-pressed={layout === k} onClick={() => setLayout(k)}>{t}</button>)}</div>
      </div></div>
    {!cards.length && <p className="pr-muted">没有符合条件的对象。</p>}
    {layout === "cards" ? <div className="os-object-grid">{cards.map((c) => <button key={c.key} type="button" className={`os-object-card${c.verdict ? ` is-${c.verdict}` : ""}`} onClick={() => onOpen(c.key)}>
      <span className="os-object-title"><i aria-hidden="true" /><b>{c.renamed || c.label}</b>{c.verdict && <em>{VERDICT_TEXT[c.verdict]}</em>}</span>
      <span className="os-object-note">{c.note || `按 ${c.identity.join(" + ")} 识别`}</span>
      <span className="os-object-meta">{meta(c)}</span>
      <span className="os-object-from">{c.sources.join("、")}</span>
    </button>)}</div>
      : <div className="os-table-scroll pr-card"><table className="os-fields os-object-table">
        <thead><tr><th scope="col">对象</th><th scope="col">数量</th><th scope="col">关系</th><th scope="col">来自表</th><th scope="col">判断</th></tr></thead>
        <tbody>{cards.map((c) => <tr key={c.key} onClick={() => onOpen(c.key)}><td><button type="button" className="pr-link" onClick={() => onOpen(c.key)}>{c.renamed || c.label}</button></td>
          <td>{c.count?.toLocaleString("zh-CN") ?? "—"}</td><td>{c.relations}</td><td>{c.sources.join("、")}</td><td>{c.verdict ? <em className={`os-verdict is-${c.verdict}`}>{VERDICT_TEXT[c.verdict]}</em> : "—"}</td></tr>)}</tbody>
      </table></div>}
  </section>;
}

const SUBS = [["overview", "概览"], ["fields", "属性"], ["rows", "数据"], ["confirm", "确认"]];

/** One object's own page: 概览 / 属性 / 数据 / 确认, as DIP's object page has 概览 / 属性 / 对象. */
export function ObjectDetail({ run, typeKey, confirm, onBack, onOpen, onSaveConfirm, form }) {
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
      {sub === "fields" && <FieldsTable run={run} type={type} form={form} />}
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
  const form = formOfRun(run)?.types.find((t) => t.type === type.key);
  if (form) return form.fields;
  const identity = new Set(type.populated_from.flatMap((p) => Object.values(p.identity)));
  return [...identity].map((path) => ({ path, identity: true })).concat(type.attributes.filter((a) => !identity.has(a.path)).map((a) => ({ path: a.path, identity: false })));
}

function FieldsTable({ run, type, form }) {
  const fields = fieldsOf(run, type);
  const [draft, setDraft] = useState(() => formOf(run, type.key));
  useEffect(() => setDraft(formOf(run, type.key)), [run, type.key]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(formOf(run, type.key));
  const shape = formOfHandover(run, type.key);
  const profiled = Boolean(shape);
  const set = (path, key, value) => setDraft((d) => editForm(d, path, key, value));
  const mark = (x) => x?.drafted && <em className="os-drafted" title="模型起草的，还没人改过">模型</em>;
  return <section className="pr-card os-form-card">
    <div className="pr-card-head"><h3>属性列表 <small>{fields.length}</small></h3>
      {form && <div className="os-toolbar">
        <button type="button" className="pr-link" disabled={!form.canDraft || form.drafting} onClick={form.onDraft} title="一次模型调用，起草中文名、描述和展示字段；你改过的不会被覆盖">{form.drafting ? "起草中…" : "✦ 起草"}</button>
        <button type="button" className="pr-primary os-save-form" disabled={!form.canSave || !dirty || form.saving} onClick={() => form.onSave(type.key, draft)}>{form.saving ? "保存中…" : "保存"}</button>
      </div>}</div>
    {form?.error && <p role="alert" className="pr-error">{form.error}</p>}
    <div className="os-form-head">
      <label htmlFor="os-type-label">中文名</label><span><input id="os-type-label" value={draft.label} maxLength={40} onChange={(e) => set(null, "label", e.target.value)} />{mark(draft.drafted && draft.label && draft)}</span>
      <label htmlFor="os-type-desc">描述</label><span><input id="os-type-desc" value={draft.description} maxLength={200} onChange={(e) => set(null, "description", e.target.value)} /></span>
    </div>
    {shape?.needs_single_key && <p className="pr-note os-tone-warn">靠 {shape.identity_fields.join(" + ")} 这几个字段一起识别。DIP 每张表只收一个主键，导入前要把它们合成一个，或者改建模。</p>}
    <div className="os-table-scroll"><table className="os-fields os-form-fields">
      <thead><tr><th scope="col">字段</th><th scope="col">中文名</th><th scope="col">描述</th><th scope="col" title="展示给人看的字段，每个对象一个">展示</th>{profiled && <><th scope="col">类型</th><th scope="col">长度</th><th scope="col" title="有值的行占多少">填充</th></>}</tr></thead>
      <tbody>{fields.map((f) => { const x = draft.fields[f.path]; return <tr key={f.path}>
        <td>{f.path}{f.identity && <em className="os-tag is-key">主键</em>}</td>
        <td><span className="os-cell-edit"><input aria-label={`${f.path} 的中文名`} value={x?.label || ""} maxLength={40} onChange={(e) => set(f.path, "label", e.target.value)} />{mark(x)}</span></td>
        <td><input aria-label={`${f.path} 的描述`} className="os-desc-input" value={x?.description || ""} maxLength={200} onChange={(e) => set(f.path, "description", e.target.value)} /></td>
        <td><input type="radio" name={`display-${type.key}`} aria-label={`用 ${f.path} 展示`} checked={draft.display_field === f.path} onChange={() => set(null, "display_field", f.path)} /></td>
        {profiled && <><td><TypeChip type={f.type} /></td><td>{f.length || "—"}</td><td><FillBar field={f} rows={f.rows} /></td></>}
      </tr>; })}</tbody>
    </table></div>
    {!profiled && <p className="pr-muted">这次运行没有逐列的类型和长度，重新上传可看到。</p>}
    {run.evaluation.form?.rejected?.length > 0 && <details className="os-how"><summary>起草时剔除的 {run.evaluation.form.rejected.length} 项</summary>
      <ul>{run.evaluation.form.rejected.map((r, i) => <li key={i}>{r.item}：{r.reason}</li>)}</ul></details>}
  </section>;
}

const formOfHandover = (run, key) => formOfRun(run)?.types.find((t) => t.type === key);

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
  const [saving, setSaving] = useState("");
  async function download() {
    setSaving("…");
    try {
      const r = await fetch(`/api/ontology/runs/${run.saved_as}/objects/${encodeURIComponent(typeKey)}?all=1`, { cache: "no-store" });
      const all = await r.json();
      if (!r.ok) throw new Error(all.error || `服务返回 ${r.status}`);
      const url = URL.createObjectURL(new Blob([rowsCsv(all.columns, all.rows)], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = `${all.label}.csv`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSaving("");
    } catch (e) { setSaving(e.message === "Failed to fetch" ? "连不上本机建模服务" : e.message); }
  }
  return <section className="pr-card"><div className="pr-card-head"><h3 title="每行是本体在数据里认出的一个对象；同一个对象出现在几张表里时合成一行，写得不一样时显示先读到的那个">数据列表</h3>
    <div className="os-toolbar">{d && <span className="pr-muted">共 {d.total.toLocaleString("zh-CN")} 个</span>}
      <button type="button" className="pr-link os-download" disabled={!d || saving === "…"} onClick={download}>{saving === "…" ? "准备中…" : "下载 CSV"}</button>
      {saving && saving !== "…" && <span role="alert" className="pr-error">{saving}</span>}</div></div>
    {state.status === "error" && <p role="alert" className="pr-error">{state.error}</p>}
    {d && <div className={`os-table-scroll${state.status === "loading" ? " is-loading" : ""}`}><table className="os-fields">
      <thead><tr><th scope="col">序号</th>{d.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
      <tbody>{d.rows.map((row, i) => <tr key={i}><td>{(d.page - 1) * d.size + i + 1}</td>{d.columns.map((c) => <td key={c}>{row[c] ?? "—"}</td>)}</tr>)}</tbody>
    </table></div>}
    {state.status === "loading" && !d && <p className="pr-muted">正在读取…</p>}
    {d && pages > 1 && <div className="os-pager"><button type="button" className="pr-link" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
      <span>第 {page} / {pages} 页</span><button type="button" className="pr-link" disabled={page >= pages} onClick={() => setPage(page + 1)}>下一页</button></div>}
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

export function TypeChip({ type }) {
  return <em className={`os-type os-type-${(type || "none").toLowerCase()}`}>{type || "全空"}</em>;
}

/** How full a column is, drawn: the bar is the share of rows with a value. */
export function FillBar({ field, rows }) {
  const f = filled(field, rows);
  if (!f) return "—";
  return <span className="os-fill" title={`${(f.rows - f.empty).toLocaleString("zh-CN")} / ${f.rows.toLocaleString("zh-CN")} 行有值`}>
    <span className="os-fill-track"><i style={{ width: `${f.share}%` }} className={f.share < 100 ? "is-gap" : ""} /></span><small>{f.share}%</small></span>;
}

/** A module's own places down the left, one shown at a time: the way DIP splits a module instead of stacking it. */
export function SubLayout({ label, items, active, onChange, children }) {
  return <div className="os-sublayout">
    <nav className="os-subnav" aria-label={label}>{items.map(([key, text, count]) => <button key={key} type="button" aria-current={active === key ? "page" : undefined} onClick={() => onChange(key)}>
      <span>{text}</span>{count && <small>{count}</small>}</button>)}</nav>
    <div className="os-subbody">{children}</div>
  </div>;
}
