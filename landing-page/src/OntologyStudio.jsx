import { useEffect, useRef, useState } from "react";
import {
  ACCEPT, CHECK_LABELS, DEMO_DOC_URL, DEMO_URL, ERROR_LABELS, isDocument, sourceLine, RESULT_KEY, STATUS_LABELS, answerLines, attemptSummary, checkSummary, questionSummary,
  progressSteps, referenceCounts, serviceError, stabilityLines, typeLabel, typeSources, validateRun,
} from "./ontologyStudioModel.js";
import { overviewTiles, pathOf } from "./ontologyGraphModel.js";
import { OntologyGraph } from "./OntologyGraph.jsx";
import "./PublicRecallReview.css";
import "./OntologyStudio.css";

const TABS = [["upload", "上传"], ["ontology", "看本体"], ["evaluation", "看评测"]];
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

const EXAMPLE_QUESTIONS = ["哪些客户的售后问题最多？", "哪些产品最常出问题？", "订单主要来自哪些行业？"];
const TABLE_EXT = /\.(csv|xlsx)$/i;
const sizeText = (n) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

function Mark() {
  return <svg className="os-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="0" y="0" width="10" height="10" fill="#4948df" /><rect x="22" y="0" width="10" height="10" fill="#afacfd" />
    <rect x="0" y="22" width="10" height="10" fill="#f3b944" /><rect x="22" y="22" width="10" height="10" fill="#4746dc" />
    <rect x="10" y="3" width="12" height="4" fill="#7474f9" /><rect x="3" y="10" width="4" height="12" fill="#7474f9" /><rect x="25" y="10" width="4" height="12" fill="#4748e2" /><rect x="10" y="25" width="12" height="4" fill="#7474f9" /></svg>;
}

function Progress({ events, kind, elapsed }) {
  const steps = progressSteps(events, kind);
  return <div className="os-progress" role="status" aria-live="polite">
    <ol className="os-steps">{steps.map((st) => <li key={st.key} className={`is-${st.status}`}>
      <span className="os-step-dot" aria-hidden="true">{st.status === "done" ? "✓" : ""}</span>
      <span><b>{st.label}</b>{st.detail && <small>{st.detail}</small>}</span>
      <em className="sr-only">{st.status === "done" ? "完成" : st.status === "active" ? "进行中" : "未开始"}</em>
    </li>)}</ol>
    <p className="pr-muted">已用 {elapsed} 秒。每一步都来自本机服务的实时回报；模型出错时代码会退回重做，最多三次。</p>
  </div>;
}

function UploadTab({ health, busy, events, elapsed, error, onBuild, onDemo, onDocDemo }) {
  const [file, setFile] = useState(null);
  const [purpose, setPurpose] = useState("");
  const [over, setOver] = useState(false);
  const inputRef = useRef(null);
  const offline = health === "offline";
  const kind = file && (TABLE_EXT.test(file.name) ? "table" : "document");
  const blocked = offline ? "本机建模服务没有启动" : health === "no-key" ? "建模服务缺少模型凭据" : !file ? "先选择一个文件" : "";
  function pick(f) { if (f) setFile(f); }
  return <div className="os-upload-grid">
    <section className="pr-card os-main-card">
      <h2>上传一份业务文件</h2>
      {busy ? <Progress events={events} kind={kind} elapsed={elapsed} /> : <>
        {file ? <div className="os-file-card">
          <Mark />
          <div><b>{file.name}</b><small>{kind === "table" ? "数据表" : "文档"} · {sizeText(file.size)}</small></div>
          <button type="button" className="pr-link" onClick={() => { setFile(null); if (inputRef.current) inputRef.current.value = ""; }}>换一个文件</button>
        </div> : <label htmlFor="os-file" className={`os-drop${over ? " is-over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]); }}>
          <Mark />
          <b>把文件拖到这里，或点击选择</b>
          <span className="os-chips"><span>数据表 .xlsx .csv</span><span>文档 .md .txt .docx .pdf</span></span>
          <small>不超过 10 MB · 文件和结果只留在本机</small>
        </label>}
        <input id="os-file" ref={inputRef} className="sr-only" type="file" accept={ACCEPT} onChange={(e) => pick(e.target.files?.[0])} />
        <label htmlFor="os-purpose" className="os-purpose">这份本体要帮你回答什么问题？<span>（可选，会交给模型作为建模目的，也会作为第一道业务问答题）</span>
          <textarea id="os-purpose" rows={2} maxLength={300} value={purpose} placeholder="例如：哪些客户、产品的售后问题最多？" onChange={(e) => setPurpose(e.target.value)} />
        </label>
        <div className="os-chips os-suggest" role="group" aria-label="示例问题">{EXAMPLE_QUESTIONS.map((q) => <button key={q} type="button" onClick={() => setPurpose(q)}>{q}</button>)}</div>
        <div className="os-go">
          <button className="pr-primary" disabled={Boolean(blocked)} onClick={() => onBuild(file, purpose)}>生成本体并评测</button>
          {blocked && <span className="pr-muted">{blocked}</span>}
        </div>
        <details className="os-how"><summary>它会怎么做</summary>
          <p>数据表：模型只看表头和每列少量示例值，提出对象、识别字段和关系；代码拿全部行核验，出错退回重做，最多三次。</p>
          <p>文档：模型按段落提出概念和关系，每一项都要引用原文；代码核对引用确实在原文里，找不到的剔除并列出。</p>
        </details>
      </>}
      {error && <p role="alert" className="pr-error">{error}</p>}
      {offline && <div className="pr-note"><p>本机的建模服务没有启动。在仓库根目录运行（需要本机 DeepSeek 凭据）：</p><code className="os-cmd">{START}</code></div>}
    </section>
    <aside className="pr-card os-side-card">
      <h2>没有文件？先试示例</h2>
      <p className="pr-muted">一家合成的"示例制造公司"，数据全部是编造的，里面故意放了几个数据问题。结果是用 DeepSeek 实际跑出来的。</p>
      <div className="os-demo-buttons">
        <button type="button" className="os-demo" onClick={onDemo} disabled={busy}><b>示例数据表</b><small>客户、产品、订单、售后工单四张表</small></button>
        <button type="button" className="os-demo" onClick={onDocDemo} disabled={busy}><b>示例文档</b><small>售后服务流程说明</small></button>
      </div>
      <p className="pr-muted os-downloads">下载示例文件自己上传：<a href="/samples/demo_company.xlsx" download>示例数据表</a> · <a href="/samples/after_sales_process.md" download>示例文档</a> · <a href="/samples/demo_reference_ontology.json" download>参考本体</a></p>
    </aside>
  </div>;
}

function ShowOnGraph({ type, onShow }) {
  return <button type="button" className="os-graph-link" onClick={() => onShow(type)}>在图上看</button>;
}

function QuestionItem({ item, onPath }) {
  const a = item.answer;
  const max = a?.groups?.length ? Math.max(...a.groups.map(([, n]) => n)) : 0;
  const extra = answerLines(item).slice(a?.groups?.length || 0);   // group lines come first; the bars show those
  return <li className="os-question">
    <div className="os-question-head"><span className={`os-pill os-${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span><b>{item.question}</b></div>
    {a?.groups?.length > 0 && <ul className="os-bars">{a.groups.map(([value, n]) => <li key={value}><span>{value}</span><i style={{ width: `${Math.max(4, (n / max) * 100)}%` }} /><b>{n}</b></li>)}</ul>}
    {extra.length > 0 && <ul className="os-answer">{extra.map((l) => <li key={l}>{l}</li>)}</ul>}
    {item.path && <p className="pr-muted">怎么查的：{item.path}{item.query && onPath && <> <button type="button" className="os-graph-link" onClick={() => onPath(item.query, item.path)}>在图上看路径</button></>}</p>}
    {item.status !== "answered" && item.reason && <p className="pr-muted">原因：{item.reason}</p>}
  </li>;
}

function QuestionsSection({ run, canAsk, busy, error, onAsk, askRef, onPath, onUpload }) {
  const example = !run.saved_as;
  const [text, setText] = useState("");
  const round = run.evaluation.questions;
  const asked = run.evaluation.asked || [];
  return <section className="pr-card">
    <div className="pr-card-head"><h2>业务问答：能用数据回答问题吗</h2>{round && <span className="pr-muted">{questionSummary(round)}</span>}</div>
    <p className="pr-muted">模型只负责把问题写成查询（一次调用）；答案由代码在上传的数据上算出来。答不了时写明是本体缺了哪一块、数据里没有，还是查询写法表达不了。</p>
    {!canAsk && <CannotAsk what="自己提问、重新出题" example={example} onUpload={onUpload} />}
    {canAsk && <div className="os-ask">
      <button className="pr-primary" disabled={!canAsk || busy} onClick={() => onAsk(null)}>{busy ? "出题回答中…" : round ? "重新出一组问题" : "出一组业务问题并用数据回答"}</button>
      <label htmlFor="os-question">或者问一个问题
        <span className="os-ask-row"><input id="os-question" ref={askRef} value={text} maxLength={300} disabled={!canAsk || busy} placeholder="例如：哪些客户的售后工单最多？" onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) onAsk(text.trim()); }} />
        <button className="pr-link" disabled={!canAsk || busy || !text.trim()} onClick={() => onAsk(text.trim())}>问</button></span>
      </label>
    </div>}
    {error && <p role="alert" className="pr-error">{error}</p>}
    {asked.length > 0 && <><h3 className="os-sub">你问的</h3><ul className="os-questions">{[...asked].reverse().flatMap((r, ri) => r.error ? [<li key={`e${ri}`} className="pr-error">{r.error}</li>] : r.items.map((item, i) => <QuestionItem key={`${ri}-${i}`} item={item} onPath={onPath} />))}</ul></>}
    {round && <><h3 className="os-sub">模型出的题</h3>
      {round.error ? <p className="pr-error">{round.error}</p> : <ul className="os-questions">{round.items.map((item, i) => <QuestionItem key={i} item={item} onPath={onPath} />)}</ul>}
      <p className="pr-muted os-tech">出题模型 {round.model}，提示词 {round.prompt_version}</p></>}
  </section>;
}

function CannotAsk({ what, example, onUpload }) {
  return <div className="pr-note os-cannot">
    <span>{example ? `这是示例结果，只能看，不能${what}。上传自己的文件后就可以。` : `本机建模服务没有连上，暂时不能${what}。启动建模服务后刷新页面。`}</span>
    {example && onUpload && <button type="button" className="pr-link" onClick={onUpload}>上传自己的文件</button>}
  </div>;
}

function DiffList({ title, items }) {
  return items.length ? <div className="os-diff"><h3 className="os-sub">{title}（{items.length}）</h3><ul className="os-list">{items.map((x) => <li key={Array.isArray(x) ? x.join("/") : x}>{Array.isArray(x) ? (x[0] === x[1] ? x[0] : `${x[0]} ↔ ${x[1]}`) : x}</li>)}</ul></div> : null;
}

function ReferenceSection({ run, canCompare, onCompare, busy, error, onUpload }) {
  const ref = run.evaluation.reference;
  return <section className="pr-card">
    <div className="pr-card-head"><h2>对照标准答案</h2>{ref && <span className="pr-muted">{referenceCounts(ref.diff)}</span>}</div>
    <p className="pr-muted">上传一份人写的参考本体（JSON：对象的 label，最好带来自哪张表、按哪个字段识别；关系写两端的对象）。代码按"读同一张表、用同样的识别字段"来对应对象，名字不同也能对上；关系两端都对上才算命中。</p>
    {canCompare && <div className="os-upload">
      <label htmlFor="os-reference">选择参考本体（.json）<input id="os-reference" type="file" accept=".json,application/json" disabled={!canCompare || busy}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onCompare(f); e.target.value = ""; }} /></label>
      <p className="pr-muted">示例公司的参考本体：<a href="/samples/demo_reference_ontology.json" download>下载 demo_reference_ontology.json</a></p>
    </div>}
    {!canCompare && <CannotAsk what="和自己的参考本体比" example={!run.saved_as} onUpload={onUpload} />}
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

function OntologyTab({ run, view, setView, graphProps }) {
  const { ontology } = run;
  const doc = isDocument(run);
  const attempts = attemptSummary(ontology);
  const retries = attempts.attempts - 1;
  return <>
    <section className="pr-card os-summary-card">
      <div className="pr-card-head"><h2>{run.file.name}</h2><span className={`pr-status ${attempts.passed ? "pr-status-ok" : "pr-status-wait"}`}>{doc ? (attempts.passed ? "每一项都有原文引用" : "没有提取出可核实的概念") : attempts.passed ? "本体结构已通过核验" : "本体结构未通过核验"}</span></div>
      <p className="pr-muted">{sourceLine(run)}{doc ? ` · 被剔除 ${ontology.rejected.length} 项` : attempts.passed ? ` · ${retries ? `代码退回 ${retries} 次后通过` : "第一次提交就通过"}` : ""}</p>
      {run.sources.some((s) => s.skipped_rows) && <p className="pr-muted">表头上方的标题行已跳过：{run.sources.filter((s) => s.skipped_rows).map((s) => `${s.name}（${s.skipped_rows.join("；")}）`).join("、")}</p>}
      <p>建模目的：{run.purpose}</p>
      <details className="os-how"><summary>技术信息</summary>
        {!doc && <p>"结构已通过核验"只说明本体里的字段、识别字段和关系都能在数据里对上；数据本身干不干净看"数据体检"。</p>}
        {doc ? <p>文档分 {ontology.chunks_processed} 段交给模型{ontology.chunks_total > ontology.chunks_processed ? `（共 ${ontology.chunks_total} 段，文档太长，后面的没有处理）` : ""}；被剔除的项是引用在原文里找不到，或两端不是已核实的概念。</p>
          : attempts.rejected.length > 0 && <p>前面被代码退回的原因：{attempts.rejected.map(([code, n]) => `${ERROR_LABELS[code] || code} ${n} 处`).join("、")}。</p>}
        <p>模型 {ontology.model}，提示词 {ontology.prompt_version}。建模目的会作为提示的一部分交给模型。</p>
        {doc && ontology.rejected.length > 0 && <ul>{ontology.rejected.map((r, i) => <li key={i}>{r.item}：{r.reason}</li>)}</ul>}
      </details>
    </section>
    {run.previous && <section className="pr-card" id="os-stability">
      <h2>和上一次运行比</h2>
      {stabilityLines(run.previous.diff).length
        ? <><p className="pr-muted">同一份文件上一次运行（{run.previous.started_at.slice(0, 16).replace("T", " ")}）得到的本体和这次不一样。模型每次搭的本体会有出入，下面是差别；拿不准时用"对照标准答案"和参考本体比。</p>
          <ul className="os-list">{stabilityLines(run.previous.diff).map((l) => <li key={l}>{l}</li>)}</ul></>
        : <p className="pr-muted">同一份文件上一次运行（{run.previous.started_at.slice(0, 16).replace("T", " ")}）得到的对象和关系与这次完全一致。</p>}
    </section>}
    <section className="pr-card">
      <div className="pr-card-head"><h2>本体</h2>
        <div className="og-toggle" role="group" aria-label="显示方式">{[["graph", "关系图"], ["list", "列表"]].map(([key, text]) => <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}>{text}</button>)}</div></div>
      {view === "graph" && <OntologyGraph run={run} {...graphProps} onAsk={doc ? null : graphProps.onAsk} />}
      {view === "list" && <div className="os-list-view">
        <h3 className="os-sub">对象（{ontology.object_types.length}）</h3>
        <div className="pr-types">{ontology.object_types.map((t) => <article key={t.key} className="pr-type">
          <span className="pr-tag">{t.key}</span>
          <h3>{t.label || t.key}</h3>
          {t.populated_from.length > 0 && <p>来自：{typeSources(t)}</p>}
          {t.definition && <p>{t.definition}</p>}
          {t.attributes.length > 0 && <p>属性：{t.attributes.map((a) => a.path).join("、")}</p>}
          {t.time_field && <p>时间：{t.time_field.path}</p>}
          {t.rationale && <small>{t.rationale}</small>}
        </article>)}</div>
        <h3 className="os-sub">关系（{ontology.relations.length}）</h3>
        {ontology.relations.length ? <ul className="pr-rows">{ontology.relations.map((r) => <li key={r.key}>
          <b>{typeLabel(ontology, r.from)} {r.label || "→"} {typeLabel(ontology, r.to)}</b><span>{r.meaning}</span><code>{r.source}</code></li>)}</ul>
          : <p className="pr-muted">没有关系。</p>}
      </div>}
    </section>
    {(ontology.data_gaps.length > 0 || ontology.ignored_fields.length > 0) && <section className="pr-card">
      <h2>模型指出的数据缺口（{ontology.data_gaps.length}）</h2>
      {ontology.data_gaps.length > 0 && <ul className="os-list">{ontology.data_gaps.map((g) => <li key={g}>{g}</li>)}</ul>}
      {ontology.ignored_fields.length > 0 && <details><summary>标为不用的字段（{ontology.ignored_fields.length}）</summary><ul>{ontology.ignored_fields.map((f) => <li key={`${f.source}.${f.path}`}>{f.source}.{f.path}：{f.reason}</li>)}</ul></details>}
    </section>}
  </>;
}

function Checks({ fit, title, note }) {
  const summary = checkSummary(fit);
  return <section className="pr-card">
    <div className="pr-card-head"><h2>{title}</h2><span className="pr-muted">通过 {summary.passed} / {summary.total} 项</span></div>
    <p className="pr-muted">{note}</p>
    <ul className="os-checks">{fit.checks.map((c) => <li key={c.key}><span className={`os-pill ${c.passed ? "os-pass" : "os-fail"}`}>{c.passed ? "通过" : "不通过"}</span>{CHECK_LABELS[c.key] || c.key}</li>)}</ul>
  </section>;
}

function DataFit({ run, onShow }) {
  const fit = run.evaluation.data_fit;
  const { ontology } = run;
  if (!fit) return <section className="pr-card"><p className="pr-error">本体没有通过核验，无法评测。先看"看本体"里被退回的原因。</p></section>;
  return <>
    <Checks fit={fit} title="数据体检：本体和数据对得上吗" note="全部由代码拿上传的每一行计算，不经过模型。每个问题都可以点“在图上看”，回到关系图里对应的对象。" />
    {fit.identity_conflicts.length > 0 && <section className="pr-card">
      <h2>同一对象信息打架（{fit.identity_conflicts.length}）</h2>
      <div className="pr-table-wrap"><table className="pr-table"><thead><tr><th>对象</th><th>表</th><th>编号</th><th>字段</th><th>不同的值</th><th></th></tr></thead>
        <tbody>{fit.identity_conflicts.map((c, i) => <tr key={i}><td>{typeLabel(ontology, c.type)}</td><td>{c.source}</td><td>{c.identity}</td><td>{c.field}</td><td>{c.values.join(" / ")}</td><td><ShowOnGraph type={c.type} onShow={onShow} /></td></tr>)}</tbody></table></div>
    </section>}
    {fit.identity_spellings?.length > 0 && <section className="pr-card">
      <h2>同一个编号有几种写法（{fit.identity_spellings.length}）</h2>
      <p className="pr-muted">这些写法被当成同一个对象合并了，但源数据里写法不统一，建议在源系统里统一。</p>
      <ul className="pr-rows">{fit.identity_spellings.map((x, i) => <li key={i}><b>{typeLabel(ontology, x.type)} {x.identity}</b><span>写法：{x.variants.map((v) => `“${v}”`).join("、")}</span><ShowOnGraph type={x.type} onShow={onShow} /></li>)}</ul>
    </section>}
    {fit.suspected_duplicates?.length > 0 && <section className="pr-card">
      <h2>疑似重复（请人工确认）</h2>
      <p className="pr-muted">去掉开头的 0 以后相同的编号，现在被当成不同的对象；如果它们其实是同一个，需要在源数据里统一。</p>
      <ul className="pr-rows">{fit.suspected_duplicates.map((d, i) => <li key={i}><b>{typeLabel(ontology, d.type)}</b><span>{d.identities.join(" 和 ")}</span><ShowOnGraph type={d.type} onShow={onShow} /></li>)}</ul>
    </section>}
    {fit.missing_across_sources.length > 0 && <section className="pr-card">
      <h2>引用了、但在它所属的表里找不到</h2>
      <ul className="pr-rows">{fit.missing_across_sources.map((m) => <li key={`${m.type}/${m.source}`}><b>{typeLabel(ontology, m.type)}：{m.count} 个不在"{m.source}"表里</b><span>例如 {m.examples.join("、")}</span><ShowOnGraph type={m.type} onShow={onShow} /></li>)}</ul>
    </section>}
    <details className="pr-card os-more"><summary>关系连通、字段去处等明细</summary>
      <h3 className="os-sub">关系连通</h3>
      <div className="pr-table-wrap"><table className="pr-table"><thead><tr><th>关系</th><th>所在表</th><th>连上的行 / 总行</th></tr></thead>
        <tbody>{fit.relations.map((r) => { const rel = ontology.relations.find((x) => x.key === r.key);
          return <tr key={r.key}><td>{rel ? `${typeLabel(ontology, rel.from)} ${rel.label || "→"} ${typeLabel(ontology, rel.to)}` : r.key}</td><td>{r.source}</td><td>{r.linked_rows} / {r.rows}</td></tr>; })}</tbody></table></div>
      <p className="pr-muted">孤立对象（一条关系都没有）：{fit.orphans.map((o) => `${typeLabel(ontology, o.type)} ${o.count}`).join("、") || "无"}。表的连通：{fit.source_groups.map((g) => g.join(" + ")).join(" ｜ ")}。</p>
      <h3 className="os-sub">字段去处</h3>
      <div className="pr-table-wrap"><table className="pr-table"><thead><tr><th>表</th><th>列数</th><th>用上</th><th>写明不用</th><th>没有去处</th></tr></thead>
        <tbody>{Object.entries(fit.fields).map(([name, f]) => <tr key={name}><td>{name}</td><td>{f.total}</td><td>{f.used}</td><td>{f.ignored}</td><td>{f.unaccounted}</td></tr>)}</tbody></table></div>
    </details>
  </>;
}

function DocumentFitView({ run, onShow }) {
  const fit = run.evaluation.document_fit;
  if (!fit) return <section className="pr-card"><p className="pr-error">没有提取出可核实的概念，无法评测。先看"看本体"里被剔除的原因。</p></section>;
  const keyOf = (label) => run.ontology.object_types.find((t) => t.label === label)?.key;
  return <>
    <Checks fit={fit} title="文档检查：每一项都能回到原文吗" note={`由代码逐项核对模型给的引用是否真在原文里，不经过模型。模型共提出 ${fit.proposed} 项，保留 ${fit.kept} 项，剔除 ${fit.rejected} 项。${fit.cut ? "文档太长，只处理了前面的部分。" : ""}`} />
    {fit.isolated.length > 0 && <section className="pr-card"><h2>没有任何关系的概念（{fit.isolated.length}）</h2>
      <div className="os-chips os-suggest">{fit.isolated.map((label) => <button key={label} type="button" onClick={() => onShow(keyOf(label))}>{label}</button>)}</div></section>}
  </>;
}

const EVAL_VIEWS = [["fit", "数据体检"], ["qa", "业务问答"], ["ref", "对照标准"]];

function EvaluationTab({ run, evalView, setEvalView, questions, onShow, onPath }) {
  const doc = isDocument(run);
  const tiles = Object.fromEntries(overviewTiles(run).map((t) => [t.key, t]));
  return <>
    <div className="os-segments" role="tablist" aria-label="评测">{EVAL_VIEWS.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={evalView === key} onClick={() => setEvalView(key)}>
      <b>{key === "fit" && doc ? "文档检查" : label}</b><small className={`os-tone-${tiles[key].tone}`}>{tiles[key].value}</small></button>)}</div>
    {evalView === "fit" && (doc ? <DocumentFitView run={run} onShow={onShow} /> : <DataFit run={run} onShow={onShow} />)}
    {evalView === "qa" && (doc ? <section className="pr-card"><h2>业务问答</h2><p className="pr-muted">文档没有数据行可以查询，业务问答只对数据表可用。把同一业务的数据表也上传，就能用数据回答问题。</p></section>
      : <QuestionsSection run={run} {...questions} onPath={onPath} />)}
    {evalView === "ref" && <ReferenceSection run={run} canCompare={questions.canAsk} onCompare={questions.onCompare} busy={questions.comparing} error={questions.compareError} onUpload={questions.onUpload} />}
  </>;
}

export function OntologyStudio() {
  const [tab, setTab] = useState("upload");
  const [run, setRun] = useState(() => loadLocal());
  const [health, setHealth] = useState("checking");
  const [busy, setBusy] = useState(false);
  const [events, setEvents] = useState([]);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState("");
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState("");
  const [view, setView] = useState("graph");
  const [evalView, setEvalView] = useState("fit");
  const [selected, setSelected] = useState(null);
  const [path, setPath] = useState(null);
  const [reveal, setReveal] = useState(0);
  const timer = useRef(null);
  const askRef = useRef(null);

  useEffect(() => {
    fetch("/api/ontology/health", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((h) => setHealth(h.model_ready ? "ready" : "no-key")).catch(() => setHealth("offline"));
  }, []);
  useEffect(() => () => clearInterval(timer.current), []);

  function show(result) { const valid = validateRun(result); setRun(valid); saveLocal(valid); setSelected(null); setPath(null); setEvalView("fit"); setTab("ontology"); }
  function update(result) { const valid = validateRun(result); setRun(valid); saveLocal(valid); }
  async function build(file, purpose) {
    setBusy(true); setError(""); setElapsed(0); setEvents([]);
    const started = Date.now();
    timer.current = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    try {
      const body = JSON.stringify({ filename: file.name, content_base64: await toBase64(file), purpose });
      const response = await fetch("/api/ontology/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body });
      const data = await response.json().catch(() => ({ error: `服务返回 ${response.status}` }));
      if (!response.ok) throw new Error(serviceError(response.status, data));
      for (;;) {
        await new Promise((r) => setTimeout(r, 1000));
        const poll = await fetch(`/api/ontology/jobs/${data.job_id}`, { cache: "no-store" });
        const job = await poll.json().catch(() => ({ state: "failed", error: `服务返回 ${poll.status}` }));
        if (!poll.ok) throw new Error(serviceError(poll.status, job));
        setEvents(job.events || []);
        if (job.state === "done") { show(job.result); break; }
        if (job.state === "failed") throw new Error(job.error || "建模失败");
      }
    } catch (e) { setError(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message); }
    finally { clearInterval(timer.current); setBusy(false); }
  }
  async function post(url, payload, setWorking, setFailure) {
    setWorking(true); setFailure("");
    try {
      const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await response.json().catch(() => ({ error: `服务返回 ${response.status}` }));
      if (!response.ok) throw new Error(serviceError(response.status, data));
      update(data);
    } catch (e) { setFailure(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message); }
    finally { setWorking(false); }
  }
  const ask = (question) => post("/api/ontology/ask", { saved_as: run.saved_as, ...(question ? { question } : {}) }, setAsking, setAskError);
  async function compare(file) {
    let reference;
    try { reference = JSON.parse(await file.text()); } catch { setCompareError(`${file.name} 不是有效的 JSON`); return; }
    post("/api/ontology/compare", { saved_as: run.saved_as, reference, reference_name: file.name }, setComparing, setCompareError);
  }
  function askOntology() { setEvalView("qa"); setTab("evaluation"); setTimeout(() => { askRef.current?.scrollIntoView({ block: "center" }); askRef.current?.focus(); }, 50); }
  function showOnGraph(type) { if (!type) return; setPath(null); setSelected({ kind: "node", key: type }); setView("graph"); setTab("ontology"); setReveal((n) => n + 1); }
  function showPath(query, text) { const p = pathOf(run.ontology, query); if (!p) return; setPath({ ...p, text }); setSelected({ kind: "node", key: p.nodes[p.nodes.length - 1] }); setView("graph"); setTab("ontology"); setReveal((n) => n + 1); }
  function openTile(key) {
    if (key === "ontology" || key === "stability") { setTab("ontology"); if (key === "stability") setTimeout(() => document.getElementById("os-stability")?.scrollIntoView({ block: "start" }), 50); return; }
    setEvalView(key); setTab("evaluation");
  }
  function demo(url = DEMO_URL) { setError(""); readText(url).then(show).catch((e) => setError(`示例读取失败：${e.message}`)); }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(run, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `${run.file.name.replace(/\.[^.]+$/, "")}-ontology.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className="pr-page" aria-labelledby="os-title">
    <header className="pr-head">
      <div className="pr-head-line">
        <h1 id="os-title">上传建本体</h1>
        <span className="pr-meta">上传一份业务文件，自动生成公司本体，再自动体检、问答、对照</span>
      </div>
      {run && tab !== "upload" && <div className="os-overview">
        <div className="os-overview-file"><span className="pr-muted">当前文件</span><b>{run.file.name}</b><button className="pr-link" onClick={download}>下载结果</button></div>
        {overviewTiles(run).map((t) => <button key={t.key} type="button" className={`os-tile os-tone-${t.tone}`} onClick={() => openTile(t.key)}><small>{t.label}</small><b>{t.value}</b></button>)}
      </div>}
      <nav className="pr-tabs os-steps-nav" role="tablist" aria-label="步骤">{TABS.map(([key, label], i) => <button key={key} type="button" role="tab" id={`os-tab-${key}`}
        aria-selected={tab === key} aria-controls="os-panel" disabled={key !== "upload" && !run} onClick={() => setTab(key)}><span className="os-step-no">{i + 1}</span>{label}</button>)}</nav>
    </header>
    <div id="os-panel" role="tabpanel" aria-labelledby={`os-tab-${tab}`} className="pr-panel os-panel">
      {tab === "upload" && <UploadTab health={health} busy={busy} events={events} elapsed={elapsed} error={error} onBuild={build} onDemo={() => demo(DEMO_URL)} onDocDemo={() => demo(DEMO_DOC_URL)} />}
      {tab === "ontology" && run && <OntologyTab run={run} view={view} setView={setView}
        graphProps={{ selected, onSelect: (s) => { setSelected(s); setPath(null); }, path, onClearPath: () => setPath(null), onAsk: askOntology, reveal }} />}
      {tab === "evaluation" && run && <EvaluationTab run={run} evalView={evalView} setEvalView={setEvalView} onShow={showOnGraph} onPath={showPath}
        questions={{ canAsk: Boolean(run.saved_as) && health === "ready", busy: asking, error: askError, onAsk: ask, askRef, onCompare: compare, comparing, compareError, onUpload: () => setTab("upload") }} />}
    </div>
  </section>;
}
