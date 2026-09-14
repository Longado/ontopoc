import { useEffect, useRef, useState } from "react";
import {
  ALIAS_VERDICTS, BUCKETS, DATASET_KEY, FLAG_LABELS, REVIEWER_KEY, INDEX_URL, MARKS, ROLE_LABELS, VERDICT_TO_MARK, aliasDoubts, aliasKey,
  confirmOntology, displayValue, emptyState, exportState, fieldLabel, highlight, markCandidate, markOf, nextSelection, noteCandidate,
  orderCandidates, partExample, readyToConfirm, restoreState, restoreView, sharedModelYears, stepSelection, storageKey, viewKey,
  dateCaveat, earlierDates, keyAction, NOTICE, personalInfo, uncleanNotes, verdictSplit,
  packUrl, pickDataset, summarize, timingLabel, validateIndex, validatePack, visibleCandidates,
} from "./publicReviewModel.js";
import "./PublicRecallReview.css";

const now = () => new Date().toISOString();
const narrow = () => window.matchMedia?.("(max-width: 760px)").matches;
const TRANSFORM_NOTE = { colon_hierarchy: "（按层级拆分）", split_comma: "（逗号分隔多项）" };
const TABS = [["ontology", "口径"], ["recalls", "召回"], ["review", "复核"], ["results", "结果"]];


function Evidence({ text, evidence }) {
  const parts = highlight(text, evidence);
  return parts ? <>{parts[0]}<mark>{parts[1]}</mark>{parts[2]}</> : text;
}

function Badges({ candidate, signal, earlier }) {
  const time = timingLabel(candidate.timing);
  return <span className="pr-badges">
    {time && <span className={`pr-badge pr-badge-${candidate.timing.relation}`}>{time}</span>}
    {earlier.map((path) => <span key={path} className="pr-badge pr-badge-earlier">{fieldLabel(path)}在召回前</span>)}
    {signal.flags.map((f) => <span key={f} className="pr-badge pr-badge-flag">{FLAG_LABELS[f] || f}</span>)}
    {candidate.via_alias && <span className="pr-badge pr-badge-alias">经名称对应</span>}
  </span>;
}

function Field({ label, children }) {
  return <div className="pr-field"><dt>{label}</dt><dd>{children}</dd></div>;
}

function ScopeTab({ pack, state, onAnswer, onConfirm }) {
  const { ontology, source } = pack;
  const [draft, setDraft] = useState({});
  const confirmed = Boolean(state.confirmed_at);
  const checks = confirmed ? state.alias_checks || {} : draft;
  const typeOf = (role) => ontology.object_types.find((t) => t.role === role);
  const label = Object.fromEntries(ontology.object_types.map((t) => [t.key, t.label || t.key]));
  const shared = (role) => ontology.metrics.shared_across_sources[typeOf(role)?.key] || 0;
  const filters = ontology.object_types.flatMap((t) => t.sources.filter((s) => s.where).map((s) => `${label[t.key]}只取${[].concat(s.where).map((w) => `${fieldLabel(w.path)}为“${w.equals}”`).join("且")}的记录`));
  const example = partExample(pack);
  const years = sharedModelYears(pack);
  const eventTime = typeOf("event")?.time_field;
  const signalTime = typeOf("signal")?.time_field;
  const caveat = dateCaveat(pack);
  const answered = ontology.value_aliases.filter((a) => checks[aliasKey(a)]).length;
  const ready = readyToConfirm(pack, checks);
  function answer(a, verdict) {
    if (confirmed) onAnswer(aliasKey(a), verdict);
    else setDraft((d) => ({ ...d, [aliasKey(a)]: verdict }));
  }
  return <>
    <section className="pr-card">
      <h2>开始复核前，核对系统怎么读这份数据</h2>
      <p className="pr-muted">下面是系统从公开数据里自动整理出的口径，每一项都已由代码拿全部记录核验过。前四项看有没有明显不对；名称对应请逐条判断，你的判断随复核一起下载。</p>
      <ul className="pr-checks">
        <li><h3>数据范围</h3>
          <p>{pack.dataset?.label || "本数据集"}，NHTSA 公开数据，{source.retrieved_from.slice(0, 10)} 取数：{source.events} 个召回，{source.record_counts.complaints} 条车主投诉。{filters.map((f) => `${f}。`).join("")}</p>
          {source.cleaning?.filter((c) => c.removed > 0).map((c) => <p key={c.rule} className="pr-muted">取数时去掉 {c.removed} 条投诉，规则：<code>{c.rule}</code></p>)}
        </li>
        <li><h3>召回和投诉怎么对上</h3>
          <p>靠车型年款和部件两样对上：两边都出现的车型年款 {shared("affected_object")} 个{years.length ? `（例如 ${years.slice(0, 3).join("、")}）` : ""}，部件 {shared("mechanism")} 个。</p>
          {ontology.data_gaps.length > 0 && <details><summary>系统自己指出的数据缺口（{ontology.data_gaps.length} 条）</summary><ul>{ontology.data_gaps.map((g) => <li key={g}>{g}</li>)}</ul></details>}
        </li>
        <li><h3>哪些投诉算候选</h3>
          <p>投诉写的部件和召回部件相同，或是召回部件的任意一层上级，就算同部件候选。{example && <>例如召回写 <code>{example.recall}</code>，投诉只写 <code>{example.complaint}</code> 也算，所以这个召回有 {example.candidates} 条候选，多数要靠复核排除。</>}</p>
        </li>
        <li><h3>召回前后怎么算</h3>
          <p>{eventTime && signalTime ? `召回按“${fieldLabel(eventTime.path)}”，投诉按“${fieldLabel(signalTime.path)}”，比较谁先谁后。` : "这份数据没有可比的日期，不标召回前后。"}</p>
          {caveat && <p>投诉另有“{caveat.fields.map(fieldLabel).join("、")}”，没有用来比较先后。按它算，标为召回后的 {caveat.after} 条次候选里有 {caveat.earlier} 条次其实发生在召回之前；复核列表里这些会单独标出。</p>}
        </li>
      </ul>
    </section>
    <section className="pr-card">
      <div className="pr-card-head"><h2>名称对应：需要你判断</h2>{ontology.value_aliases.length > 0 && <span className="pr-muted">已判断 {answered}/{ontology.value_aliases.length}</span>}</div>
      {ontology.value_aliases.length ? <ul className="pr-aliases">{ontology.value_aliases.map((a) => <li key={aliasKey(a)}>
        <p>投诉里的 <code>{a.value}</code>，系统当作召回里的 <code>{a.target_value}</code>，因此多连上 {a.records_linked} 条投诉。它们是同一个部件吗？</p>
        <p className="pr-muted" lang="en">模型的理由：{a.reasoning}</p>
        <div className="pr-marks" role="group" aria-label={`${a.value} 的判断`}>{Object.entries(ALIAS_VERDICTS).map(([key, text]) => <button key={key} type="button" aria-pressed={checks[aliasKey(a)] === key} onClick={() => answer(a, key)}>{text}</button>)}</div>
      </li>)}</ul> : <p className="pr-muted">这份数据没有需要判断的名称对应。</p>}
      {ontology.rejected_aliases.length > 0 && <details><summary>被代码拒绝的对应（{ontology.rejected_aliases.length} 条，没有采用）</summary><ul>{ontology.rejected_aliases.map((a, i) => <li key={i}>“{a.value}” → “{a.target_value}”：{a.reason}</li>)}</ul></details>}
      {confirmed ? <p className="pr-muted">已核对 · {state.confirmed_at.slice(0, 16).replace("T", " ")}（本机记录，不是审批）。判断可以随时改。</p>
        : <><button className="pr-primary" onClick={() => onConfirm(draft)} disabled={!ready}>核对完毕，开始复核</button>
          {!ready && <p className="pr-muted">还有 {ontology.value_aliases.length - answered} 条名称对应没判断。</p>}</>}
    </section>
    <section className="pr-card">
      <details><summary>技术细节：自动搭建的本体（给实施人员看）</summary>
        <h3 className="pr-sub">搭建过程</h3>
        <ul className="pr-rows">{(ontology.attempt_errors || []).map((errors, i) => <li key={i}><b>第 {i + 1} 次提交</b>
          <span>{errors.length ? `被代码退回，${errors.length} 个问题` : `通过全部核验`}</span>
          {errors.length > 0 && <ul className="pr-errors">{errors.map((e, j) => <li key={j}><code>{e.code}</code> {e.message}</li>)}</ul>}</li>)}</ul>
        <h3 className="pr-sub">对象类型</h3>
        <div className="pr-types">{ontology.object_types.map((t) => <article key={t.key} className="pr-type">
          <span className={`pr-tag pr-role-${t.role}`}>{ROLE_LABELS[t.role] || t.role}</span>
          <h3>{t.label || t.key}</h3>
          <p>{t.sources.map((s) => `${s.source}：${s.fields.join(" + ")}${TRANSFORM_NOTE[s.transform] || ""}${s.where ? `，只取 ${[].concat(s.where).map((w) => `${w.path} = ${w.equals}`).join(" 且 ")}` : ""}`).join("；")}</p>
          {t.time_field && <p>时间：{t.time_field.source}.{t.time_field.path}</p>}
          {t.rationale && <small>{t.rationale}</small>}
        </article>)}</div>
        <h3 className="pr-sub">关系</h3>
        <ul className="pr-rows">{ontology.relations.map((r) => <li key={r.key}><b>{label[r.from]} → {label[r.to]}</b><span>{r.meaning}</span><code>{r.source}</code></li>)}</ul>
        <details><summary>未使用的字段（{ontology.ignored_fields.length} 个）</summary><ul>{ontology.ignored_fields.map((f) => <li key={`${f.source}.${f.path}`}>{f.source}.{f.path}：{f.reason}</li>)}</ul></details>
      </details>
    </section>
  </>;
}

const readJson = (url, what) => fetch(url, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(`${what}读取失败（${r.status}）`); return r.json(); });
const remember = (key, value) => { try { localStorage.setItem(key, value); } catch { /* storage unavailable: the choice just is not remembered */ } };
const recallSaved = (key) => { try { return localStorage.getItem(key); } catch { return null; } };

export function PublicRecallReview({ language = "zh" }) {
  const [index, setIndex] = useState(null);
  const [datasetId, setDatasetId] = useState("");
  const [pack, setPack] = useState(null);
  const [state, setState] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [storageNote, setStorageNote] = useState("");
  const [storageBlocked, setStorageBlocked] = useState(false);
  const [tab, setTab] = useState("ontology");
  const [recallId, setRecallId] = useState("");
  const [bucket, setBucket] = useState("outside_all");
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [reviewer, setReviewer] = useState(() => recallSaved(REVIEWER_KEY) || "");
  const [focusTick, setFocusTick] = useState(0);
  const [scrollTick, setScrollTick] = useState(0);
  const detailRef = useRef(null);
  const listRef = useRef(null);

  useEffect(() => {
    let active = true;
    readJson(INDEX_URL, "数据集清单").then((data) => {
      if (!active) return;
      const idx = validateIndex(data);
      setIndex(idx);
      setDatasetId(pickDataset(idx, recallSaved(DATASET_KEY)));
    }).catch((e) => { if (active) setLoadError(e.message); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!index || !datasetId) return undefined;
    let active = true;
    remember(DATASET_KEY, datasetId);
    setPack(null); setState(null); setLoadError(""); setStorageNote(""); setStorageBlocked(false);
    const entry = index.datasets.find((d) => d.id === datasetId);
    readJson(packUrl(entry), `数据集 ${entry.label} `)
      .then((data) => {
        if (!active) return;
        const p = validatePack(data);
        let restored;
        try { restored = restoreState(localStorage.getItem(storageKey(p)), p); }
        catch { restored = emptyState(p); setStorageBlocked(true); setStorageNote("本机已有复核记录无法读取，原记录保留未覆盖；本次复核不会自动保存。"); }
        const view = restoreView(recallSaved(viewKey(p)), p, Boolean(restored.confirmed_at));
        setPack(p); setState(restored);
        setTab(view.tab); setRecallId(view.recallId); setBucket(view.bucket); setSelected(view.selected);
      })
      .catch((e) => { if (active) setLoadError(e.message); });
    return () => { active = false; };
  }, [index, datasetId]);

  useEffect(() => {
    if (!pack || !state || storageBlocked) return;
    try { localStorage.setItem(storageKey(pack), JSON.stringify(state)); setStorageNote("复核随点随存到本机浏览器，刷新可恢复。"); }
    catch { setStorageNote("保存失败：浏览器存储不可用。请用“下载复核结果”保留进度。"); }
  }, [pack, state, storageBlocked]);

  const recall = pack?.recalls.find((r) => r.id === recallId);
  const visible = recall ? orderCandidates(visibleCandidates(recall, bucket), pack.signals) : [];
  const current = nextSelection(selected, visible);
  useEffect(() => { if (current !== selected) setSelected(current); }, [current, selected]);
  useEffect(() => {
    if (pack && recall) remember(viewKey(pack), JSON.stringify({ tab, recallId, bucket, selected: current }));
  }, [pack, recall, tab, recallId, bucket, current]);
  useEffect(() => { if (focusTick) listRef.current?.querySelector('[aria-pressed="true"]')?.focus(); }, [focusTick]);
  const keyRef = useRef(null);
  useEffect(() => {
    if (tab !== "review") return undefined;
    const listener = (e) => keyRef.current?.(e);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [tab]);
  useEffect(() => { if (scrollTick && narrow()) detailRef.current?.scrollIntoView({ block: "start" }); }, [scrollTick]);

  const datasetPicker = index && <label className="pr-dataset" htmlFor="pr-dataset">数据集
    <select id="pr-dataset" value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
      {index.datasets.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
    </select></label>;
  if (loadError || !pack || !state || !recall) {
    return <section className="pr-page"><header className="pr-head"><div className="pr-head-line"><h1 id="pr-title">汽车召回范围研判</h1>{datasetPicker}</div></header>
      <p role={loadError ? "alert" : "status"} className={loadError ? "pr-error" : "pr-muted"}>{loadError ? `${loadError}。可以换一个数据集。` : "读取数据中…"}</p></section>;
  }

  const byId = Object.fromEntries(pack.recalls.map((r) => [r.id, r]));
  const candidate = visible.find((c) => c.id === current);
  const signal = candidate && pack.signals[candidate.id];
  const entry = candidate && markOf(state, recall.series, candidate.id);
  const stats = summarize(pack, state, recall.id);
  const recallText = recall.fields.find((f) => f.path === "Summary")?.value || recall.fields[0]?.value || "";
  const seriesMembers = pack.recalls.filter((r) => r.series === recall.series);
  const reviewedAll = Object.keys(state.marks).length;
  const doubts = aliasDoubts(pack, state);
  const reviewerIssue = personalInfo(reviewer);
  const noteIssues = uncleanNotes(state);

  function apply(change) {
    try { setState((s) => change(s)); setError(""); } catch (e) { setError(e.message); }
  }
  function choose(id) {
    setSelected(id);
    setScrollTick((n) => n + 1);
  }
  keyRef.current = (e) => {
    const action = keyAction(e);
    if (!action || !candidate) return;
    e.preventDefault();
    if (action.step) { setSelected(stepSelection(current, visible, action.step)); setFocusTick((n) => n + 1); }
    else if (state.confirmed_at) apply((s) => markCandidate(s, recall.series, candidate.id, action.mark, now()));
  };
  function openRecall(id) { setRecallId(id); setSelected(""); setTab("review"); }
  function backToList() {
    listRef.current?.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: "center" });
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(exportState(pack, state, now(), reviewer), null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `${datasetId}-review.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className="pr-page" aria-labelledby="pr-title">
    {language === "en" && <p className="pr-note" lang="en">This scenario page is available in Chinese only for now.</p>}
    <header className="pr-head">
      <div className="pr-head-line">
        <h1 id="pr-title">汽车召回范围研判</h1>
        <span className={`pr-status ${state.confirmed_at ? "pr-status-ok" : "pr-status-wait"}`}>{state.confirmed_at ? "口径已核对" : "口径待核对"}</span>
        {datasetPicker}
        <span className="pr-meta">NHTSA · {pack.source.events} 个召回 · {pack.source.record_counts.complaints} 条投诉 · {pack.source.retrieved_from.slice(0, 10)} 取数</span>
      </div>
      <nav className="pr-tabs" role="tablist" aria-label="研判步骤">{TABS.map(([key, label]) => <button key={key} type="button" role="tab" id={`pr-tab-${key}`}
        aria-selected={tab === key} aria-controls="pr-panel" onClick={() => setTab(key)}>{label}{key === "review" && <small>{recall.id}</small>}{key === "results" && reviewedAll > 0 && <small>{reviewedAll}</small>}</button>)}</nav>
    </header>
    <p className="pr-boundary">{pack.boundary} 模型 {pack.run.model}，原文判断提示词 {pack.run.matcher_prompt_version}；初判仅供参考。</p>

    <div id="pr-panel" role="tabpanel" aria-labelledby={`pr-tab-${tab}`} className="pr-panel">
      {tab === "ontology" && <ScopeTab key={pack.ontology.hash} pack={pack} state={state}
        onAnswer={(key, verdict) => apply((s) => confirmOntology(s, s.confirmed_at, { ...s.alias_checks, [key]: verdict }))}
        onConfirm={(checks) => { apply((s) => confirmOntology(s, now(), checks)); setTab("recalls"); }} />}

      {tab === "recalls" && <section className="pr-card">
        <h2>选择一个召回</h2>
        <p className="pr-muted">按部件分组，组内按日期排列。原文写明“修复后再召回”的召回连成一个系列，系列内共用复核结论和模型初判。点一个召回进入复核。</p>
        <div className="pr-groups">{pack.groups.map((g) => <div key={g.id} className="pr-group">
          <h3>{g.id}</h3>
          <div className="pr-recalls">{g.recalls.map((id) => byId[id]).map((r) => <button key={r.id} aria-pressed={r.id === recallId} onClick={() => openRecall(r.id)}>
            <strong>{r.id}<span className="pr-date"> · {r.date}</span></strong>
            {r.references.length > 0 && <span className="pr-chain">接续召回 {r.references.join("、")}</span>}
            <small>覆盖 {r.covered.length} 个车型年款 · 范围外 {r.counts.outside_all} 条{r.text_checked ? `（模型判是 ${verdictSplit(visibleCandidates(r, "outside_all")).yes}）` : " · 没有模型初判"}</small>
          </button>)}</div>
        </div>)}</div>
      </section>}

      {tab === "review" && <div className="pr-panel">
        <section className="pr-card">
          <div className="pr-card-head"><h2>召回 {recall.id}</h2><button type="button" className="pr-link" onClick={() => setTab("recalls")}>换一个召回</button></div>
          <dl className="pr-fields">
            <Field label="报告日期">{recall.date}</Field>
            <Field label="部件">{recall.mechanism.join("、")}</Field>
            <Field label="覆盖车型年款">{recall.covered.join("、") || "无"}</Field>
            {seriesMembers.length > 1 && <Field label="同一系列">{seriesMembers.map((r) => `${r.id}（${r.date}）`).join(" → ")}</Field>}
          </dl>
          <p className="pr-quote">{recallText}</p>
        </section>
        <section className="pr-card">
          <div className="pr-buckets" role="group" aria-label="候选分类">{Object.entries(BUCKETS).map(([key, label]) => <button key={key} aria-pressed={bucket === key} onClick={() => setBucket(key)}>{label}<b>{recall.counts[key]}</b>{recall.text_checked && <small>模型判是 {verdictSplit(visibleCandidates(recall, key)).yes}</small>}</button>)}</div>
          <p className="pr-muted">分类只按车型年款和部件划分，不代表同一故障已确认；每类旁边是模型判"是"的条数，其余是"不是""说不清"或没有初判。</p>
          <p className="pr-muted">排序：召回后提交的在前，其次是起火、碰撞，再按提交日期由新到旧。{storageNote} 本召回已复核 {stats.reviewed}/{stats.total}。</p>
          {!state.confirmed_at && <p className="pr-note">先在“口径”里核对，才能复核。</p>}
          {error && <p role="alert" className="pr-error">{error}</p>}
          {!recall.candidates.length ? <p className="pr-empty">没有找到同部件投诉。0 条不代表没有同类问题：两边的部件名称写法不同、又没有通过核验的名称对应时，记录连不上。</p>
            : !visible.length ? <p className="pr-empty">这一类没有投诉，换一个分类看看。</p>
            : <div className="pr-layout">
              <div className="pr-list" ref={listRef} aria-label="投诉列表（上下方向键切换）">{visible.map((c) => {
                const mark = markOf(state, recall.series, c.id)?.mark;
                return <button key={c.id} aria-pressed={c.id === current} tabIndex={c.id === current ? 0 : -1} onClick={() => choose(c.id)}>
                  <strong>投诉 {c.id}</strong><span>{pack.signals[c.id].objects.join("、")}</span>
                  <Badges candidate={c} signal={pack.signals[c.id]} earlier={earlierDates(pack, c)} />
                  <small>模型：{c.text_check ? MARKS[VERDICT_TO_MARK[c.text_check.verdict]] : "未判断"} · 复核：{mark ? MARKS[mark] : "未复核"}</small>
                </button>;
              })}</div>
              {candidate && <article className="pr-detail" ref={detailRef} aria-label="投诉详情">
                <h3>投诉 {candidate.id} · {signal.objects.join("、")}</h3>
                <Badges candidate={candidate} signal={signal} earlier={earlierDates(pack, candidate)} />
                <p className="pr-muted">投诉部件：{signal.parts.join("、")}{candidate.timing ? ` · 召回 ${candidate.timing.event_date}，投诉 ${candidate.timing.signal_date}` : ""}</p>
                {candidate.via_alias && <p className="pr-note">这条投诉是经名称对应连上本召回部件的。你在口径里的判断：{pack.ontology.value_aliases.map((a) => `“${a.value} → ${a.target_value}”${ALIAS_VERDICTS[state.alias_checks?.[aliasKey(a)]] || "未判断"}`).join("、")}{doubts.length ? "，请按原文判断它是不是同一故障" : ""}。
                  <button type="button" className="pr-link" onClick={() => setTab("ontology")}>去口径改判断</button></p>}
                {candidate.other_events.length > 0 && <p className="pr-muted">已被召回 {candidate.other_events.map((id) => `${id}（${byId[id]?.date || "?"}${byId[id]?.series === recall.series ? "，同一系列" : ""}）`).join("、")} 覆盖</p>}
                <dl className="pr-kv">{signal.fields.map((f, i) => <div key={`${f.path}#${i}`}><dt>{fieldLabel(f.path)}</dt><dd><Evidence text={displayValue(f.value)} evidence={candidate.text_check?.evidence} /></dd></div>)}</dl>
                <div className="pr-model">{candidate.text_check ? <><strong>模型初判：{MARKS[VERDICT_TO_MARK[candidate.text_check.verdict]]}</strong><p>{candidate.text_check.reasoning}</p></> : <strong>这个召回没有模型初判</strong>}</div>
                <fieldset className="pr-marks" disabled={!state.confirmed_at}><legend>你的复核（点选即保存{seriesMembers.length > 1 ? "，同一系列共用" : ""}）</legend>
                  {Object.entries(MARKS).map(([key, label]) => <button key={key} type="button" aria-pressed={entry?.mark === key} onClick={() => apply((s) => markCandidate(s, recall.series, candidate.id, key, now()))}>{label}</button>)}
                  <label htmlFor="pr-note">备注（可选）</label>
                  <textarea id="pr-note" maxLength={1000} disabled={!entry} value={entry?.note || ""} placeholder={entry ? "只写看到的事实，不写推测的结论；不要写车主姓名、电话或车架号" : "先选结论再写备注"} aria-describedby="pr-note-hint" onChange={(e) => apply((s) => noteCandidate(s, recall.series, candidate.id, e.target.value, now()))} />
                  {personalInfo(entry?.note) && <p id="pr-note-hint" className="pr-error">备注里像是有{personalInfo(entry.note)}。样本库是公开的，请删掉，否则无法下载。</p>}
                </fieldset>
                <button className="pr-back" onClick={backToList}>返回列表</button>
              </article>}
            </div>}
          {visible.length > 0 && <p className="pr-muted pr-keys">键盘：列表里用 ↑ ↓ 切换投诉，按 1 同一故障、2 不是、3 说不清。</p>}
        </section>
      </div>}

      {tab === "results" && <>
        <section className="pr-card">
          <h2>复核进度</h2>
          <dl className="pr-fields">
            <Field label="已复核（全部召回）">{reviewedAll} 条</Field>
            <Field label={`召回 ${recall.id}`}>{stats.reviewed}/{stats.total} 条</Field>
            <Field label="与模型一致">{stats.compared ? `${stats.agree}/${stats.compared} 条` : "暂无可比条目"}</Field>
            <Field label="未进入任何候选的投诉">{pack.unconsidered.count} 条，最多的部件是 {pack.unconsidered.top_parts.slice(0, 3).map(([p, n]) => `${p} ${n}`).join("、")}</Field>
          </dl>
        </section>
        <section className="pr-card">
          <h2>和模型不一致的条目</h2>
          {stats.disagreements.length ? <ul className="pr-rows">{stats.disagreements.map((d) => {
            const c = recall.candidates.find((x) => x.id === d.id);
            return <li key={d.id}><button type="button" className="pr-link" onClick={() => { setTab("review"); setBucket(c.bucket); choose(d.id); }}>投诉 {d.id}</button><span>模型“{MARKS[d.model]}”，你“{MARKS[d.human]}”</span></li>;
          })}</ul> : <p className="pr-muted">召回 {recall.id} 暂时没有分歧。复核有模型初判的投诉后，分歧会出现在这里。</p>}
        </section>
        <section className="pr-card">
          <h2>下载</h2>
          <p className="pr-muted">下载的文件交给实施人员导入样本库，不需要自己读懂。文件里每行带车型、部件、投诉日期、起火碰撞、召回前后与所属系列，还有你对名称对应的判断；这些复核就是校准模型初判的标注。</p>
          <p className="pr-note">{NOTICE}</p>
          <label className="pr-reviewer" htmlFor="pr-reviewer">复核人
            <input id="pr-reviewer" value={reviewer} maxLength={40} placeholder="代号即可，样本库是公开的" autoComplete="off" aria-invalid={Boolean(reviewerIssue)}
              aria-describedby="pr-reviewer-hint" onChange={(e) => { setReviewer(e.target.value); remember(REVIEWER_KEY, e.target.value); }} />
          </label>
          <p id="pr-reviewer-hint" className={reviewerIssue ? "pr-error" : "pr-muted"}>{reviewerIssue ? `复核人里像是有${reviewerIssue}。样本库是公开的，请换成代号。`
            : reviewer.trim() ? "" : "不填也能下载，导入时需要补上复核人。"}</p>
          {noteIssues.length > 0 && <p className="pr-error">这些备注里像是有个人信息或本机内容，删掉后才能下载：{noteIssues.map((n) => `召回 ${n.recall} 投诉 ${n.complaint}（${n.issue}）`).join("、")}</p>}
          <button className="pr-primary" onClick={download} disabled={!reviewedAll || Boolean(reviewerIssue) || noteIssues.length > 0}>下载复核结果</button>
        </section>
      </>}
    </div>
    <footer className="pr-source">数据来自 NHTSA 公开接口（{pack.source.retrieved_from.slice(0, 10)} 取数）。OntoPoc 与 NHTSA 及所涉车企无关联，页面内容不是官方结论。</footer>
  </section>;
}
