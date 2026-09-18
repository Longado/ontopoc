import { useEffect, useRef, useState } from "react";
import { askSuggestions, bridgeLines, latestAsked, layoutTables } from "./dataLayoutModel.js";
import {
  ACCEPT, CHECK_LABELS, DEMO_DOC_URL, DEMO_URL, ERROR_LABELS, isDocument, previousLine, sourceLine, RESULT_KEY, STATUS_LABELS, answerLines, attemptSummary, checkSummary,
  COVERAGE_NOTE, conflictGroups, conflictNote, jobOutcome, jobStartedAt, localTime, memoryNote, saveResult, progressSteps, referenceCounts, serviceError, sharePercent, stabilityLines, staleNote, typeLabel, validateRun,
} from "./ontologyStudioModel.js";
import { consensusLines, overviewTiles, pathOf } from "./ontologyGraphModel.js";
import { batchProblem, batchSummary, isDoc, sizeText, uploadPayload } from "./ontologyUploadModel.js";
import { summaryMarkdown } from "./ontologySummaryModel.js";
import { OntologyGraph, Verdict } from "./OntologyGraph.jsx";
import { ACCEPTANCE_LABELS, acceptItem, acceptanceSummary, canAccept, purposeNote, savedAcceptance } from "./ontologyAcceptanceModel.js";
import { addType, confirmProgress, decisionsOf, otherRunTypes, referenceDownload, removeAdded, renameType, setVerdict, splitExtras } from "./ontologyConfirmModel.js";
import { toggleVariant, variantNote, variantRows } from "./ontologyVariantsModel.js";
import { cardinalityLabel, cardinalityLine, formOf } from "./ontologyHandoverModel.js";
import { folderLabel } from "./runLibraryModel.js";
import { FillBar, ObjectCards, ObjectDetail, SubLayout, TypeChip } from "./ObjectPages.jsx";
import { InstanceGraph } from "./InstanceGraph.jsx";
import { RulesView } from "./RulesView.jsx";
import { rulesTile } from "./rulesModel.js";
import { earlierVersionOf, versionRows } from "./versionModel.js";
import { answerTags, filterQuestions, stabilityRows, typeMix } from "./visualModel.js";
import { objectsNav, qaNav, sectionOfTile, sectionsFor } from "./workspaceModel.js";
import "./PublicRecallReview.css";
import "./OntologyStudio.css";

const START = "PYTHONPATH=src python -m ontology_poc_generator.ontology_server";

const readText = (url) => fetch(url, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(`读取失败（${r.status}）`); return r.json(); });
const storage = () => { try { return window.localStorage; } catch { return null; } };
const JOB_KEY = "ontopoc.job";   // this tab's build in progress, so a refresh picks it up again
const pendingJob = { get: () => { try { return sessionStorage.getItem(JOB_KEY); } catch { return null; } },
  set: (id) => { try { if (id) sessionStorage.setItem(JOB_KEY, id); else sessionStorage.removeItem(JOB_KEY); } catch { /* a private window without storage: a refresh just loses the progress view */ } } };
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

function Mark() {
  return <svg className="os-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="0" y="0" width="10" height="10" fill="#4948df" /><rect x="22" y="0" width="10" height="10" fill="#afacfd" />
    <rect x="0" y="22" width="10" height="10" fill="#f3b944" /><rect x="22" y="22" width="10" height="10" fill="#4746dc" />
    <rect x="10" y="3" width="12" height="4" fill="#7474f9" /><rect x="3" y="10" width="4" height="12" fill="#7474f9" /><rect x="25" y="10" width="4" height="12" fill="#4748e2" /><rect x="10" y="25" width="12" height="4" fill="#7474f9" /></svg>;
}

function Progress({ events, kind, elapsed, lost }) {
  const steps = progressSteps(events, kind);
  return <div className="os-progress" role="status" aria-live="polite">
    <ol className="os-steps">{steps.map((st) => <li key={st.key} className={`is-${st.status}`}>
      <span className="os-step-dot" aria-hidden="true">{st.status === "done" ? "✓" : ""}</span>
      <span><b>{st.label}</b>{st.detail && <small>{st.detail}</small>}</span>
      <em className="sr-only">{st.status === "done" ? "完成" : st.status === "active" ? "进行中" : "未开始"}</em>
    </li>)}</ol>
    <p className="pr-muted">已用 {elapsed} 秒。每一步都来自本机服务的实时回报；模型出错时代码会退回重做，最多三次。</p>
    {lost && <p className="os-stale" role="alert">现在连不上本机建模服务。它回来后，这里会接着显示这次建模的结果；它若重启过，会告诉你这次建模中断了。</p>}
  </div>;
}

function SendPreview({ file }) {
  const [state, setState] = useState({ status: "idle" });
  async function load() {
    if (state.status !== "idle") return;
    setState({ status: "loading" });
    try {
      const response = await fetch("/api/ontology/preview", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, content_base64: await toBase64(file) }) });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(serviceError(response.status, data));
      setState({ status: "ready", data });
    } catch (e) { setState({ status: "error", error: e.message === "Failed to fetch" ? "连不上本机建模服务。" : e.message }); }
  }
  const d = state.data;
  return <details className="os-how os-preview" onToggle={(e) => { if (e.currentTarget.open) load(); }}>
    <summary>看看会发给模型什么</summary>
    {state.status === "loading" && <p>正在读取文件…</p>}
    {state.status === "error" && <p className="pr-error">{state.error}</p>}
    {d?.kind === "document" && <p>文档的正文会按段发给模型：共 {d.paragraphs} 段、{d.chars} 字，分成 {d.chunks_total} 块，这次会发 {d.chunks_sent} 块{d.chunks_sent < d.chunks_total ? "（太长，后面的不处理）" : ""}。</p>}
    {d?.kind === "table" && <>
      <p>只发下面这些：每列的字段名和最多 3 个示例值；出题时，取值不超过 12 种的列会发全部取值。其余的行不会离开本机，数据体检和答题都在本机算。</p>
      {d.sources.map((src) => <div key={src.name} className="pr-table-wrap"><table className="pr-table">
        <caption>{src.name}（{src.record_count} 行）</caption>
        <thead><tr><th>字段</th><th>示例值</th><th>出题时发送的全部取值</th></tr></thead>
        <tbody>{src.fields.map((f) => <tr key={f.path}><td>{f.path}</td><td>{f.examples.join("、")}</td><td>{f.values ? f.values.join("、") : "—"}</td></tr>)}</tbody>
      </table></div>)}
    </>}
  </details>;
}

function UploadTab({ health, busy, events, elapsed, lost, error, onBuild, onDemo, onDocDemo, runs }) {
  const [files, setFiles] = useState([]);
  const [asVersion, setAsVersion] = useState(null);   // null: not answered; true / false: the person's answer
  const earlier = earlierVersionOf(runs, files);
  useEffect(() => setAsVersion(null), [earlier?.saved_as]);
  const go = () => onBuild(files, purpose, earlier && asVersion ? earlier.saved_as : null);
  const [purpose, setPurpose] = useState("");
  const [over, setOver] = useState(false);
  const offline = health === "offline";
  const kind = files.length && !files.some(isDoc) ? "table" : files.length ? "document" : null;
  const problem = files.length ? batchProblem(files) : "";
  const blocked = offline ? "本机建模服务没有启动" : health === "no-key" ? "建模服务缺少模型凭据" : !files.length ? "先传文件" : problem;
  const pick = (picked) => setFiles((old) => [...old, ...[...picked].filter((f) => !old.some((o) => o.name === f.name && o.size === f.size))]);
  const drop = (e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files || []); };
  return <div className="os-start">
    <h1 id="os-title">今天要看哪份数据？</h1>
    <p className="os-start-sub">传几张业务表或一份文档，写一句你想弄清的问题。文件只留在这台电脑上。</p>
    {busy ? <div className="os-composer is-busy"><Progress events={events} kind={kind} elapsed={elapsed} lost={lost} /></div> : <>
      <input id="os-file" className="sr-only" type="file" accept={ACCEPT} multiple onChange={(e) => { pick(e.target.files || []); e.target.value = ""; }} />
      <div className={`os-composer${over ? " is-over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}>
        {files.length > 0 && <div className="os-composer-files">
          {files.map((f) => <span key={`${f.name}-${f.size}`} className="os-file-chip">{f.name}<button type="button" aria-label={`去掉 ${f.name}`} onClick={() => setFiles(files.filter((o) => o !== f))}>×</button></span>)}
          <small className={problem ? "os-bad" : "pr-muted"}>{problem || batchSummary(files)}</small>
        </div>}
        <label htmlFor="os-purpose" className="sr-only">这份本体要帮你回答什么问题</label>
        <textarea id="os-purpose" rows={3} maxLength={300} value={purpose} placeholder={files.length ? "想从这份数据里弄清什么？例如：哪些客户、产品的售后问题最多？" : "把文件拖进来，或点左下角的＋。再写一句想弄清的问题（可选）"}
          onChange={(e) => setPurpose(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !blocked) go(); }} />
        <div className="os-composer-bar">
          <label htmlFor="os-file" className="os-composer-add" title="选文件：数据表 .xlsx .csv，文档 .md .txt .docx .pdf，不超过 10 MB">＋</label>
          <button type="button" className="os-composer-go" disabled={Boolean(blocked)} title={blocked || "生成本体并评测"} aria-label="生成本体并评测" onClick={go}>➤</button>
        </div>
      </div>
      {earlier && <div className="os-version-ask" role="group" aria-label="是不是新版本">
        <span>「{folderLabel(earlier.file)}」的新版本？</span>
        <button type="button" aria-pressed={asVersion === true} onClick={() => setAsVersion(true)} title="上次的确认、验收问题和规则接着用，并比出哪些对象多了、少了">是</button>
        <button type="button" aria-pressed={asVersion === false} onClick={() => setAsVersion(false)}>不是</button>
      </div>}
      <div className="os-start-chips">
        {!files.length && <><span className="pr-muted">没有文件？</span>
          <button type="button" onClick={onDemo}>打开示例数据表</button>
          <button type="button" onClick={onDocDemo}>打开示例文档</button></>}
        {files.length > 0 && !purpose && EXAMPLE_QUESTIONS.map((q) => <button key={q} type="button" onClick={() => setPurpose(q)}>{q}</button>)}
      </div>
      {files.length === 1 && !problem && !offline && <SendPreview key={`${files[0].name}-${files[0].size}-${files[0].lastModified}`} file={files[0]} />}
    </>}
    {error && <p role="alert" className="pr-error">{error}</p>}
    {offline && <div className="pr-note"><p>本机的建模服务没有启动。在仓库根目录运行（需要本机 DeepSeek 凭据）：</p><code className="os-cmd">{START}</code></div>}
  </div>;
}

function Hint({ children }) {   // the explanation a first-time reader needs once; the card opens on its result
  return <details className="os-hint"><summary>这是什么</summary><div className="os-hint-body">{children}</div></details>;
}

function useFirst(items, n = SHOWN_GROUPS) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, n);
  const toggle = items.length > n && <button type="button" className="pr-link os-more-groups" onClick={() => setAll(!all)}>{all ? `只看前 ${n} 条` : `展开其余 ${items.length - n} 条`}</button>;
  return [shown, toggle];
}

function Conflicts({ fit, ontology, onShow }) {
  const [rows, toggle] = useFirst(fit.identity_conflicts);
  const groups = conflictGroups(fit);
  return <section className="pr-card">
    <h2>同一对象信息打架（{fit.identity_conflicts.length}）</h2>
    <p className="pr-muted">同一个编号在不同行里，某个字段写了不同的值。也可能不是数据错了，而是这里本来就是一对多（例如一张订单分三次交付，三个交付日期挂在了订单上）：那要把它拆成单独的对象，而不是回去改数据。{fit.identity_conflicts.length > SHOWN_GROUPS ? "如果一类对象大量打架，常见原因是识别字段不够区分：同一个编号其实是好几样东西（例如缺了行号）。" : ""}</p>
    {groups.length > 1 && <ul className="os-list">{groups.map((g) => <li key={`${g.type}/${g.field}`}>{typeLabel(ontology, g.type)}的“{g.field}”：{g.count} 个编号</li>)}</ul>}
    <div className="pr-table-wrap"><table className="pr-table"><thead><tr><th>对象</th><th>表</th><th>编号</th><th>字段</th><th>不同的值</th><th></th></tr></thead>
      <tbody>{rows.map((c, i) => <tr key={i}><td>{typeLabel(ontology, c.type)}</td><td>{c.source}</td><td>{c.identity}</td><td>{c.field}</td><td>{c.values.join(" / ")}</td><td><ShowOnGraph type={c.type} onShow={onShow} /></td></tr>)}</tbody></table></div>
    {toggle}
  </section>;
}

function Spellings({ fit, ontology, onShow }) {
  const [rows, toggle] = useFirst(fit.identity_spellings);
  return <section className="pr-card">
    <h2>同一个编号有几种写法（{fit.identity_spellings.length}）</h2>
    <p className="pr-muted">这些写法被当成同一个对象合并了，但源数据里写法不统一，建议在源系统里统一。</p>
    <ul className="pr-rows">{rows.map((x, i) => <li key={i}><b>{typeLabel(ontology, x.type)} {x.identity}</b><span>写法：{x.variants.map((v) => `“${v}”`).join("、")}</span><ShowOnGraph type={x.type} onShow={onShow} /></li>)}</ul>
    {toggle}
  </section>;
}

function Variants({ run, variants, onShow }) {
  const rows = variantRows(run, variants.decisions);
  const note = variantNote(run);
  const accepted = rows.filter((g) => g.accepted);
  return <section className="pr-card" id="os-variants">
    <div className="pr-card-head"><h2>两个名字其实是同一个东西</h2>{rows.length > 0 && <span className="pr-muted">候选 {rows.length} 组，你采纳了 {accepted.length} 组</span>}</div>
    <Hint>上面那项检查管的是同一个编号被写歪（只认大小写和空格的差别）。这里管的是两个不同的名字：“DEPARTMENT OF FLEET AND FACILITY MANAGEMENT”和“DEPT OF FLEET MGMT”是同一个部门，代码看不出来，所以它们现在是两个对象。这一步把按名字识别的对象的全部取值交给模型，问哪些指同一个东西；模型给的每一组，代码都拿数据核对过，数据里没有的取值一律丢掉。</Hint>
    <div className="os-go">
      <button type="button" className="pr-primary" disabled={!variants.canFind || variants.busy} onClick={variants.onFind}>{variants.busy ? "找对应中…" : note ? "重新找一遍" : "找出可能的对应"}</button>
      <span className="pr-muted">{variants.canFind ? "会调用一次模型，只发这些名字和各自的记录数。采纳只是记下你的判断：不改数据，也不把两个对象合并。" : run.saved_as ? "本机建模服务没有连上，暂时不能找。" : "这是示例结果，找对应要上传自己的文件。"}</span>
    </div>
    {variants.error && <p role="alert" className="pr-error">{variants.error}</p>}
    {note && <p className="pr-muted">{note.line}</p>}
    {rows.length > 0 && <ul className="pr-rows os-variants">{rows.map((g) => <li key={`${g.type}/${g.values.join("/")}`}>
      <b>{g.label}：{g.values.map((v, i) => `“${v}”${g.records ? `（${g.records[i]} 条）` : ""}`).join(" ＝ ")}</b>
      <span>{g.carried ? "这组是你上次确认时采纳的，这次模型没有重新提出" : ""}{g.reasoning ? `模型：${g.reasoning}` : ""}</span>
      {g.accepted && variants.decisions.types?.[g.type]?.verdict !== "ok" && <span className="os-tone-warn">保存确认前要先把{g.label}判“对”</span>}
      <button type="button" className="pr-link" onClick={() => variants.onToggle(g)}>{g.accepted ? "已采纳 ✕" : "采纳"}</button>
      <ShowOnGraph type={g.type} onShow={onShow} />
    </li>)}</ul>}
    {note?.dropped.length > 0 && <details className="os-how"><summary>代码丢掉的 {note.dropped.length} 组</summary>
      <ul>{note.dropped.map((d) => <li key={d}>{d}</li>)}</ul></details>}
    {accepted.length > 0 && <p className="pr-note">采纳的 {accepted.length} 组要到“本体管理”底部的逐项确认里保存才算数：保存后它们进你确认过的本体，下次上传同一份文件自动带回来。</p>}
  </section>;
}

function ShowOnGraph({ type, onShow }) {
  return <button type="button" className="os-graph-link" onClick={() => onShow(type)}>在图上看</button>;
}

const SHOWN_GROUPS = 10;   // one screen of bars; the rest open on request

function AcceptanceSection({ run, acceptance, onSave, onPath, busy, error, adding, setAdding }) {
  const saved = savedAcceptance(run);
  return <section className="pr-card os-acceptance" id="os-acceptance">
    <div className="pr-card-head"><h2>验收问题</h2>{acceptance && <span className="pr-muted">{acceptanceSummary(acceptance)}</span>}</div>
    <Hint>模型每次出的题都不一样，所以"能答几题"没法比较。把你和客户说定的 1–3 道问题固定下来：存的是你已经看过、认可口径的那个查询。同一份文件以后再上传，代码用同样的查询再算一次，只告诉你哪道的答案或口径变了；查询用到的字段没了，就停下来指出断点，不去猜新含义。</Hint>
    {!acceptance && <p className="pr-muted">还没有。答出来的题旁点"存为验收问题"。</p>}
    {error && <p role="alert" className="pr-error">{error}</p>}
    {acceptance && <ul className="os-questions">{acceptance.items.map((item, i) => <li key={i} className="os-question">
      <div className="os-question-head"><span className={`os-pill os-${item.status === "broken" ? "ontology_gap" : item.status}`}>{ACCEPTANCE_LABELS[item.status] || item.status}</span><b>{item.question}</b>
        {item.changed !== null && <span className={`pr-muted ${item.changed ? "os-tone-warn" : ""}`}>{item.changed ? "和上次不一样" : "和上次一致"}</span>}</div>
      {item.note && <p className="pr-muted">口径：{item.note}</p>}
      <Answer item={item} onPath={onPath} run={run} />
      {!item.query && <p className="pr-muted">这道还没有能执行的查询，所以每次重跑都算作答不了。在下面的问答里再问一次，答出来并认可口径后，存为验收问题就会替换它。</p>}
      {item.status === "broken" && <p className="pr-error">这道题的查询在这一版本体上走不通：{item.reason}。要么改本体，要么重新出题并重新认可口径。</p>}
      {item.changed && item.previous?.answer && <details className="os-how"><summary>上次的答案</summary><Answer item={item.previous} /></details>}
      <button type="button" className="pr-link" disabled={busy} onClick={() => onSave(saved.filter((s) => s.question !== item.question))}>去掉这道</button>
    </li>)}</ul>}
    {adding && <div className="os-add">
      <label htmlFor="os-note">{adding.item.query ? '口径说明（可选，写清按什么算，例如"按订单号计数，不是按订单行"）' : "这道现在还答不了。先记下来，它会一直留在验收问题里、算进总数，不会被其他题的通过盖住。备注（可选，例如谁点名要的、要补什么数据）"}
        <input id="os-note" value={adding.note} maxLength={200} onChange={(e) => setAdding({ ...adding, note: e.target.value })} /></label>
      <div className="os-go">
        <button type="button" className="pr-primary" disabled={busy} onClick={() => { onSave(acceptItem(saved, adding.item, adding.note)); setAdding(null); }}>{busy ? "保存中…" : "确认存下"}</button>
        <button type="button" className="pr-link" onClick={() => setAdding(null)}>取消</button>
      </div>
    </div>}
  </section>;
}

function Answer({ item, onPath, run }) {
  const [all, setAll] = useState(false);
  const a = item.answer;
  const note = run && item.query ? conflictNote(run, pathOf(run.ontology, item.query)?.nodes || []) : "";
  const max = a?.groups?.length ? Math.max(...a.groups.map(([, n]) => n)) : 0;
  const width = ([, n, all]) => (a.share ? (n / all) * 100 : (n / max) * 100);   // a measure ranks by its own value, so max covers it too
  const extra = answerLines(item).slice(a?.groups?.length || 0);   // group lines come first; the bars show those
  return <>
    {answerTags(item).length > 0 && <p className="os-answer-tags" title={a.share ? "分母小的组比例容易偏高，请一起看分母" : a.measure?.op === "average" ? "只有一两个值的组，别当成规律" : undefined}>{answerTags(item).map((t) => <span key={t}>{t}</span>)}</p>}
    {a?.groups?.length > 0 && <ul className="os-bars">{(all ? a.groups : a.groups.slice(0, SHOWN_GROUPS)).map((g) => <li key={g[0]}><span>{g[0]}</span><i style={{ width: `${Math.max(2, width(g))}%` }} /><b>{a.share ? `${g[1]} / ${g[2]}（${sharePercent(g[1], g[2])}%）` : a.measure ? `${g[1].toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${g[2] === undefined ? "" : `（${g[2]} 个值）`}` : g[1]}</b></li>)}</ul>}
    {a?.groups?.length > SHOWN_GROUPS && <button type="button" className="pr-link os-more-groups" onClick={() => setAll(!all)}>{all ? "只看前 10 组" : `展开其余 ${a.groups.length - SHOWN_GROUPS} 组`}</button>}
    {note && <p className="pr-muted">{note}</p>}
    {extra.length > 0 && <ul className="os-answer">{extra.map((l) => <li key={l}>{l}</li>)}</ul>}
    {item.path && <p className="os-path-line" title="怎么查的"><span aria-hidden="true">↳</span><span className="sr-only">怎么查的：</span>{item.path}{item.query && onPath && <button type="button" className="os-graph-link" onClick={() => onPath(item.query, item.path)}>在图上看</button>}</p>}
    {item.status === "query_limit" && <p className="pr-muted" title="查询能数个数、算占比、求和求平均、按几样东西分组；还不能限定时间段、按数值条件筛选、一道题同时给两个数">这种问法还不支持，本体没问题。{item.reason ? `模型：${item.reason}` : ""}</p>}
    {item.status !== "answered" && item.status !== "query_limit" && item.reason && <p className="pr-muted">原因：{item.reason}</p>}
  </>;
}

function QuestionItem({ item, onPath, run, onAccept }) {
  const why = run && onAccept ? canAccept(run, item) : "不可用";
  return <li className="os-question">
    <div className="os-question-head"><span className={`os-pill os-${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span><b>{item.question}</b></div>
    <Answer item={item} onPath={onPath} run={run} />
    {onAccept && item.status === "answered" && (why
      ? <p className="pr-muted">{why}</p>
      : <button type="button" className="pr-link os-accept" onClick={() => onAccept(item)} title="把这道题和这个查询固定下来，以后重传同一份文件会再算一次">＋ 存为验收问题</button>)}
    {onAccept && item.status !== "answered" && !why && <button type="button" className="pr-link os-accept" onClick={() => onAccept(item)} title="现在还答不了，先留在验收清单上">＋ 记为必答题</button>}
  </li>;
}

const QUESTION_FILTERS = [["all", "全部"], ["answered", "能回答"], ["unanswered", "答不了"]];

function QuestionsSection({ run, canAsk, busy, error, onAsk, onPath, onUpload, onAccept, part }) {
  const example = !run.saved_as;
  const round = run.evaluation.questions;
  const asked = run.evaluation.asked || [];
  const [which, setWhich] = useState("all");
  const mine = [...asked].reverse().flatMap((r, ri) => (r.error ? [{ error: r.error, key: `e${ri}` }] : r.items.map((item, i) => ({ item, key: `${ri}-${i}` }))));
  const shownMine = mine.filter((m) => m.error ? which === "all" : filterQuestions([m.item], which).length);
  const shownRound = round && !round.error ? filterQuestions(round.items, which) : [];
  return <section className="pr-card">
    <div className="pr-card-head"><h2 title={part === "model" && round ? `出题模型 ${round.model}，提示词 ${round.prompt_version}` : undefined}>{part === "mine" ? "你问的" : "模型出的题"}</h2>
      <div className="os-toolbar"><span className="pr-muted">{overviewTiles(run).find((t) => t.key === "qa").value}</span>
        <div className="og-toggle" role="group" aria-label="按能不能回答筛选">{QUESTION_FILTERS.map(([k, t]) => <button key={k} type="button" aria-pressed={which === k} onClick={() => setWhich(k)}>{t}</button>)}</div>
        {canAsk && part === "model" && <button type="button" className="pr-link" disabled={busy} onClick={() => onAsk(null)}>{busy ? "出题中…" : round ? "↻ 重新出一组" : "出一组题"}</button>}</div></div>
    <Hint>模型只负责把问题写成查询（一次调用）；答案由代码在上传的数据上算出来。答不了时写明是本体缺了哪一块、数据里没有，还是这种问法还不支持。</Hint>
    {!canAsk && <CannotAsk what="自己提问、重新出题" example={example} onUpload={onUpload} />}
    {error && <p role="alert" className="pr-error">{error}</p>}
    {part === "mine" && !mine.length && <p className="pr-muted">还没问过。</p>}
    {part === "mine" && shownMine.length > 0 && <><ul className="os-questions">{shownMine.map((m) => m.error ? <li key={m.key} className="pr-error">{m.error}</li> : <QuestionItem key={m.key} item={m.item} onPath={onPath} run={run} onAccept={onAccept} />)}</ul></>}
    {part === "model" && round && <>
      {round.error ? <p className="pr-error">{round.error}</p> : shownRound.length ? <ul className="os-questions">{shownRound.map((item, i) => <QuestionItem key={i} item={item} onPath={onPath} run={run} onAccept={onAccept} />)}</ul> : <p className="pr-muted">没有这一类的题。</p>}</>}
  </section>;
}

function AskBar({ run, canAsk, busy, error, onAsk, askRef, onPath }) {
  const [text, setText] = useState("");
  const [shown, setShown] = useState(null);   // a suggestion's answer, or "latest" for what was just asked
  const item = shown === "latest" ? latestAsked(run) : shown;
  const rows = run.sources.reduce((n, s) => n + s.rows, 0);
  const submit = () => { if (!text.trim() || busy) return; setShown("latest"); onAsk(text.trim()); setText(""); };
  return <section className="os-askbar" aria-label="问这份本体">
    <div className="os-askbar-row">
      <label htmlFor="os-question" className="sr-only">问这份本体</label>
      <input id="os-question" ref={askRef} value={text} maxLength={300} disabled={!canAsk || busy} autoComplete="off"
        placeholder={canAsk ? "问这份本体，例如：每个客户买了多少钱？" : "建模服务连上后可以提问"} onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
      <button type="button" className="pr-primary" disabled={!canAsk || busy || !text.trim()} onClick={submit}>{busy ? "在算…" : "问"}</button>
    </div>
    {askSuggestions(run).length > 0 && <div className="os-askbar-chips" aria-label="这份数据已经答过的问题">
      {askSuggestions(run).map((s) => <button key={s.question} type="button" aria-pressed={shown === s} onClick={() => setShown(shown === s ? null : s)}>{s.question}</button>)}</div>}
    {busy && shown === "latest" && <p className="pr-muted" role="status">出题员在把问题写成查询，写好后由代码在数据上算。</p>}
    {error && shown === "latest" && <p role="alert" className="pr-error">{error}</p>}
    {!busy && !(error && shown === "latest") && item && <div className="os-askbar-answer">
      {item.error ? <p className="pr-error">{item.error}</p> : <ul className="os-questions"><QuestionItem item={item} onPath={onPath} run={run} /></ul>}
      <p className="os-footprint">查询由出题员（模型）写，数字由代码在上传的 {rows.toLocaleString("zh-CN")} 行数据上算，不采信模型给的任何数字。</p>
      <button type="button" className="pr-link" onClick={() => setShown(null)}>收起</button>
    </div>}
  </section>;
}

function DataTab({ run, place }) {
  const all = layoutTables(run);
  const tables = all.filter((t) => t.name === (place || all[0]?.name));
  const bridges = bridgeLines(run);
  const split = new Set(all.map((t) => t.group)).size > 1;
  return <>
    {split && <section className="pr-card os-bridge">
      <h2>有几张表没连上</h2>
      <p className="pr-muted">{bridges.length ? "按取值，这些列能把它们连起来：" : "按取值也找不到能连起来的列。"}</p>
      {bridges.length > 0 && <ul className="os-list">{bridges.map((l) => <li key={l}>{l}</li>)}</ul>}
      {bridges.length > 0 && <Hint>这只说明取值对得上，是不是同一个东西由你判断。是的话，重新上传时在建模目的里写上这两列是同一个编号，模型会按它建关系；代码照样会核验。</Hint>}
    </section>}
    {tables.map((t) => <section key={t.name} className="pr-card os-table-card">
      <div className="pr-card-head"><h2>{t.name}</h2><span className="os-stats"><b>{t.rows.toLocaleString("zh-CN")}</b> 行<b>{t.fields ? t.fields.length : t.fieldCount}</b> 列{split && <em className="os-group">第 {t.group + 1} 组</em>}</span></div>
      {t.fields && <div className="os-type-mix">{typeMix(t.fields).map(([type, n]) => <span key={type}><TypeChip type={type === "全空" ? null : type} />× {n}</span>)}</div>}
      {t.skipped.length > 0 && <p className="pr-muted" title="表头上方的标题行，读表时跳过了">跳过：{t.skipped.join("；")}</p>}
      {t.fields ? <div className="os-table-scroll"><table className="os-fields">
        <thead><tr><th scope="col">字段</th><th scope="col">类型</th><th scope="col">最长</th><th scope="col" title="有值的行占多少">填充</th></tr></thead>
        <tbody>{t.fields.map((f) => <tr key={f.path}><td>{f.path}</td><td><TypeChip type={f.type} /></td><td>{f.length || "—"}</td><td><FillBar field={f} rows={t.rows} /></td></tr>)}</tbody>
      </table></div> : <p className="pr-muted">这次运行没有逐列记录，重新上传可看到。</p>}
    </section>)}
  </>;
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

function ReferenceSection({ run, canCompare, onCompare, busy, error, onUpload, onGoConfirm }) {
  const ref = run.evaluation.reference;
  const own = ref?.confirmed && run.confirmation ? splitExtras(run.ontology, run.confirmation.decisions, ref.diff) : null;
  return <section className="pr-card">
    <div className="pr-card-head"><h2>{ref?.confirmed ? "对照你确认过的本体" : "对照标准答案"}</h2>{ref && <span className="pr-muted">{referenceCounts(ref.diff)}</span>}</div>
    <Hint>标准答案有两种来源：在"本体管理"里逐项确认（最常用，确认后自动对照，同一份文件以后再上传也会自动对照）；或者上传一份人写的参考本体（JSON：对象的 label，最好带来自哪张表、按哪个字段识别；关系写两端的对象）。代码按"读同一张表、用同样的识别字段"来对应对象，名字不同也能对上；关系两端都对上才算命中。</Hint>
    {onGoConfirm && <button type="button" className="pr-link os-go-confirm" onClick={onGoConfirm}>去逐项确认本体 →</button>}
    {canCompare && <div className="os-upload">
      <input id="os-reference" className="sr-only" type="file" accept=".json,application/json" disabled={!canCompare || busy}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onCompare(f); e.target.value = ""; }} />
      <label htmlFor="os-reference" className="os-pick">{busy ? "比对中…" : "选择参考本体（.json）"}</label>
      <p className="pr-muted">示例公司的参考本体：<a href="/samples/demo_reference_ontology.json" download>下载 demo_reference_ontology.json</a></p>
    </div>}
    {!canCompare && <CannotAsk what="和自己的参考本体比" example={!run.saved_as} onUpload={onUpload} />}
    {error && <p role="alert" className="pr-error">{error}</p>}
    {ref && <>
      <p className="pr-muted">参考本体：{ref.name}{ref.confirmed && ref.confirmed_at ? `（${localTime(ref.confirmed_at)} 保存）` : ""}</p>
      <DiffList title={ref.confirmed ? "你补上、本体里没有的对象" : "参考里有、本体里没有的对象"} items={ref.diff.types.only_reference} />
      {own ? <>
        <DiffList title="你判为不对的对象" items={own.types.wrong} />
        <DiffList title="还没判断的对象" items={own.types.unjudged} />
      </> : <DiffList title={ref.confirmed ? "这次有、你上次确认里没有的对象" : "本体里多出来的对象"} items={ref.diff.types.only_ours} />}
      <DiffList title={ref.confirmed ? "你判为对的对象" : "对上的对象"} items={ref.diff.types.matched} />
      <DiffList title={ref.confirmed ? "你确认过、这次本体里没有的关系" : "参考里有、本体里没有的关系"} items={ref.diff.relations.only_reference} />
      {own ? <>
        <DiffList title="你判为不对的关系" items={own.relations.wrong} />
        <DiffList title="还没判断的关系" items={own.relations.unjudged} />
      </> : <DiffList title={ref.confirmed ? "这次有、你上次确认里没有的关系" : "本体里多出来的关系"} items={ref.diff.relations.only_ours} />}
    </>}
  </section>;
}

function ConfirmCard({ run, confirm }) {
  const [name, setName] = useState("");
  const [signer, setSigner] = useState(run.confirmation?.confirmed_by || "");
  const { ontology } = run;
  const { decisions, canSave, saving, error } = confirm;
  const others = otherRunTypes(run, decisions);
  const progress = confirmProgress(ontology, decisions);
  const saved = run.confirmation;
  const add = () => { confirm.onAdd(name); setName(""); };
  function downloadReference() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(referenceDownload(run), null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `${run.file.name.replace(/\.[^.]+$/, "")}-参考本体.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="os-board" id="os-confirm" aria-label="逐项确认">
    <div className="os-board-top pr-card">
      <div className="os-board-progress">
        <div className="os-progress-bar" role="img" aria-label={`判对 ${progress.ok}，判错 ${progress.wrong}，没判 ${progress.total - progress.judged}`}>
          <i className="is-ok" style={{ flex: progress.ok }} /><i className="is-wrong" style={{ flex: progress.wrong }} /><i style={{ flex: progress.total - progress.judged }} /></div>
        <p className="os-progress-legend"><span className="is-ok">判对 {progress.ok}</span><span className="is-wrong">判错 {progress.wrong}</span><span>没判 {progress.total - progress.judged}</span>{progress.added > 0 && <span className="is-added">补了 {progress.added}</span>}
          {run.evaluation.reference?.suggested && !saved && <em className="os-chip-note">已按上次确认预填</em>}</p>
      </div>
      <div className="os-board-save">
        <label htmlFor="os-signer" className="sr-only">确认人</label>
        <input id="os-signer" value={signer} maxLength={40} placeholder="确认人（可选）" onChange={(e) => setSigner(e.target.value)} />
        <button type="button" className="pr-primary" disabled={!canSave || saving || !(progress.ok || progress.added)} onClick={() => confirm.onSave(signer)}
          title={!canSave ? (run.saved_as ? "本机建模服务没有连上" : "示例结果不能保存") : !(progress.ok || progress.added) ? '至少判一个"对"，或补一个对象' : "存成这个文件的参考本体，并马上对照"}>{saving ? "保存中…" : saved ? "更新确认" : "保存确认"}</button>
      </div>
    </div>
    <p className="pr-muted">判"对"的意思是业务上成立，不等于建模目的已能回答。</p>
    {error && <p role="alert" className="pr-error">{error}</p>}
    {purposeNote(run) && !saved && <p role="status" className="pr-note os-tone-warn">{purposeNote(run)}</p>}
    <div className="os-board-grid">
      <div className="pr-card os-board-table">
        <div className="os-table-scroll"><table className="os-fields">
          <thead><tr><th scope="col">对象</th><th scope="col">判断</th></tr></thead>
          <tbody>{ontology.object_types.map((t) => <tr key={t.key}><td>{t.label || t.key}</td><td><Verdict confirm={confirm} kind="types" item={t} /></td></tr>)}</tbody>
        </table></div>
        {ontology.relations.length > 0 && <div className="os-table-scroll"><table className="os-fields">
          <thead><tr><th scope="col">关系</th><th scope="col">判断</th></tr></thead>
          <tbody>{ontology.relations.map((r) => <tr key={r.key}><td>{typeLabel(ontology, r.from)} {r.label || "→"} {typeLabel(ontology, r.to)}</td><td><Verdict confirm={confirm} kind="relations" item={r} /></td></tr>)}</tbody>
        </table></div>}
      </div>
      <aside className="os-board-side">
        <div className="pr-card"><h3>补漏掉的对象</h3>
          <div className="os-ask-row"><input id="os-add-type" aria-label="漏掉的对象" value={name} maxLength={40} placeholder="例如：售后工程师" onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") add(); }} />
            <button type="button" className="pr-link" disabled={!name.trim()} onClick={add}>补上</button></div>
          {decisions.added.length > 0 && <div className="os-chips os-suggest">{decisions.added.map((label) => <button key={label} type="button" onClick={() => confirm.onRemoveAdded(label)} aria-label={`去掉补充的对象 ${label}`}>{label} ✕</button>)}</div>}
          {others.length > 0 && <><h3 title="模型别的几次建模里有、这次没有">别的几次还有</h3>
            <div className="os-chips os-suggest">{others.map((t) => <button key={t.label} type="button" onClick={() => confirm.onAdd(t.label)}>＋ {t.label} <small>{t.count}/{t.runs}</small></button>)}</div></>}
        </div>
        {saved && <div className="pr-card"><h3>已保存</h3><p className="pr-muted">{localTime(saved.confirmed_at)}{saved.confirmed_by ? ` · ${saved.confirmed_by}` : ""}</p>
          <button type="button" className="pr-link" disabled={saving} onClick={downloadReference}>下载为参考本体</button></div>}
        <Hint>前面的检查只能说明本体和数据对得上，说明不了它在业务上对不对，这要懂业务的人判断。判好保存后，这份判断就是这个文件的参考本体：马上对照一次，同一份文件以后再上传会自动对照，并带上这次的判断。没判断的项不算进参考本体。{memoryNote(run) ? ` ${memoryNote(run)}` : ""}</Hint>
      </aside>
    </div>
  </section>;
}

const VIEWS = [["graph", "关系图"], ["instances", "实例图谱"], ["relations", "关系列表"]];   // DIP's 本体关系 page; objects have their own pages under 本体管理

function RelationsView({ run, confirm, suggestions = [] }) {
  const { ontology } = run;
  const cards = Object.fromEntries((formOf(run)?.relations || []).map((r) => [r.key, r]));
  if (!ontology.relations.length && !suggestions.length) return <p className="pr-muted">没有关系。</p>;
  return <div className="os-list-view">
    {suggestions.length > 0 && <div className="os-suggest-list"><h3>代码建议 <small>{suggestions.length}</small></h3>
      <ul>{suggestions.map((x, i) => <li key={i}><em className="os-chip-note">建议</em><b>{typeLabel(ontology, x.from)} — {typeLabel(ontology, x.to)}</b>
        <span className="pr-muted" title={{ same_row: "两者出现在同一张表的同一行，本体里却没把它们连起来", alternate_key: `这一列写的是${typeLabel(ontology, x.to)}的名称（对上「${x.key?.field}」），指向的不是本行已经连着的那个`, pointer: "这一列按名字和取值都指向对方的编号" }[x.kind]}>{x.via.source} ·「{x.via.field}」· {x.linked.toLocaleString("zh-CN")} / {(x.filled ?? x.rows).toLocaleString("zh-CN")} 行{x.loose ? " · 编号写法有差别" : ""}</span></li>)}</ul></div>}
    <div className="pr-table-wrap"><table className="pr-table os-form-table">
    <thead><tr><th>关系</th><th>对应关系</th><th>含义</th><th>来自表</th></tr></thead>
    <tbody>{ontology.relations.map((r) => { const c = cards[r.key]; return <tr key={r.key}>
      <td><b>{typeLabel(ontology, r.from)} {r.label || "→"} {typeLabel(ontology, r.to)}</b><Verdict confirm={confirm} kind="relations" item={r} /></td>
      <td>{c ? <><b>{cardinalityLabel(c)}</b><br /><small className="pr-muted">{cardinalityLine(ontology, c)}</small></> : "—"}</td>
      <td>{r.meaning}</td><td><code>{r.source}</code></td>
    </tr>; })}</tbody>
  </table></div></div>;
}

function GraphSection({ run, view, setView, graphProps, confirm, suggestions }) {
  const doc = isDocument(run);
  const attempts = attemptSummary(run.ontology);
  return <section className="pr-card">
      <div className="pr-card-head"><div className="os-head-title"><h2>本体关系</h2><span className={`pr-status ${attempts.passed ? "pr-status-ok" : "pr-status-wait"}`}>{doc ? (attempts.passed ? "每一项都有原文引用" : "没有提取出可核实的概念") : attempts.passed ? "本体结构已通过核验" : "本体结构未通过核验"}</span></div>
        <div className="og-toggle" role="group" aria-label="显示方式">{VIEWS.filter(([key]) => !(doc && key === "instances")).map(([key, text]) => <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}>{text}</button>)}</div></div>
      {view === "graph" && <OntologyGraph run={run} {...graphProps} confirm={confirm} onAsk={doc ? null : graphProps.onAsk} suggestions={suggestions} />}
      {view === "instances" && !doc && <InstanceGraph run={run} />}
      {view === "relations" && <RelationsView run={run} confirm={confirm} suggestions={suggestions} />}
    </section>;
}

function ObjectsPlace({ run, confirm, place }) {
  const { ontology } = run;
  const doc = isDocument(run);
  const attempts = attemptSummary(ontology);
  const retries = attempts.attempts - 1;
  return <>
    {place === "confirm" && <ConfirmCard run={run} confirm={confirm} />}
    {place === "version" && run.version && <section className="pr-card os-version">
      <div className="pr-card-head"><h2>新版本</h2><span className="pr-muted">对比 {localTime(run.version.previous_started_at)} 那一版</span></div>
      <ul className="os-version-list">{versionRows(run.version).map((o) => <li key={o.type} className={o.changed ? "is-changed" : ""}>
        <b>{o.label}</b>
        <span className="os-version-bars" aria-label={`之前 ${o.before}，现在 ${o.after}`}><i className="is-before" style={{ width: `${(o.before / o.scale) * 100}%` }} /><i className="is-after" style={{ width: `${(o.after / o.scale) * 100}%` }} /></span>
        <span className="os-version-count">{o.before.toLocaleString("zh-CN")} → {o.after.toLocaleString("zh-CN")}</span>
        <span className="os-version-delta">{o.added > 0 && <em className="is-added" title={o.added_examples.join("、")}>＋{o.added}</em>}{o.removed > 0 && <em className="is-removed" title={o.removed_examples.join("、")}>－{o.removed}</em>}{o.identity_changed && <em className="is-shift" title={`之前按 ${o.identity_changed.before.join(" + ")}，现在按 ${o.identity_changed.after.join(" + ")}：不能逐个对比`}>识别方式变了</em>}{!o.changed && !o.identity_changed && <em>=</em>}</span>
        {o.changed && !o.identity_changed && <span className="os-version-examples">{[...o.added_examples.map((x) => ["+", x]), ...o.removed_examples.map((x) => ["−", x])].map(([k, x]) => <code key={k + x} className={k === "+" ? "is-added" : "is-removed"}>{k} {x}</code>)}</span>}
      </li>)}</ul>
    </section>}
    {place === "stability" && run.evaluation.stability && <section className="pr-card" id="os-stability">
      <div className="pr-card-head"><h2>建了 {run.evaluation.stability.runs + run.evaluation.stability.failed} 次，哪些每次都有</h2><span className="pr-muted">● 这一次有 ○ 这一次没有</span></div>
      <Hint>模型每次搭的本体会有出入（这是模型的搭法不同，不是数据变了），所以这次上传同时建了几次，代码把它们对齐后数每个对象、每条关系出现了几次。每次都有的可以放心用；不是每次都有的，是模型拿不准的地方，图上画成虚线框，要不要按你的业务决定。</Hint>
      {run.evaluation.stability.failed > 0 && <p className="pr-muted os-tone-warn">{consensusLines(ontology, run.evaluation.stability, ERROR_LABELS)[0]}</p>}
      <ul className="os-dots">{stabilityRows(ontology, run.evaluation.stability).map((r) => <li key={`${r.kind}-${r.label}`} className={r.present < r.runs ? "is-shaky" : ""}>
        <span className="os-dots-marks" aria-label={`${r.runs} 次里 ${r.present} 次有`}>{Array.from({ length: r.runs }, (_, i) => <i key={i} className={i < r.present ? "is-on" : ""} />)}</span>
        <span>{r.label}</span><small>{r.kind}{r.here ? "" : " · 这次没有"}</small></li>)}</ul>
    </section>}
    {place === "history" && run.previous && <section className="pr-card">
      <div className="pr-card-head"><h2>和上一次比</h2><span className={`os-diff-count${stabilityLines(run.previous.diff).length ? " is-changed" : ""}`}>{stabilityLines(run.previous.diff).length ? `${stabilityLines(run.previous.diff).length} 处不同` : "完全一致"}</span></div>
      <p className="pr-muted">{previousLine(run.previous)}{run.previous.purpose && run.previous.purpose !== run.purpose ? " · 两次目的不同" : ""}</p>
      {stabilityLines(run.previous.diff).length > 0 && <ul className="os-list">{stabilityLines(run.previous.diff).map((l) => <li key={l}>{l}</li>)}</ul>}
    </section>}
    {place === "build" && (ontology.data_gaps.length > 0 || ontology.ignored_fields.length > 0) && <section className="pr-card">
      <h2>模型指出的数据缺口（{ontology.data_gaps.length}）</h2>
      {ontology.data_gaps.length > 0 && <ul className="os-list">{ontology.data_gaps.map((g) => <li key={g}>{g}</li>)}</ul>}
      {ontology.ignored_fields.length > 0 && <details><summary>标为不用的字段（{ontology.ignored_fields.length}）</summary><ul>{ontology.ignored_fields.map((f) => <li key={`${f.source}.${f.path}`}>{f.source}.{f.path}：{f.reason}</li>)}</ul></details>}
    </section>}
    {place === "build" && <section className="pr-card os-build-card">
      <h2>这次是怎么建出来的</h2>
      <p className="pr-muted">{sourceLine(run)}{doc ? ` · 被剔除 ${ontology.rejected.length} 项` : attempts.passed ? ` · ${retries ? `模型改了 ${retries} 次后通过核验（${retries > 1 ? "前几版" : "第 1 版"}：${attempts.rejected.map(([code]) => ERROR_LABELS[code] || code).join("、")}）` : "第一版就通过核验"}` : ""}</p>
      {run.sources.some((s) => s.skipped_rows) && <p className="pr-muted">表头上方的标题行已跳过：{run.sources.filter((s) => s.skipped_rows).map((s) => `${s.name}（${s.skipped_rows.join("；")}）`).join("、")}</p>}
      <div className="os-how">
        {!doc && <p>"结构已通过核验"只说明本体里的字段、识别字段和关系都能在数据里对上；数据本身干不干净看"数据体检"。</p>}
        {doc ? <p>文档分 {ontology.chunks_processed} 段交给模型{ontology.chunks_total > ontology.chunks_processed ? `（共 ${ontology.chunks_total} 段，文档太长，后面的没有处理）` : ""}；被剔除的项是引用在原文里找不到，或两端不是已核实的概念。</p>
          : attempts.rejected.length > 0 && <p>前面被代码退回的原因：{attempts.rejected.map(([code, n]) => `${ERROR_LABELS[code] || code} ${n} 处`).join("、")}。</p>}
        <p>模型 {ontology.model}，提示词 {ontology.prompt_version}。建模目的会作为提示的一部分交给模型。</p>
        {doc && ontology.rejected.length > 0 && <ul>{ontology.rejected.map((r, i) => <li key={i}>{r.item}：{r.reason}</li>)}</ul>}
      </div>
    </section>}
  </>;
}

function Checks({ fit, title, note }) {
  const summary = checkSummary(fit);
  return <section className="pr-card">
    <div className="pr-card-head"><h2>{title}</h2><span className="pr-muted">通过 {summary.passed} / {summary.total} 项</span></div>
    <ul className="os-check-grid">{fit.checks.map((c) => <li key={c.key} className={c.passed ? "is-pass" : "is-fail"}>
      <span className="os-check-mark" aria-hidden="true">{c.passed ? "✓" : "✕"}</span><span className="sr-only">{c.passed ? "通过：" : "不通过："}</span>{CHECK_LABELS[c.key] || c.key}</li>)}</ul>
    <Hint><p>{note}</p><p>{COVERAGE_NOTE}</p></Hint>
  </section>;
}

function DataFit({ run, onShow, variants }) {
  const fit = run.evaluation.data_fit;
  const { ontology } = run;
  if (!fit) return <section className="pr-card"><p className="pr-error">本体没有通过核验，无法评测。先看"本体管理"底部"这次是怎么建出来的"里被退回的原因。</p></section>;
  return <>
    <Checks fit={fit} title="数据体检：本体和数据对得上吗" note="全部由代码拿上传的每一行计算，不经过模型。每个问题都可以点“在图上看”，回到关系图里对应的对象。" />
    {fit.identity_conflicts.length > 0 && <Conflicts fit={fit} ontology={ontology} onShow={onShow} />}
    {fit.identity_spellings?.length > 0 && <Spellings fit={fit} ontology={ontology} onShow={onShow} />}
    {variants?.decisions && <Variants run={run} variants={variants} onShow={onShow} />}
    {fit.id_only?.length > 0 && <section className="pr-card">
      <h2>只有编号、没有描述它的表（{fit.id_only.length}）</h2>
      <Hint>这些对象是从别的表里的一列编号认出来的，这份数据里没有任何一张表在说它们是什么。它们能用来分组统计，但图上它们和有明细表的对象长得一样，讲给客户之前要说清楚：现在只有编号。</Hint>
      <ul className="pr-rows">{fit.id_only.map((t) => <li key={t.type}><b>{typeLabel(ontology, t.type)}：{t.count} 个编号</b><span>来自“{t.source}”的“{t.field}”</span><ShowOnGraph type={t.type} onShow={onShow} /></li>)}</ul>
    </section>}
    {fit.identity_risks?.length > 0 && <section className="pr-card">
      <h2>识别字段可能不稳（{fit.identity_risks.length}）</h2>
      <p className="pr-muted">这是提示，不是不通过：代码只看了识别字段的名字像不像"名称"一类会被改写的字段。</p>
      <ul className="pr-rows">{fit.identity_risks.map((r) => <li key={r.type}><b>{typeLabel(ontology, r.type)}：按 {r.fields.join("、")} 识别</b><span>{r.reason}</span><ShowOnGraph type={r.type} onShow={onShow} /></li>)}</ul>
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
  if (!fit) return <section className="pr-card"><p className="pr-error">没有提取出可核实的概念，无法评测。先看"本体管理"底部"这次是怎么建出来的"里被剔除的原因。</p></section>;
  const keyOf = (label) => run.ontology.object_types.find((t) => t.label === label)?.key;
  return <>
    <Checks fit={fit} title="文档检查：每一项都能回到原文吗" note={`由代码逐项核对模型给的引用是否真在原文里，不经过模型。模型共提出 ${fit.proposed} 项，保留 ${fit.kept} 项，剔除 ${fit.rejected} 项。${fit.cut ? "文档太长，只处理了前面的部分。" : ""}`} />
    {fit.isolated.length > 0 && <section className="pr-card"><h2>没有任何关系的概念（{fit.isolated.length}）</h2>
      <div className="os-chips os-suggest">{fit.isolated.map((label) => <button key={label} type="button" onClick={() => onShow(keyOf(label))}>{label}</button>)}</div></section>}
  </>;
}

const CHECK_VIEWS = [["fit", "数据体检"], ["rules", "规则"], ["ref", "对照标准"]];

function CheckSection({ run, evalView, setEvalView, questions, variants, onShow, rules }) {
  const doc = isDocument(run);
  const tiles = { ...Object.fromEntries(overviewTiles(run).map((t) => [t.key, t])), rules: rulesTile(run.evaluation.rules) || { value: "", tone: "muted" } };
  const view = ["ref", "rules"].includes(evalView) && !(doc && evalView === "rules") ? evalView : "fit";
  return <>
    <div className="os-segments" role="tablist" aria-label="数据体检">{CHECK_VIEWS.filter(([key]) => !(doc && key === "rules")).map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={view === key} onClick={() => setEvalView(key)}>
      <b>{key === "fit" && doc ? "文档检查" : label}</b><small className={`os-tone-${tiles[key].tone}`}>{tiles[key].value}</small></button>)}</div>
    {view === "rules" && <RulesView run={run} {...rules} />}
    {view === "fit" && (doc ? <DocumentFitView run={run} onShow={onShow} /> : <DataFit run={run} onShow={onShow} variants={variants} />)}
    {view === "ref" && <ReferenceSection run={run} canCompare={questions.canAsk} onCompare={questions.onCompare} busy={questions.comparing} error={questions.compareError} onUpload={questions.onUpload} onGoConfirm={questions.onGoConfirm} />}
  </>;
}

function QaSection({ run, questions, onPath, askRef, place }) {
  const [adding, setAdding] = useState(null);   // the answered question being fixed, with the note being written
  const onAccept = (item) => { setAdding({ item, note: "" }); setTimeout(() => document.getElementById("os-note")?.focus(), 50); };
  return <>
    {place === "ask" && <AskBar run={run} canAsk={questions.canAsk} busy={questions.busy} error={questions.error} onAsk={questions.onAsk} askRef={askRef} onPath={onPath} />}
    {(place === "acceptance" || adding) && <AcceptanceSection run={run} acceptance={run.evaluation.acceptance} onSave={questions.onAccept} onPath={onPath}
      busy={questions.accepting} error={questions.acceptError} adding={adding} setAdding={setAdding} />}
    {place !== "acceptance" && <QuestionsSection run={run} {...questions} onPath={onPath} onAccept={onAccept} part={place === "ask" ? "mine" : "model"} />}
  </>;
}

export function OntologyStudio({ request = null, runs = null, section = null, nav = 0, onSection = () => {}, onRunsChanged = () => {}, onCurrent = () => {} } = {}) {
  const [run, setRun] = useState(() => loadLocal());
  const tab = section || (run ? "objects" : "upload");
  const setTab = onSection;
  const [objectKey, setObjectKey] = useState(null);   // the object whose own page is open under 本体管理
  const [objPlace, setObjPlace] = useState("objects");   // which of 本体管理's places is shown
  const [qaPlace, setQaPlace] = useState("ask");
  const [dataPlace, setDataPlace] = useState(null);   // which uploaded table 数据接入 shows
  const [savingRules, setSavingRules] = useState(false);
  const [rulesError, setRulesError] = useState("");
  const [suggestions, setSuggestions] = useState([]);   // relations code sees in the data and the ontology lacks
  useEffect(() => {
    setSuggestions([]);
    if (!run?.saved_as || isDocument(run) || run.ontology.status !== "auto_built_verified") return;
    fetch(`/api/ontology/runs/${run.saved_as}/suggestions`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : { suggestions: [] }))
      .then((b) => setSuggestions(b.suggestions || []), () => setSuggestions([]));   // suggestions are extra: without them the page still works
  }, [run?.saved_as]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setObjectKey(null); }, [nav]);
  useEffect(() => { if (!section) onSection(tab); }, []);   // eslint-disable-line react-hooks/exhaustive-deps -- tell the sidebar where the studio opened
  const [health, setHealth] = useState("checking");
  const [stale, setStale] = useState("");
  const [busy, setBusy] = useState(false);
  const [events, setEvents] = useState([]);
  const [elapsed, setElapsed] = useState(0);
  const [lost, setLost] = useState(false);
  const [error, setError] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState("");
  const [comparing, setComparing] = useState(false);
  const [finding, setFinding] = useState(false);
  const [findError, setFindError] = useState("");
  const [accepting, setAccepting] = useState(false);
  const [acceptError, setAcceptError] = useState("");
  const [compareError, setCompareError] = useState("");
  const [view, setView] = useState("graph");
  const [decisions, setDecisions] = useState(() => (run ? decisionsOf(run) : null));
  const [storageWarning, setStorageWarning] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmError, setConfirmError] = useState("");
  const [evalView, setEvalView] = useState("fit");
  const [selected, setSelected] = useState(null);
  const [path, setPath] = useState(null);
  const [reveal, setReveal] = useState(0);
  const following = useRef(null);
  const askRef = useRef(null);

  useEffect(() => {   // asked again whenever the window comes back, so edits made meanwhile are caught before the next run
    const check = () => fetch("/api/ontology/health", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((h) => { setHealth(h.model_ready ? "ready" : "no-key"); setStale(staleNote(h)); }).catch(() => { setHealth("offline"); setStale(""); });
    check();
    window.addEventListener("focus", check);
    return () => window.removeEventListener("focus", check);
  }, []);

  const keep = (valid) => setStorageWarning(saveResult(storage(), valid));
  function show(result) { const valid = validateRun(result); setRun(valid); keep(valid); setDecisions(decisionsOf(valid)); setConfirmError(""); setSelected(null); setPath(null); setEvalView("fit"); setObjectKey(null); setObjPlace("objects"); setQaPlace("ask"); setDataPlace(null); setTab("objects"); onCurrent(valid); onRunsChanged(); }
  function update(result) { const valid = validateRun(result); setRun(valid); keep(valid); onRunsChanged(); }
  useEffect(() => { onCurrent(run && tab !== "upload" ? run : null); }, [run, tab]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {   // the sidebar asked for new work, or for a run kept on this machine
    if (!request) return;
    if (request.kind === "new") { setError(""); setTab("upload"); return; }
    setError("");
    fetch(`/api/ontology/runs/${request.saved_as}`, { cache: "no-store" })
      .then(async (r) => { const body = await r.json().catch(() => ({})); if (!r.ok) throw new Error(serviceError(r.status, body)); show(body); })
      .catch((e) => { setError(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message); setTab("upload"); });
  }, [request?.nonce]);   // eslint-disable-line react-hooks/exhaustive-deps
  async function build(files, purpose, previous = null) {
    setBusy(true); setError(""); setEvents([]);
    let jobId;
    try {
      const contents = [];
      for (const file of files) contents.push(await toBase64(file));
      const body = JSON.stringify({ ...uploadPayload(files, purpose, ...contents), ...(previous ? { previous } : {}) });
      const response = await fetch("/api/ontology/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body });
      const data = await response.json().catch(() => ({ error: `服务返回 ${response.status}` }));
      if (!response.ok) throw new Error(serviceError(response.status, data));
      jobId = data.job_id;
      pendingJob.set(jobId);
    } catch (e) { setError(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message); setBusy(false); return; }
    follow(jobId, Date.now());
  }
  async function follow(jobId, started) {
    if (following.current === jobId) return;   // already being followed (React may run the mount effect twice)
    following.current = jobId;
    setBusy(true); setTab("upload");
    const tick = () => setElapsed(Math.max(0, Math.round((Date.now() - started) / 1000)));   // once a poll, about once a second
    tick();
    try {
      for (;;) {
        const poll = await fetch(`/api/ontology/jobs/${jobId}`, { cache: "no-store" }).catch(() => null);
        const job = poll && await poll.json().catch(() => null);
        // no answer, or a proxy's error page instead of the service's JSON: the service is down, perhaps restarting
        setLost(!job);
        if (!job) { tick(); await new Promise((r) => setTimeout(r, 1000)); continue; }
        if (!poll.ok) throw new Error(poll.status === 404 ? "找不到这次建模任务，请重新上传文件。" : serviceError(poll.status, job));
        setEvents(job.events || []);
        started = jobStartedAt(job.events || [], started);
        tick();
        const outcome = jobOutcome(job);
        if (outcome?.result) { show(outcome.result); break; }
        if (outcome) throw new Error(outcome.error);
        await new Promise((r) => setTimeout(r, 1000));
      }
    } catch (e) { setError(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message); }
    finally { following.current = null; pendingJob.set(null); setLost(false); setBusy(false); }
  }
  useEffect(() => { const id = pendingJob.get(); if (id) follow(id, Date.now()); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
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
  function askOntology() { setQaPlace("ask"); setTab("qa"); setTimeout(() => askRef.current?.focus(), 50); }
  const goConfirm = () => { setObjectKey(null); setObjPlace("confirm"); setTab("objects"); };
  function showOnGraph(type) { if (!type) return; setPath(null); setSelected({ kind: "node", key: type }); setView("graph"); setTab("graph"); setReveal((n) => n + 1); }
  function showPath(query, text) { const p = pathOf(run.ontology, query); if (!p) return; setPath({ ...p, text }); setSelected({ kind: "node", key: p.nodes[p.nodes.length - 1] }); setView("graph"); setTab("graph"); setReveal((n) => n + 1); }
  function openTile(key) {
    if (key === "ref" && !run.evaluation.reference) { goConfirm(); return; }
    if (key === "fit" || key === "ref") setEvalView(key);
    if (key === "ontology" || key === "stability") { setObjectKey(null); setObjPlace(key === "stability" ? "stability" : "objects"); }
    if (key === "qa") setQaPlace("model");
    setTab(sectionOfTile(key));
  }
  function demo(url = DEMO_URL) { setError(""); readText(url).then(show).catch((e) => setError(`示例读取失败：${e.message}`)); }
  const confirmProps = run && decisions && {
    decisions, saving, error: confirmError, canSave: Boolean(run.saved_as) && health === "ready",
    onVerdict: (kind, key, verdict) => setDecisions((d) => setVerdict(run.ontology, d, kind, key, verdict)),
    onRename: (key, label) => setDecisions((d) => renameType(d, key, label)),
    onAdd: (label) => setDecisions((d) => addType(run.ontology, d, label)),
    onRemoveAdded: (label) => setDecisions((d) => removeAdded(d, label)),
    onSave: (signer) => post("/api/ontology/confirm", { saved_as: run.saved_as, decisions, ...(signer.trim() ? { confirmed_by: signer.trim() } : {}) }, setSaving, setConfirmError),
  };
  const variantProps = run && decisions && {
    decisions, busy: finding, error: findError, canFind: Boolean(run.saved_as) && health === "ready",
    onFind: () => post("/api/ontology/variants", { saved_as: run.saved_as }, setFinding, setFindError),
    onToggle: (group) => setDecisions((d) => toggleVariant(d, group)),
  };
  function save(content, type, suffix) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${run.file.name.replace(/\.[^.]+$/, "").slice(0, 60)}-${suffix}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const download = () => save(JSON.stringify(run, null, 2), "application/json", "本体和评测.json");
  const downloadSummary = () => save(summaryMarkdown(run), "text/markdown;charset=utf-8", "纪要.md");

  const open = run && tab !== "upload";
  const questions = { canAsk: Boolean(run?.saved_as) && health === "ready", busy: asking, error: askError, onAsk: ask, onCompare: compare, comparing, compareError, onUpload: () => setTab("upload"),
    onAccept: (items) => post("/api/ontology/acceptance", { saved_as: run.saved_as, items }, setAccepting, setAcceptError), accepting, acceptError, onGoConfirm: goConfirm };
  const inDetail = tab === "objects" && objectKey;
  const placeOf = (items, key) => items.find(([k]) => k === key)?.[1];
  const crumb = !run ? [] : [sectionsFor(run).find(([k]) => k === tab)?.[1] || "",
    tab === "objects" ? placeOf(objectsNav(run, decisions), objPlace) : tab === "qa" ? placeOf(qaNav(run), qaPlace)
      : tab === "data" ? (dataPlace || run.sources[0]?.name) : tab === "graph" ? placeOf(VIEWS, view) : tab === "check" ? ({ ref: "对照标准", rules: "规则" }[evalView] || "体检") : ""].filter(Boolean);
  return <section className={`pr-page${open ? "" : " is-start"}${inDetail ? " is-object" : ""}`} aria-labelledby="os-title">
    {stale && <p role="alert" className="pr-note os-stale">{stale}</p>}
    {storageWarning && <p role="alert" className="pr-note os-storage">{storageWarning}</p>}
    {open && !inDetail && <header className="pr-head">
      <div className="os-overview">
        <div className="os-overview-file"><h1 id="os-title" className="os-crumb" title={`${run.file.name}${run.purpose ? `\n${run.purpose}` : ""}`}>{crumb.map((c, i) => <span key={c}>{i > 0 && <i aria-hidden="true">/</i>}{c}</span>)}</h1>
          <button className="os-icon-btn" onClick={downloadSummary} title="下载纪要：一页 Markdown，给会上的人看">⤓ 纪要</button>
          <button className="os-icon-btn" onClick={download} title="下载本体和评测：一个 JSON 文件">⤓ JSON</button></div>
        <div className="os-tiles">{overviewTiles(run).map((t) => <button key={t.key} type="button" className={`os-tile os-tone-${t.tone}`} title={t.hint || undefined} onClick={() => openTile(t.key)}><small>{t.label}</small><b>{t.value}</b></button>)}</div>
      </div>
    </header>}
    {inDetail && <h1 id="os-title" className="sr-only">{folderLabel(run.file.name)}</h1>}
    <div className="pr-panel os-panel">
      {tab === "upload" && <UploadTab runs={runs} health={health} busy={busy} events={events} elapsed={elapsed} lost={lost} error={error} onBuild={build} onDemo={() => demo(DEMO_URL)} onDocDemo={() => demo(DEMO_DOC_URL)} />}
      {tab === "objects" && run && (objectKey
        ? <ObjectDetail run={run} typeKey={objectKey} confirm={confirmProps} onBack={() => setObjectKey(null)} onOpen={setObjectKey} onSaveConfirm={goConfirm} />
        : <SubLayout label="本体管理" items={objectsNav(run, decisions)} active={objPlace} onChange={setObjPlace}>
          {objPlace === "objects" ? <ObjectCards run={run} decisions={decisions} onOpen={setObjectKey} /> : <ObjectsPlace run={run} confirm={confirmProps} place={objPlace} />}
        </SubLayout>)}
      {tab === "graph" && run && <GraphSection run={run} view={view} setView={setView} confirm={confirmProps} suggestions={suggestions}
        graphProps={{ selected, onSelect: (s) => { setSelected(s); setPath(null); }, path, onClearPath: () => setPath(null), onAsk: askOntology, reveal }} />}
      {tab === "data" && run && <SubLayout label="上传的表" items={run.sources.map((t) => [t.name, t.name, t.rows?.toLocaleString("zh-CN") ?? ""])} active={dataPlace || run.sources[0]?.name} onChange={setDataPlace}>
        <DataTab run={run} place={dataPlace} /></SubLayout>}
      {tab === "qa" && run && <SubLayout label="智能问答" items={qaNav(run)} active={qaPlace} onChange={setQaPlace}>
        <QaSection run={run} questions={questions} onPath={showPath} askRef={askRef} place={qaPlace} /></SubLayout>}
      {tab === "check" && run && <CheckSection run={run} evalView={evalView} setEvalView={setEvalView} onShow={showOnGraph} variants={variantProps} questions={questions}
        rules={{ canSave: Boolean(run.saved_as) && health === "ready", busy: savingRules, error: rulesError, onSave: (next) => post("/api/ontology/rules", { saved_as: run.saved_as, ...next }, setSavingRules, setRulesError) }} />}
    </div>
  </section>;
}
