import { useEffect, useMemo, useRef, useState } from "react";
import { OntologyGraph } from "./OntologyGraph.jsx";
import { definitionRun, libraryEntries } from "./ontologyLibraryModel.js";
import { graphSelection, mappingKey, updateMapping } from "./ontologyReferenceModel.js";
import "./DomainReference.css";

const KINDS = { object: "对象", relation: "关系", property: "属性" };
const GROUPS = { mapped: "已对应", only_reference: "仅参考有", only_local: "仅本次有", different: "约束不同", unchecked: "当前无法检查", not_applicable: "本次不适用" };
async function read(url, payload) {
  const response = await fetch(url, payload ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) } : { cache: "no-store" });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "读取失败，请重试。");
  return body;
}

export function DomainReference({ run, onUpdate }) {
  const [context, setContext] = useState(null);
  const [entries, setEntries] = useState([]);
  const [definition, setDefinition] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [preview, setPreview] = useState(null);
  const [review, setReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("object");
  const [owner, setOwner] = useState("");
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("different");
  const [graph, setGraph] = useState(null);
  const [selected, setSelected] = useState(null);
  const [retry, setRetry] = useState(0);
  const dialog = useRef(null);
  const sequence = useRef(0);
  const definitionGraph = useMemo(() => definition ? definitionRun(definition) : null, [definition]);

  function restore(ctx) {
    setReview(false);
    setDefinition(ctx.definition); setMappings(ctx.stale.length ? [] : ctx.record?.mappings || []);
    setPreview(ctx.stale.length ? null : ctx.record?.diff || null); setDirty(false); setError("");
    setKind("object"); setOwner(""); setSearch("");
  }
  useEffect(() => {
    const turn = ++sequence.current;
    setContext(null); setDefinition(null); setError("");
    if (!run.saved_as) return;
    setBusy(true);
    Promise.all([read(`/api/ontology/runs/${run.saved_as}/reference`), read("/api/ontology/library")])
      .then(([ctx, catalogue]) => { if (turn === sequence.current) { setContext(ctx); setEntries(catalogue.entries); restore(ctx); } })
      .catch(e => { if (turn === sequence.current) setError(e.message); })
      .finally(() => { if (turn === sequence.current) setBusy(false); });
    return () => { sequence.current++; };
  }, [run.saved_as, run.ontology, run.confirmation, retry]);

  async function choose(id) {
    setReview(false);
    const turn = ++sequence.current;
    setDefinition(null); setPreview(null); setMappings([]); setDirty(true); setError(""); setKind("object"); setOwner(""); setSearch("");
    if (!id) return;
    setBusy(true);
    try { const d = await read(`/api/ontology/library/${id}`); if (turn === sequence.current) setDefinition(d); }
    catch (e) { if (turn === sequence.current) setError(e.message); }
    finally { if (turn === sequence.current) setBusy(false); }
  }
  function change(row, next) {
    setMappings(old => updateMapping(old, row, next, definition)); setDirty(true); setPreview(null); setError("");
  }
  async function compare(save) {
    const turn = sequence.current;
    setBusy(true); setError("");
    try {
      const payload = { saved_as: run.saved_as, reference_id: definition.entry.id, reference_sha256: definition.sha256,
        run_sha256: context.run_sha256, mappings, ...(save ? { confirmed: true } : {}) };
      const body = await read(`/api/ontology/reference/${save ? "confirm" : "preview"}`, payload);
      if (turn !== sequence.current) return;
      if (save) onUpdate(body);
      else { setPreview(body.diff); setReview(true); setGroup(body.diff.different.length ? "different" : "mapped"); }
    } catch (e) { if (turn === sequence.current) setError(e.message); }
    finally { if (turn === sequence.current) setBusy(false); }
  }
  function showGraph(side, row) {
    const selection = graphSelection(side === "reference" ? definitionGraph : run, row, side);
    if (!selection) { setError("该项尚未解析到图中，请查看参考的来源与支持范围。"); return; }
    setGraph(side); setSelected(selection);
    dialog.current.showModal();
  }
  const chosenOwner = owner || definition?.entity_types[0]?.id;
  const entity = definition?.entity_types.find(e => e.id === chosenOwner);
  const decisions = new Map(mappings.map(m => [mappingKey(m), m]));
  const objectMap = Object.fromEntries(mappings.filter(m => m.kind === "object" && m.local).map(m => [m.reference, m.local]));
  const rows = !definition ? [] : (kind === "object" ? definition.entity_types.map(e => ({ ...e, kind, reference: e.id }))
    : kind === "relation" ? definition.relationships.map(r => ({ ...r, kind, reference: r.id }))
      : (entity?.properties || []).map(p => ({ ...p, kind, owner: entity.id, reference: p.id })));
  const shown = rows.filter(r => `${r.name} ${r.id} ${r.description || ""}`.toLowerCase().includes(search.trim().toLowerCase()));
  const filtered = libraryEntries(entries, query, "");
  const options = entries.filter(e => e.id === definition?.entry.id || filtered.includes(e));

  return <section className={`pr-card dr-panel${definition ? " has-definition" : ""}`} aria-label="领域参考对照">
    <div className="pr-card-head"><h2>领域参考对照</h2>{context?.record && !dirty && !context.stale.length && <span className="dr-saved">已保存人工对应</span>}</div>
    <p className="pr-muted">选一份领域参考，指定它与本次本体的对应，再看差异。参考不是标准答案；未对应不代表建模错误。</p>
    {!run.saved_as ? <p className="pr-note">上传自己的文件后，可保存领域参考对应。</p> : <>
      {error && <p role="alert" className="pr-error">{error} <button type="button" className="pr-link" onClick={() => setRetry(n => n + 1)}>重新读取</button></p>}
      {context?.stale.map(text => <p key={text} role="alert" className="pr-note">{text} 旧对应已保留在运行记录；本页从空白对应重新核对。</p>)}
      <div className="dr-picker">
        <input type="search" aria-label="搜索领域参考" placeholder="搜索领域或关键词" value={query} onChange={e => setQuery(e.target.value)} disabled={busy} />
        <select aria-label="选择领域参考" value={definition?.entry.id || ""} disabled={busy || !context} onChange={e => choose(e.target.value)}>
          <option value="">选择本体库参考</option>{options.map(e => <option key={e.id} value={e.id}>{e.title} · {e.category}</option>)}
        </select>
      </div>
      {busy && <p role="status" className="pr-muted">正在处理…</p>}
      {definition && context && <>
        <details className="dr-source"><summary>来源与支持范围 · {definition.entry.title}</summary>
          <p><a href={definition.entry.source_url} target="_blank" rel="noreferrer">原始本体</a> · 版本 {definition.entry.commit.slice(0, 7)} · {definition.metadata.author}</p>
          <p className="pr-muted">按原始 IRI 区分概念。只比较声明与字段信息，不计算业务质量分，不修改本体或问答结果。</p>
          {definition.warnings.map((w, i) => <p key={i} className="pr-muted">{w.message}</p>)}
        </details>
        {!review && <><div className="dr-mapping-tools"><div className="dr-tabs" role="group" aria-label="对应类型">
          {Object.entries(KINDS).map(([key, label]) => <button type="button" key={key} aria-pressed={kind === key} onClick={() => { setKind(key); setSearch(""); }}>{label}对应</button>)}
        </div>
        <div className="dr-picker">
          {kind === "property" && <select aria-label="选择参考对象的属性" value={chosenOwner} onChange={e => setOwner(e.target.value)}>
            {definition.entity_types.map(e => <option key={e.id} value={e.id}>{e.name}{objectMap[e.id] ? " · 已对应对象" : " · 先对应对象"}</option>)}
          </select>}
          <input type="search" aria-label="查找参考项" placeholder={`查找${KINDS[kind]}名称或 IRI`} value={search} onChange={e => setSearch(e.target.value)} />
        </div></div>
        <div className="dr-mappings" aria-label="人工指定对应">
          {!shown.length && <p className="pr-muted">没有匹配的参考项。</p>}
          {shown.map(row => {
            const key = mappingKey(row), decision = decisions.get(key);
            const localObject = context.local.objects.find(o => o.key === objectMap[row.owner]);
            const choices = kind === "object" ? context.local.objects.map(o => [o.key, o.label])
              : kind === "relation" ? context.local.relations.map(r => [r.key, `${context.local.objects.find(o => o.key === r.from)?.label || r.from} → ${context.local.objects.find(o => o.key === r.to)?.label || r.to} · ${r.label || r.meaning || r.key}`])
                : (localObject?.fields || []).map(f => [JSON.stringify([f.source, f.path]), `${f.source}.${f.path}`]);
            const base = { kind, reference: row.reference, ...(row.owner ? { owner: row.owner } : {}) };
            const value = decision ? decision.local ? (kind === "property" ? JSON.stringify([decision.local.source, decision.local.path]) : decision.local) : "__skip" : "";
            return <div className="dr-mapping-row" key={key}>
              <div className="dr-name"><b title={row.id}>{row.name}</b><small>{kind === "relation" ? `${definition.entity_types.find(e => e.id === row.from)?.name || "端点未解析"} → ${definition.entity_types.find(e => e.id === row.to)?.name || "端点未解析"}` : row.type || "参考对象"}</small>
                <button className="pr-link" type="button" aria-label={`查看参考 ${row.name}`} onClick={() => showGraph("reference", row)}>看参考图</button></div>
              <div className="dr-choice"><select aria-label={`${row.name} 对应${KINDS[kind]}`} disabled={busy} value={value} onChange={e => {
                const v = e.target.value;
                change(base, !v ? null : v === "__skip" ? { ...base, reason: "" } : { ...base, local: kind === "property" ? { source: JSON.parse(v)[0], path: JSON.parse(v)[1] } : v });
              }}><option value="">{kind === "property" && !localObject ? "先对应所属对象" : "尚未指定对应"}</option>
                {choices.map(([v, text]) => <option key={v} value={v}>{text}</option>)}<option value="__skip">本次不适用（写原因）</option></select>
                {value === "__skip" && <input aria-label={`${row.name} 不适用原因`} placeholder="为什么本次不适用" maxLength={500} disabled={busy} value={decision.reason} onChange={e => change(base, { ...base, reason: e.target.value })} />}
                {decision?.local && <button className="pr-link" type="button" aria-label={`查看本次 ${row.name}`} onClick={() => showGraph("local", { ...base, local: decision.local, local_owner: objectMap[row.owner] })}>看本次图</button>}
              </div>
            </div>;
          })}
        </div></>}
        {preview && review && <section className="dr-differences" aria-label="对应差异">
          <div className="dr-tabs" role="group" aria-label="差异类型">{Object.entries(GROUPS).map(([key, label]) => <button type="button" key={key} aria-pressed={group === key} onClick={() => setGroup(key)}>{label} · {preview[key].length}</button>)}</div>
          <p className="pr-muted">已对应只表示你指定了关联；约束和无法检查的内容仍需分别查看。未列出差异不代表语义完全一致。</p>
          <ul className="dr-diff-list">{!preview[group].length && <li>这一类没有条目。</li>}{preview[group].map((row, i) => <li key={i}>
            <b>{KINDS[row.kind] || "定义"} · {row.reference_label || row.local_label}</b>
            {row.reference_label && row.local_label && <span> ↔ {row.local_label}</span>}
            {row.reason && <p>{row.reason}</p>}{row.details?.map(t => <p key={t}>{t}</p>)}
            {row.reference && <button type="button" className="pr-link" onClick={() => showGraph("reference", row)}>定位参考</button>}
            {row.local && <button type="button" className="pr-link" onClick={() => showGraph("local", row)}>定位本次</button>}
          </li>)}</ul>
        </section>}
        <div className="dr-actions"><span className="pr-muted">{mappings.length} 项人工判断{dirty ? " · 尚未保存" : ""}</span>
          {review && <button type="button" className="pr-link" disabled={busy} onClick={() => setReview(false)}>修改对应</button>}
          <button type="button" className="pr-link" disabled={busy || !dirty} onClick={() => restore(context)}>取消修改</button>
          {!review && <button type="button" className="pr-primary" disabled={busy} onClick={() => compare(false)}>预览差异</button>}
          {review && <button type="button" className="pr-primary" disabled={busy || !preview} onClick={() => compare(true)}>确认对应并保存</button>}
        </div>
      </>}
    </>}
    <dialog ref={dialog} className="dr-graph-dialog" aria-label="对应项关系图" onClose={() => setGraph(null)}>
      <header><h2>{graph === "reference" ? "参考定义 · 未在本次数据上核验" : "本次本体"}</h2><button type="button" className="pr-link" onClick={() => dialog.current.close()}>关闭图</button></header>
      {graph && <OntologyGraph key={`${graph}-${definition?.sha256}`} run={graph === "reference" ? definitionGraph : run} selected={selected} onSelect={setSelected} />}
    </dialog>
  </section>;
}
