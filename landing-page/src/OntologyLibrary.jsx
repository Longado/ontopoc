import { useEffect, useMemo, useRef, useState } from "react";
import { OntologyGraph } from "./OntologyGraph.jsx";
import { definitionRun, libraryEntries } from "./ontologyLibraryModel.js";
import "./OntologyLibrary.css";

async function readDefinition(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `本体读取失败（${response.status}）`);
  return body;
}

export function OntologyLibrary({ active }) {
  const [entries, setEntries] = useState(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [definition, setDefinition] = useState(null);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [catalogueError, setCatalogueError] = useState("");
  const [reload, setReload] = useState(0);
  const sequence = useRef(0);
  const page = useRef(null);
  const information = useRef(null);
  useEffect(() => {
    if (active && definition) page.current?.closest(".app-main")?.scrollTo({ top: 0 });
  }, [active, definition]);
  useEffect(() => {
    if (!active || entries) return;
    let cancelled = false;
    setCatalogueError("");
    readDefinition("/api/ontology/library").then((body) => { if (!cancelled) setEntries(body.entries); })
      .catch(() => { if (!cancelled) setCatalogueError("连不上本机本体库服务，确认它正在运行后重试。"); });
    return () => { cancelled = true; };
  }, [active, entries, reload]);
  const shown = libraryEntries(entries || [], query, category);
  const categories = [...new Set((entries || []).map((e) => e.category))];
  const run = useMemo(() => definition ? definitionRun(definition) : null, [definition]);

  async function open(url, options) {
    const turn = ++sequence.current;
    setBusy(true); setError("");
    try {
      const body = await readDefinition(url, options);
      if (turn === sequence.current) { setDefinition(body); setSelected(null); }
    } catch (e) {
      if (turn === sequence.current) setError(e.message === "Failed to fetch" ? "连不上本机本体库服务，请重试。" : e.message);
    } finally { if (turn === sequence.current) setBusy(false); }
  }
  async function importFile(file) {
    if (!file) return;
    if (!/\.(rdf|owl)$/i.test(file.name)) { setError("本体定义请用 .rdf 或 .owl 文件。"); return; }
    if (file.size > 2 * 1024 * 1024) { setError("本体文件太大，上限 2 MB。"); return; }
    try {
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
        reader.onerror = () => reject(new Error("文件读取失败。"));
        reader.readAsDataURL(file);
      });
      await open("/api/ontology/library/import", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, content_base64: encoded }) });
    } catch (e) { setError(e.message); }
  }
  function back() { sequence.current++; setDefinition(null); setSelected(null); setBusy(false); setError(""); }

  const importControl = <label className="ol-import pr-primary">导入 RDF / OWL
    <input type="file" accept=".rdf,.owl" aria-label="导入本体定义" disabled={busy} onChange={(e) => { importFile(e.target.files[0]); e.target.value = ""; }} />
  </label>;

  return <section ref={page} className={`pr-page ol-page${active && definition ? " is-definition" : ""}`} aria-labelledby="ol-title">
    <header className={definition ? "ol-detail-head" : "pr-head ol-head"}>
      {definition ? <>
        <div className="ol-detail-title">
          <div className="ol-detail-heading"><button className="pr-link" type="button" onClick={back}>← 本体库</button>
            <h1 id="ol-title" title={definition.entry?.title || definition.name}>{definition.entry?.title || definition.name}</h1></div>
          <p className="ol-count">{definition.entity_types.length} 个对象 · {definition.relationships.length} 条关系 · {definition.entity_types.reduce((n, e) => n + e.properties.length, 0)} 个属性</p>
          <small className="pr-muted">参考定义，不含实例数据，未在你的数据上核验。</small>
        </div>
        <div className="ol-detail-tools">
          <label className="ol-object">对象<select value={selected?.kind === "node" ? selected.key : ""} onChange={(e) => setSelected(e.target.value ? { kind: "node", key: e.target.value } : null)}>
            <option value="">在图上选择或查找</option>{definition.entity_types.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
          <button type="button" className={`ol-info-button${definition.warnings.length ? " has-warnings" : ""}`} onClick={() => information.current.showModal()}>
            说明与原文{definition.warnings.length > 0 && ` · ${definition.warnings.length} 项提示`}</button>
          {importControl}
        </div>
      </> : <>
        <div><p className="ol-eyebrow">领域参考</p><h1 id="ol-title">本体库</h1><p className="pr-muted">先看看业务通常怎样表达，再决定哪些适合你的数据。</p></div>
        {importControl}
      </>}
      {busy && <p className="ol-message" role="status">正在读取本体定义…</p>}
      {error && <p className="pr-error ol-message" role="alert">{error}</p>}
    </header>
    {definition ? <>
      <OntologyGraph key={definition.sha256} run={run} selected={selected} onSelect={setSelected} />
      <dialog ref={information} className="ol-info-dialog" aria-labelledby="ol-info-title">
        <header><h2 id="ol-info-title">说明与原文</h2><button type="button" className="pr-link" onClick={() => information.current.close()}>关闭</button></header>
        <div className="ol-info-body">
          <h3>{definition.name}</h3>
          <p>{definition.description || definition.metadata?.description}</p>
          {definition.entry && <p className="ol-source">作者：{definition.metadata.author} · 收录自 <a href={definition.entry.source_url} target="_blank" rel="noreferrer">Ontology Playground 原文</a> · MIT
            <small>收录版本：{definition.entry.commit.slice(0, 12)}</small></p>}
          {!definition.entry && <p className="pr-muted">来自本机文件：{definition.filename}</p>}
          <p className="pr-note">这里只浏览定义，没有在你的数据上核验。导入不调用模型；本次导入保留在当前页面，刷新后需重新选文件。</p>
          {definition.warnings.length > 0 && <details className="ol-warnings" open><summary>这份定义有 {definition.warnings.length} 项需要留意</summary>
            <ul>{definition.warnings.map((w, i) => <li key={i}>{w.message}{w.subject && <small>{w.subject}</small>}</li>)}</ul></details>}
        {(definition.unattached_properties.length > 0 || run.ontology.relations.length !== definition.relationships.length) && <details className="pr-card ol-unresolved"><summary>未能放到图上的定义</summary>
          {definition.unattached_properties.map((p) => <p key={p.id}>{p.name} · {p.id}</p>)}
          {definition.relationships.filter((r) => !run.ontology.relations.some((g) => g.key === r.id)).map((r) => <p key={r.id}>{r.name}：{r.from || "未声明起点"} → {r.to || "未声明终点"}</p>)}
        </details>}
        <details className="pr-card ol-raw"><summary>查看保留的 RDF/XML 原文</summary><pre>{definition.rdf_xml}</pre></details>
        </div>
      </dialog>
    </> : <>
      <p className="pr-note ol-boundary">这里只浏览对象、属性和关系定义，不含实例数据，也没有在你的数据上核验。导入不调用模型；本次导入保留在当前页面，刷新后需重新选文件。</p>
      <div className="ol-filters"><label>搜索<input type="search" value={query} placeholder="名称、作者或关键词" onChange={(e) => setQuery(e.target.value)} /></label>
        <label>领域<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">全部领域</option>{categories.map((c) => <option key={c}>{c}</option>)}</select></label></div>
      {catalogueError && <p className="pr-error" role="alert">{catalogueError} <button className="pr-link" onClick={() => setReload((n) => n + 1)}>重试</button></p>}
      {!entries && !catalogueError && <p role="status">正在读取本地本体库…</p>}
      {entries && <p className="pr-muted ol-results">显示 {shown.length} / {entries.length} 份本体</p>}
      {entries && !shown.length && <p>没有找到匹配的本体，试试其他关键词或领域。</p>}
      <div className="ol-grid">{shown.map((e) => <button key={e.id} type="button" className="pr-card ol-card" onClick={() => open(`/api/ontology/library/${encodeURIComponent(e.id)}`)}>
        <span className="ol-category">{e.category}</span><h2>{e.title}</h2><p className="ol-original">{e.name}</p>
        <p className="ol-card-description">{e.description}</p><p className="ol-count">{e.counts.entities} 个对象 · {e.counts.relationships} 条关系 · {e.counts.properties} 个属性</p>
        <small>{e.author}</small><b className="ol-open">查看定义与关系图 →</b>
      </button>)}</div>
    </>}
  </section>;
}
