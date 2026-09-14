import { useEffect, useRef, useState } from "react";
import {
  ACCEPT, CHECK_LABELS, DEMO_DOC_URL, DEMO_URL, ERROR_LABELS, isDocument, sourceLine, RESULT_KEY, STATUS_LABELS, answerLines, attemptSummary, checkSummary, questionSummary,
  referenceCounts, stabilityLines, typeLabel, typeSources, validateRun,
} from "./ontologyStudioModel.js";
import { OntologyGraph } from "./OntologyGraph.jsx";
import "./PublicRecallReview.css";
import "./OntologyStudio.css";

const TABS = [["upload", "上传"], ["ontology", "本体"], ["evaluation", "评测"]];
const START = "PYTHONPATH=src python -m ontology_poc_generator.ontology_server";

const readText = (url) => fetch(url, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(`读取失败（${r.status}）`); return r.json(); });
const saveLocal = (run) => { try { localStorage.setItem(RESULT_KEY, JSON.stringify(run)); } catch { /* storage unavailable: the result is only kept in this tab */ } };
const loadLocal = () => { try { return validateRun(JSON.parse(localStorage.getItem(RESULT_KEY))); } catch { return null; } };

function toBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.readAsDataURL(file);
  });
}

function UploadTab({ health, busy, elapsed, error, onBuild, onDemo, onDocDemo }) {
  const [file, setFile] = useState(null);
  const [purpose, setPurpose] = useState("");
  const offline = health === "offline";
  return <>
    <section className="pr-card">
      <h2>上传一份业务数据表或文档</h2>
      <p className="pr-muted">数据表：Excel（.xlsx，每个 sheet 当作一张表）或 CSV。模型只看表头和每列少量示例值，提出对象、身份字段和关系；代码拿全部行核验，出错退回重做，最多三次。</p>
      <p className="pr-muted">文档：Markdown、文本、Word（.docx）或 PDF。模型按段落提出概念和关系，每一项都要引用原文；代码核对引用确实在原文里，找不到的剔除并列出。文件和结果只留在本机。</p>
      <div className="os-upload">
        <label htmlFor="os-file">选择文件<input id="os-file" type="file" accept={ACCEPT} disabled={busy} onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
        <label htmlFor="os-purpose">这份本体要帮谁回答什么问题（可不填）
          <textarea id="os-purpose" rows={2} maxLength={300} disabled={busy} value={purpose} placeholder="例如：让售后负责人看清哪些客户、产品的售后问题最多" onChange={(e) => setPurpose(e.target.value)} />
        </label>
        <button className="pr-primary" disabled={!file || busy || offline || health === "no-key"} onClick={() => onBuild(file, purpose)}>{busy ? `生成中… ${elapsed} 秒` : "生成本体并评测"}</button>
      </div>
      {busy && <p className="pr-muted" role="status">模型提出本体、代码核验、必要时退回重做，通常要 1–3 分钟。</p>}
      {error && <p role="alert" className="pr-error">{error}</p>}
      {offline && <div className="pr-note"><p>本机的建模服务没有启动。在仓库根目录运行（需要本机 DeepSeek 凭据）：</p><code className="os-cmd">{START}</code></div>}
      {health === "no-key" && <p className="pr-note">建模服务已启动，但没有模型凭据：设置 DEEPSEEK_API_KEY 后重启服务。</p>}
    </section>
    <section className="pr-card">
      <h2>先看一个示例</h2>
      <p className="pr-muted">一家合成的"示例制造公司"：客户、产品、订单、售后工单四张表（Excel），数据全部是编造的，里面故意放了两个数据问题。结果是用 DeepSeek 实际跑出来的。</p>
      <div className="os-demos"><button className="pr-link" onClick={onDemo} disabled={busy}>打开示例结果（数据表）</button>
        <button className="pr-link" onClick={onDocDemo} disabled={busy}>打开示例结果（售后服务流程文档）</button></div>
    </section>
  </>;
}

function QuestionItem({ item }) {
  const lines = answerLines(item);
  return <li className="os-question">
    <div className="os-question-head"><span className={`os-pill os-${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span><b>{item.question}</b></div>
    {lines.length > 0 && <ul className="os-answer">{lines.map((l) => <li key={l}>{l}</li>)}</ul>}
    {item.path && <p className="pr-muted">怎么查的：{item.path}</p>}
    {item.status !== "answered" && item.reason && <p className="pr-muted">原因：{item.reason}</p>}
  </li>;
}

function QuestionsSection({ run, canAsk, busy, error, onAsk, askRef }) {
  const [text, setText] = useState("");
  const round = run.evaluation.questions;
  const asked = run.evaluation.asked || [];
  return <section className="pr-card">
    <div className="pr-card-head"><h2>评测二：能不能回答业务问题</h2>{round && <span className="pr-muted">{questionSummary(round)}</span>}</div>
    <p className="pr-muted">模型只负责把问题写成查询（一次调用）；答案由代码在上传的数据上算出来。答不了时写明是本体缺了哪一块，还是数据里没有。</p>
    {!canAsk && <p className="pr-note">要自己出题或提问，需要上传文件并开着本机建模服务；示例结果里已附一轮问答。</p>}
    <div className="os-ask">
      <button className="pr-primary" disabled={!canAsk || busy} onClick={() => onAsk(null)}>{busy ? "出题回答中…" : round ? "重新出一组问题" : "出一组业务问题并用数据回答"}</button>
      <label htmlFor="os-question">或者问一个问题
        <span className="os-ask-row"><input id="os-question" ref={askRef} value={text} maxLength={300} disabled={!canAsk || busy} placeholder="例如：哪些客户的售后工单最多？" onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) onAsk(text.trim()); }} />
        <button className="pr-link" disabled={!canAsk || busy || !text.trim()} onClick={() => onAsk(text.trim())}>问</button></span>
      </label>
    </div>
    {error && <p role="alert" className="pr-error">{error}</p>}
    {asked.length > 0 && <><h3 className="os-sub">你问的</h3><ul className="os-questions">{[...asked].reverse().flatMap((r, ri) => r.error ? [<li key={`e${ri}`} className="pr-error">{r.error}</li>] : r.items.map((item, i) => <QuestionItem key={`${ri}-${i}`} item={item} />))}</ul></>}
    {round && <><h3 className="os-sub">模型出的题（{round.model}，{round.prompt_version}）</h3>
      {round.error ? <p className="pr-error">{round.error}</p> : <ul className="os-questions">{round.items.map((item, i) => <QuestionItem key={i} item={item} />)}</ul>}</>}
  </section>;
}

function DiffList({ title, items }) {
  return items.length ? <div className="os-diff"><h3 className="os-sub">{title}（{items.length}）</h3><ul className="os-list">{items.map((x) => <li key={Array.isArray(x) ? x.join("/") : x}>{Array.isArray(x) ? (x[0] === x[1] ? x[0] : `${x[0]} ↔ ${x[1]}`) : x}</li>)}</ul></div> : null;
}

function ReferenceSection({ run, canCompare, onCompare, busy, error }) {
  const ref = run.evaluation.reference;
  const fileRef = useRef(null);
  return <section className="pr-card">
    <div className="pr-card-head"><h2>评测三：和标准答案比</h2>{ref && <span className="pr-muted">{referenceCounts(ref.diff)}</span>}</div>
    <p className="pr-muted">上传一份人写的参考本体（JSON：对象的 label，最好带来自哪张表、按哪个字段识别；关系写两端的对象）。代码按"读同一张表、用同样的身份字段"来对应对象，名字不同也能对上；关系两端都对上才算命中。</p>
    <div className="os-upload">
      <label htmlFor="os-reference">选择参考本体（.json）<input id="os-reference" ref={fileRef} type="file" accept=".json,application/json" disabled={!canCompare || busy}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onCompare(f); e.target.value = ""; }} /></label>
      <p className="pr-muted">示例公司的参考本体：<a href="/data/demo-reference-ontology.json" target="_blank" rel="noreferrer">demo-reference-ontology.json</a></p>
    </div>
    {!canCompare && <p className="pr-note">要和自己的参考本体比，需要上传文件并开着本机建模服务；示例结果里已附一次比对。</p>}
    {error && <p role="alert" className="pr-error">{error}</p>}
    {ref && <>
      <p className="pr-muted">参考本体：{ref.name}</p>
      <DiffList title="参考里有、本体里没有的对象" items={ref.diff.types.only_reference} />
      <DiffList title="本体里多出来的对象" items={ref.diff.types.only_ours} />
      <DiffList title="对上的对象" items={ref.diff.types.matched} />
      <DiffList title="参考里有、本体里没有的关系" items={ref.diff.relations.only_reference} />
      <DiffList title="本体里多出来的关系" items={ref.diff.relations.only_ours} />
    </>}
  </section>;
}

function OntologyTab({ run, onAskOntology }) {
  const { ontology } = run;
  const doc = isDocument(run);
  const attempts = attemptSummary(ontology);
  const [view, setView] = useState("graph");
  return <>
    <section className="pr-card">
      <div className="pr-card-head"><h2>{run.file.name}</h2><span className={`pr-status ${attempts.passed ? "pr-status-ok" : "pr-status-wait"}`}>{doc ? (attempts.passed ? "每一项都有原文引用" : "没有提取出可核实的概念") : attempts.passed ? "本体结构已通过核验" : "本体结构未通过核验"}</span></div>
      <p className="pr-muted">{sourceLine(run)}</p>
      {run.sources.some((s) => s.skipped_rows) && <p className="pr-muted">表头上方的标题行已跳过：{run.sources.filter((s) => s.skipped_rows).map((s) => `${s.name}（${s.skipped_rows.join("；")}）`).join("、")}</p>}
      <p>建模目的：{run.purpose}<span className="pr-muted">（这句话作为建模目的交给了模型）</span></p>
      {!doc && <p className="pr-muted">"结构已通过核验"只说明本体里的字段、身份和关系都能在数据里对上；数据本身干不干净看"评测"。</p>}
      {doc ? <p>文档分 {ontology.chunks_processed} 段交给模型{ontology.chunks_total > ontology.chunks_processed ? `（共 ${ontology.chunks_total} 段，文档太长，后面的没有处理）` : ""}；被剔除 {ontology.rejected.length} 项（引用在原文里找不到，或两端不是已核实的概念）。模型 {ontology.model}，提示词 {ontology.prompt_version}。</p>
      : <p>模型提交 {attempts.attempts} 次{attempts.rejected.length ? `，前面被代码退回的原因：${attempts.rejected.map(([code, n]) => `${ERROR_LABELS[code] || code} ${n} 处`).join("、")}` : "，第一次就通过"}。模型 {ontology.model}，提示词 {ontology.prompt_version}。</p>}
      {doc && ontology.rejected.length > 0 && <details><summary>被剔除的项（{ontology.rejected.length}）</summary><ul>{ontology.rejected.map((r, i) => <li key={i}>{r.item}：{r.reason}</li>)}</ul></details>}
    </section>
    {run.previous && <section className="pr-card">
      <h2>和上一次运行比</h2>
      {stabilityLines(run.previous.diff).length
        ? <><p className="pr-muted">同一份文件上一次运行（{run.previous.started_at.slice(0, 16).replace("T", " ")}）得到的本体和这次不一样。模型每次搭的本体会有出入，下面是差别；拿不准时用"评测三"和参考本体比。</p>
          <ul className="os-list">{stabilityLines(run.previous.diff).map((l) => <li key={l}>{l}</li>)}</ul></>
        : <p className="pr-muted">同一份文件上一次运行（{run.previous.started_at.slice(0, 16).replace("T", " ")}）得到的对象和关系与这次完全一致。</p>}
    </section>}
    <section className="pr-card">
      <div className="pr-card-head"><h2>本体</h2>
        <div className="og-toggle" role="group" aria-label="显示方式">{[["graph", "关系图"], ["list", "列表"]].map(([key, text]) => <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}>{text}</button>)}</div></div>
      {view === "graph" && <OntologyGraph run={run} onAsk={doc ? null : onAskOntology} />}
    </section>
    {view === "list" && <><section className="pr-card">
      <h2>对象（{ontology.object_types.length}）</h2>
      <div className="pr-types">{ontology.object_types.map((t) => <article key={t.key} className="pr-type">
        <span className="pr-tag">{t.key}</span>
        <h3>{t.label || t.key}</h3>
        <p>来自：{typeSources(t)}</p>
        {t.attributes.length > 0 && <p>属性：{t.attributes.map((a) => a.path).join("、")}</p>}
        {t.time_field && <p>时间：{t.time_field.path}</p>}
        {t.rationale && <small>{t.rationale}</small>}
      </article>)}</div>
    </section>
    <section className="pr-card">
      <h2>关系（{ontology.relations.length}）</h2>
      {ontology.relations.length ? <ul className="pr-rows">{ontology.relations.map((r) => <li key={r.key}>
        <b>{typeLabel(ontology, r.from)} {r.label || "→"} {typeLabel(ontology, r.to)}</b><span>{r.meaning}</span><code>{r.source}</code></li>)}</ul>
        : <p className="pr-muted">没有关系。</p>}
    </section></>}
    <section className="pr-card">
      <h2>模型指出的数据缺口（{ontology.data_gaps.length}）</h2>
      {ontology.data_gaps.length ? <ul className="os-list">{ontology.data_gaps.map((g) => <li key={g}>{g}</li>)}</ul> : <p className="pr-muted">没有。</p>}
      {ontology.ignored_fields.length > 0 && <details><summary>标为不用的字段（{ontology.ignored_fields.length}）</summary><ul>{ontology.ignored_fields.map((f) => <li key={`${f.source}.${f.path}`}>{f.source}.{f.path}：{f.reason}</li>)}</ul></details>}
    </section>
  </>;
}

function DocumentFit({ run, questions }) {
  const fit = run.evaluation.document_fit;
  if (!fit) return <section className="pr-card"><p className="pr-error">没有提取出可核实的概念，无法评测。先看"本体"里被剔除的原因。</p></section>;
  const summary = checkSummary(fit);
  return <>
    <section className="pr-card">
      <div className="pr-card-head"><h2>评测一：文档检查（每一项都能回到原文吗）</h2><span className="pr-muted">通过 {summary.passed} / {summary.total} 项</span></div>
      <p className="pr-muted">由代码逐项核对模型给的引用是否真在原文里，不经过模型。模型共提出 {fit.proposed} 项，保留 {fit.kept} 项，剔除 {fit.rejected} 项。{fit.cut ? "文档太长，只处理了前面的部分。" : ""}</p>
      <ul className="os-checks">{fit.checks.map((c) => <li key={c.key}><span className={`os-pill ${c.passed ? "os-pass" : "os-fail"}`}>{c.passed ? "通过" : "不通过"}</span>{CHECK_LABELS[c.key] || c.key}</li>)}</ul>
      {fit.isolated.length > 0 && <p className="pr-muted">没有任何关系的概念：{fit.isolated.join("、")}</p>}
    </section>
    <section className="pr-card"><h2>评测二：能不能回答业务问题</h2><p className="pr-muted">文档没有数据行可以查询，评测二只对数据表可用。把同一业务的数据表也上传，就能用数据回答问题。</p></section>
    <ReferenceSection run={run} canCompare={questions.canAsk} onCompare={questions.onCompare} busy={questions.comparing} error={questions.compareError} />
  </>;
}

function EvaluationTab({ run, questions }) {
  if (isDocument(run)) return <DocumentFit run={run} questions={questions} />;
  const fit = run.evaluation.data_fit;
  const { ontology } = run;
  if (!fit) return <section className="pr-card"><p className="pr-error">本体没有通过核验，无法评测。先看"本体"里被退回的原因。</p></section>;
  const summary = checkSummary(fit);
  return <>
    <section className="pr-card">
      <div className="pr-card-head"><h2>评测一：数据检查（本体和数据对不对得上）</h2><span className="pr-muted">通过 {summary.passed} / {summary.total} 项</span></div>
      <p className="pr-muted">全部由代码拿上传的每一行计算，不经过模型。</p>
      <ul className="os-checks">{fit.checks.map((c) => <li key={c.key}><span className={`os-pill ${c.passed ? "os-pass" : "os-fail"}`}>{c.passed ? "通过" : "不通过"}</span>{CHECK_LABELS[c.key] || c.key}</li>)}</ul>
    </section>
    {fit.identity_conflicts.length > 0 && <section className="pr-card">
      <h2>同一对象信息打架（{fit.identity_conflicts.length}）</h2>
      <div className="pr-table-wrap"><table className="pr-table"><thead><tr><th>对象</th><th>表</th><th>身份</th><th>字段</th><th>不同的值</th></tr></thead>
        <tbody>{fit.identity_conflicts.map((c, i) => <tr key={i}><td>{typeLabel(ontology, c.type)}</td><td>{c.source}</td><td>{c.identity}</td><td>{c.field}</td><td>{c.values.join(" / ")}</td></tr>)}</tbody></table></div>
    </section>}
    {fit.identity_spellings?.length > 0 && <section className="pr-card">
      <h2>同一个编号有几种写法（{fit.identity_spellings.length}）</h2>
      <p className="pr-muted">这些写法被当成同一个对象合并了，但源数据里写法不统一，建议在源系统里统一。</p>
      <ul className="pr-rows">{fit.identity_spellings.map((s, i) => <li key={i}><b>{typeLabel(ontology, s.type)} {s.identity}</b><span>写法：{s.variants.map((v) => `“${v}”`).join("、")}</span></li>)}</ul>
    </section>}
    {fit.suspected_duplicates?.length > 0 && <section className="pr-card">
      <h2>疑似重复（请人工确认）</h2>
      <p className="pr-muted">去掉开头的 0 以后相同的编号，现在被当成不同的对象；如果它们其实是同一个，需要在源数据里统一。</p>
      <ul className="pr-rows">{fit.suspected_duplicates.map((d, i) => <li key={i}><b>{typeLabel(ontology, d.type)}</b><span>{d.identities.join(" 和 ")}</span></li>)}</ul>
    </section>}
    {fit.missing_across_sources.length > 0 && <section className="pr-card">
      <h2>引用了、但在它所属的表里找不到</h2>
      <ul className="pr-rows">{fit.missing_across_sources.map((m) => <li key={`${m.type}/${m.source}`}><b>{typeLabel(ontology, m.type)}：{m.count} 个不在"{m.source}"表里</b><span>例如 {m.examples.join("、")}</span></li>)}</ul>
    </section>}
    <section className="pr-card">
      <h2>关系连通</h2>
      <div className="pr-table-wrap"><table className="pr-table"><thead><tr><th>关系</th><th>所在表</th><th>连上的行 / 总行</th></tr></thead>
        <tbody>{fit.relations.map((r) => { const rel = ontology.relations.find((x) => x.key === r.key);
          return <tr key={r.key}><td>{rel ? `${typeLabel(ontology, rel.from)} → ${typeLabel(ontology, rel.to)}` : r.key}</td><td>{r.source}</td><td>{r.linked_rows} / {r.rows}</td></tr>; })}</tbody></table></div>
      <p className="pr-muted">孤立对象（一条关系都没有）：{fit.orphans.map((o) => `${typeLabel(ontology, o.type)} ${o.count}`).join("、") || "无"}。表的连通：{fit.source_groups.map((g) => g.join(" + ")).join(" ｜ ")}。</p>
    </section>
    <section className="pr-card">
      <h2>字段去处</h2>
      <div className="pr-table-wrap"><table className="pr-table"><thead><tr><th>表</th><th>列数</th><th>用上</th><th>写明不用</th><th>没有去处</th></tr></thead>
        <tbody>{Object.entries(fit.fields).map(([name, f]) => <tr key={name}><td>{name}</td><td>{f.total}</td><td>{f.used}</td><td>{f.ignored}</td><td>{f.unaccounted}</td></tr>)}</tbody></table></div>
    </section>
    <QuestionsSection run={run} {...questions} />
    <ReferenceSection run={run} canCompare={questions.canAsk} onCompare={questions.onCompare} busy={questions.comparing} error={questions.compareError} />
  </>;
}

export function OntologyStudio() {
  const [tab, setTab] = useState("upload");
  const [run, setRun] = useState(() => loadLocal());
  const [health, setHealth] = useState("checking");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState("");
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState("");
  const timer = useRef(null);
  const askRef = useRef(null);

  useEffect(() => {
    fetch("/api/ontology/health", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((h) => setHealth(h.model_ready ? "ready" : "no-key")).catch(() => setHealth("offline"));
  }, []);
  useEffect(() => () => clearInterval(timer.current), []);

  function show(result) { const valid = validateRun(result); setRun(valid); saveLocal(valid); setTab("ontology"); }
  async function build(file, purpose) {
    setBusy(true); setError(""); setElapsed(0);
    const started = Date.now();
    timer.current = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    try {
      const body = JSON.stringify({ filename: file.name, content_base64: await toBase64(file), purpose });
      const response = await fetch("/api/ontology/build", { method: "POST", headers: { "Content-Type": "application/json" }, body });
      const data = await response.json().catch(() => ({ error: `服务返回 ${response.status}` }));
      if (!response.ok) throw new Error(data.error || `服务返回 ${response.status}`);
      show(data);
    } catch (e) { setError(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message); }
    finally { clearInterval(timer.current); setBusy(false); }
  }
  async function ask(question) {
    setAsking(true); setAskError("");
    try {
      const response = await fetch("/api/ontology/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ saved_as: run.saved_as, ...(question ? { question } : {}) }) });
      const data = await response.json().catch(() => ({ error: `服务返回 ${response.status}` }));
      if (!response.ok) throw new Error(data.error || `服务返回 ${response.status}`);
      const valid = validateRun(data); setRun(valid); saveLocal(valid);
    } catch (e) { setAskError(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message); }
    finally { setAsking(false); }
  }
  async function compare(file) {
    setComparing(true); setCompareError("");
    try {
      let reference;
      try { reference = JSON.parse(await file.text()); } catch { throw new Error(`${file.name} 不是有效的 JSON`); }
      const response = await fetch("/api/ontology/compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ saved_as: run.saved_as, reference, reference_name: file.name }) });
      const data = await response.json().catch(() => ({ error: `服务返回 ${response.status}` }));
      if (!response.ok) throw new Error(data.error || `服务返回 ${response.status}`);
      const valid = validateRun(data); setRun(valid); saveLocal(valid);
    } catch (e) { setCompareError(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message); }
    finally { setComparing(false); }
  }
  function askOntology() { setTab("evaluation"); requestAnimationFrame(() => askRef.current?.scrollIntoView({ block: "center" })); setTimeout(() => askRef.current?.focus(), 50); }
  function demo(url = DEMO_URL) { setError(""); readText(url).then(show).catch((e) => setError(`示例读取失败：${e.message}`)); }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(run, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `${run.file.name.replace(/\.[^.]+$/, "")}-ontology.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const fitSummary = run && checkSummary(run.evaluation.data_fit || run.evaluation.document_fit);
  return <section className="pr-page" aria-labelledby="os-title">
    <header className="pr-head">
      <div className="pr-head-line">
        <h1 id="os-title">上传建本体</h1>
        {run && <span className="pr-meta">当前：{run.file.name} · {run.ontology.object_types.length} 个对象 · {run.ontology.relations.length} 条关系{fitSummary ? ` · ${isDocument(run) ? "文档" : "数据"}检查通过 ${fitSummary.passed}/${fitSummary.total}` : ""}</span>}
        {run && <button className="pr-link" onClick={download}>下载结果</button>}
      </div>
      <nav className="pr-tabs" role="tablist" aria-label="步骤">{TABS.map(([key, label]) => <button key={key} type="button" role="tab" id={`os-tab-${key}`}
        aria-selected={tab === key} aria-controls="os-panel" disabled={key !== "upload" && !run} onClick={() => setTab(key)}>{label}</button>)}</nav>
    </header>
    <div id="os-panel" role="tabpanel" aria-labelledby={`os-tab-${tab}`} className="pr-panel os-panel">
      {tab === "upload" && <UploadTab health={health} busy={busy} elapsed={elapsed} error={error} onBuild={build} onDemo={() => demo(DEMO_URL)} onDocDemo={() => demo(DEMO_DOC_URL)} />}
      {tab === "ontology" && run && <OntologyTab run={run} onAskOntology={askOntology} />}
      {tab === "evaluation" && run && <EvaluationTab run={run} questions={{ canAsk: Boolean(run.saved_as) && health === "ready", busy: asking, error: askError, onAsk: ask, askRef, onCompare: compare, comparing, compareError }} />}
    </div>
  </section>;
}
