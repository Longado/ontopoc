import { useEffect, useRef, useState } from "react";
import {
  BUCKETS, FLAG_LABELS, MARKS, PACK_URL, ROLE_LABELS, VERDICT_TO_MARK, confirmOntology, defaultRecallId, emptyState,
  exportState, highlight, markCandidate, markOf, nextSelection, noteCandidate, orderCandidates, restoreState, storageKey,
  summarize, timingLabel, validatePack, visibleCandidates,
} from "./publicReviewModel.js";
import "./PublicRecallReview.css";

const now = () => new Date().toISOString();
const narrow = () => window.matchMedia?.("(max-width: 760px)").matches;
const TRANSFORM_NOTE = { colon_hierarchy: "（按层级拆分）", split_comma: "（逗号分隔多项）" };

function Evidence({ text, evidence }) {
  const parts = highlight(text, evidence);
  return parts ? <>{parts[0]}<mark>{parts[1]}</mark>{parts[2]}</> : text;
}

function Badges({ candidate, signal }) {
  const time = timingLabel(candidate.timing);
  return <span className="pr-badges">
    {time && <span className={`pr-badge pr-badge-${candidate.timing.relation}`}>{time}</span>}
    {signal.flags.map((f) => <span key={f} className="pr-badge pr-badge-flag">{FLAG_LABELS[f] || f}</span>)}
    {candidate.via_alias && <span className="pr-badge pr-badge-alias">经名称对应</span>}
  </span>;
}

function Ontology({ ontology, confirmedAt, onConfirm }) {
  const label = Object.fromEntries(ontology.object_types.map((t) => [t.key, t.label || t.key]));
  const shared = Object.entries(ontology.metrics.shared_across_sources).filter(([, n]) => n > 0).map(([k, n]) => `${label[k]} ${n} 个`);
  return <section className="pr-card" aria-labelledby="pr-ontology-title">
    <h2 id="pr-ontology-title">① 系统自动搭建的本体</h2>
    <p className="pr-muted">模型只看了字段名和示例值；以下每一项都已由代码拿全部记录核验。核验通过（第 {ontology.attempts} 次提交）。两个来源靠这些对象连上：{shared.join("、")}。</p>
    <div className="pr-types">{ontology.object_types.map((t) => <article key={t.key} className={`pr-type pr-role-${t.role}`}>
      <span className="pr-tag">{ROLE_LABELS[t.role] || t.role}</span><h3>{t.label || t.key}</h3>
      <p>{t.sources.map((s) => `${s.source}：${s.fields.join(" + ")}${TRANSFORM_NOTE[s.transform] || ""}${s.where ? `，只取 ${[].concat(s.where).map((w) => `${w.path} = ${w.equals}`).join(" 且 ")}` : ""}`).join("；")}</p>
      {t.time_field && <p>时间：{t.time_field.source}.{t.time_field.path}</p>}
      {t.rationale && <small>{t.rationale}</small>}
    </article>)}</div>
    <h3>关系</h3>
    <ul className="pr-relations">{ontology.relations.map((r) => <li key={r.key}>{label[r.from]} → {label[r.to]}<small>（{r.source}）{r.meaning}</small></li>)}</ul>
    <h3>两个来源的名称对应（{ontology.value_aliases.length} 条，模型提出、代码核验）</h3>
    {ontology.value_aliases.length ? <ul className="pr-relations">{ontology.value_aliases.map((a) => <li key={`${a.source}.${a.value}`}>
      {a.source} 里的 “{a.value}” 当作 {a.target_source} 里的 “{a.target_value}”<small>多连上 {a.records_linked} 条记录。{a.reasoning}</small></li>)}</ul>
      : <p className="pr-muted">没有通过核验的名称对应。</p>}
    {ontology.rejected_aliases.length > 0 && <details><summary>被代码拒绝的对应（{ontology.rejected_aliases.length} 条）</summary><ul>{ontology.rejected_aliases.map((a, i) => <li key={i}>“{a.value}” → “{a.target_value}”：{a.reason}</li>)}</ul></details>}
    <details><summary>模型指出的数据缺口（{ontology.data_gaps.length} 条）</summary><ul>{ontology.data_gaps.map((g) => <li key={g}>{g}</li>)}</ul></details>
    <details><summary>未使用的字段（{ontology.ignored_fields.length} 个）</summary><ul>{ontology.ignored_fields.map((f) => <li key={`${f.source}.${f.path}`}>{f.source}.{f.path}：{f.reason}</li>)}</ul></details>
    {confirmedAt ? <p className="pr-confirmed" role="status">已确认本体与名称对应 · {confirmedAt.slice(0, 16).replace("T", " ")}（本机记录，不是审批）</p>
      : <button className="pr-primary" onClick={onConfirm}>确认本体和名称对应，开始复核</button>}
  </section>;
}

export function PublicRecallReview({ language = "zh" }) {
  const [pack, setPack] = useState(null);
  const [state, setState] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [storageNote, setStorageNote] = useState("");
  const [storageBlocked, setStorageBlocked] = useState(false);
  const [recallId, setRecallId] = useState("");
  const [bucket, setBucket] = useState("outside_all");
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const detailRef = useRef(null);
  const listRef = useRef(null);

  useEffect(() => {
    let active = true;
    fetch(PACK_URL, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(`页面数据读取失败（${r.status}）`); return r.json(); })
      .then((data) => {
        if (!active) return;
        const p = validatePack(data);
        setPack(p);
        setRecallId(defaultRecallId(p));
        try { setState(restoreState(localStorage.getItem(storageKey(p)), p)); }
        catch { setStorageBlocked(true); setState(emptyState(p)); setStorageNote("本机已有复核记录无法读取，原记录保留未覆盖；本次复核不会自动保存。"); }
      })
      .catch((e) => { if (active) setLoadError(e.message); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!pack || !state || storageBlocked) return;
    try { localStorage.setItem(storageKey(pack), JSON.stringify(state)); setStorageNote("复核随点随存到本机浏览器，刷新可恢复。"); }
    catch { setStorageNote("保存失败：浏览器存储不可用。请用“下载复核结果”保留进度。"); }
  }, [pack, state, storageBlocked]);

  const recall = pack?.recalls.find((r) => r.id === recallId);
  const visible = recall ? orderCandidates(visibleCandidates(recall, bucket), pack.signals) : [];
  const current = nextSelection(selected, visible);
  useEffect(() => { if (current !== selected) setSelected(current); }, [current, selected]);

  if (loadError) return <section className="pr-page"><p role="alert">{loadError}</p></section>;
  if (!pack || !state || !recall) return <section className="pr-page"><p role="status">读取数据中…</p></section>;

  const byId = Object.fromEntries(pack.recalls.map((r) => [r.id, r]));
  const candidate = visible.find((c) => c.id === current);
  const signal = candidate && pack.signals[candidate.id];
  const entry = candidate && markOf(state, recall.series, candidate.id);
  const stats = summarize(pack, state, recall.id);
  const recallText = recall.fields.find((f) => f.path === "Summary")?.value || recall.fields[0]?.value || "";
  const seriesMembers = pack.recalls.filter((r) => r.series === recall.series);

  function apply(change) {
    try { setState((s) => change(s)); setError(""); } catch (e) { setError(e.message); }
  }
  function choose(id) {
    setSelected(id);
    if (narrow()) requestAnimationFrame(() => detailRef.current?.scrollIntoView({ block: "start" }));
  }
  function backToList() {
    listRef.current?.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: "center" });
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(exportState(pack, state, now()), null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = "nhtsa-recall-review.json"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className="pr-page" aria-labelledby="pr-title">
    {language === "en" && <p className="pr-note" lang="en">This scenario page is available in Chinese only for now.</p>}
    <header>
      <span className="pr-eyebrow">公开数据 · 美国 NHTSA 汽车召回与车主投诉</span>
      <h1 id="pr-title">召回发布后，哪些同类问题落在召回范围外？</h1>
      <p>雪佛兰 Bolt EV / EUV 2017–2023：{pack.source.events} 个召回、车主投诉 {pack.source.record_counts.complaints} 条，{pack.source.retrieved_from.slice(0, 10)} 取数。系统自动搭建本体、按本体查范围，模型读投诉原文给出初判，由你逐条复核。</p>
    </header>
    <p className="pr-boundary">{pack.boundary} 模型 {pack.run.model}，原文判断提示词 {pack.run.matcher_prompt_version}；初判仅供参考。</p>

    <Ontology ontology={pack.ontology} confirmedAt={state.confirmed_at} onConfirm={() => apply((s) => confirmOntology(s, now()))} />

    <section className="pr-card" aria-labelledby="pr-recalls-title">
      <h2 id="pr-recalls-title">② 选择一个召回</h2>
      <p className="pr-muted">按部件分组，组内按日期排列。原文写明“修复后再召回”的召回连成一个系列，系列内共用复核结论和模型初判。</p>
      <div className="pr-groups">{pack.groups.map((g) => <div key={g.id} className="pr-group">
        <h3>{g.id}</h3>
        <div className="pr-recalls">{g.recalls.map((id) => byId[id]).map((r) => <button key={r.id} aria-pressed={r.id === recallId} onClick={() => { setRecallId(r.id); setSelected(""); }}>
          <strong>{r.id}<span className="pr-date"> · {r.date}</span></strong>
          {r.references.length > 0 && <span>接续召回 {r.references.join("、")}</span>}
          <small>覆盖 {r.covered.length} 个车型年款 · 范围外 {r.counts.outside_all} 条{r.text_checked ? " · 已有模型初判" : ""}</small>
        </button>)}</div>
      </div>)}</div>
      <div className="pr-recall-detail">
        <p><strong>召回内容：</strong>{recallText}</p>
        <p><strong>覆盖车型年款：</strong>{recall.covered.join("、") || "无"}</p>
        {seriesMembers.length > 1 && <p><strong>同一系列：</strong>{seriesMembers.map((r) => `${r.id}（${r.date}）`).join(" → ")}</p>}
        {!recall.text_checked && <p className="pr-note">这个召回还没跑模型原文判断，下面只有按部件和车型年款算出的候选；可用命令行 <code>scripts/run_public_ontology.py --campaign {recall.id}</code> 补跑。</p>}
      </div>
    </section>

    <section className="pr-card" aria-labelledby="pr-review-title">
      <h2 id="pr-review-title">③ 复核同部件投诉</h2>
      <div className="pr-buckets" role="group" aria-label="候选分类">{Object.entries(BUCKETS).map(([key, label]) => <button key={key} aria-pressed={bucket === key} onClick={() => setBucket(key)}>{label} {recall.counts[key]}</button>)}</div>
      <p className="pr-muted">排序：召回后提交的在前，其次是起火、碰撞，再按提交日期由新到旧。另有 {pack.unconsidered.count} 条投诉没有进入任何召回的候选，部件最多的是 {pack.unconsidered.top_parts.map(([p, n]) => `${p} ${n}`).join("、")}。</p>
      {!state.confirmed_at && <p className="pr-note">先在 ① 确认本体，才能复核。</p>}
      <p role="status" className="pr-muted">{storageNote} 本召回已复核 {stats.reviewed}/{stats.total}。</p>
      {error && <p role="alert" className="pr-error">{error}</p>}
      {!recall.candidates.length ? <p className="pr-empty">没有找到同部件投诉。0 条不代表没有同类问题：两边的部件名称写法不同、又没有通过核验的名称对应时，记录连不上。</p>
        : !visible.length ? <p className="pr-empty">这一类没有投诉，换一个分类看看。</p>
        : <div className="pr-layout">
          <div className="pr-list" ref={listRef} aria-label="投诉列表">{visible.map((c) => {
            const mark = markOf(state, recall.series, c.id)?.mark;
            return <button key={c.id} aria-pressed={c.id === current} onClick={() => choose(c.id)}>
              <strong>投诉 {c.id}</strong><span>{pack.signals[c.id].objects.join("、")}</span>
              <Badges candidate={c} signal={pack.signals[c.id]} />
              <small>模型：{c.text_check ? MARKS[VERDICT_TO_MARK[c.text_check.verdict]] : "未判断"} · 复核：{mark ? MARKS[mark] : "未复核"}</small>
            </button>;
          })}</div>
          {candidate && <article className="pr-detail" ref={detailRef} aria-label="投诉详情">
            <h3>投诉 {candidate.id} · {signal.objects.join("、")}</h3>
            <Badges candidate={candidate} signal={signal} />
            <p className="pr-muted">投诉部件：{signal.parts.join("、")}{candidate.timing ? ` · 召回 ${candidate.timing.event_date}，投诉 ${candidate.timing.signal_date}` : ""}</p>
            {candidate.via_alias && <p className="pr-note">这条投诉是经“名称对应”连上本召回的部件，确认本体时请看 ① 里的对应是否成立。</p>}
            {candidate.other_events.length > 0 && <p className="pr-muted">已被召回 {candidate.other_events.map((id) => `${id}（${byId[id]?.date || "?"}${byId[id]?.series === recall.series ? "，同一系列" : ""}）`).join("、")} 覆盖</p>}
            <dl>{signal.fields.map((f, i) => <div key={`${f.path}#${i}`}><dt>{f.path}</dt><dd><Evidence text={f.value} evidence={candidate.text_check?.evidence} /></dd></div>)}</dl>
            <div className="pr-model">{candidate.text_check ? <><strong>模型初判：{MARKS[VERDICT_TO_MARK[candidate.text_check.verdict]]}</strong><p>{candidate.text_check.reasoning}</p></> : <strong>这个召回没有模型初判</strong>}</div>
            <fieldset className="pr-marks" disabled={!state.confirmed_at}><legend>你的复核（点选即保存{seriesMembers.length > 1 ? "，同一系列共用" : ""}）</legend>
              {Object.entries(MARKS).map(([key, label]) => <button key={key} type="button" aria-pressed={entry?.mark === key} onClick={() => apply((s) => markCandidate(s, recall.series, candidate.id, key, now()))}>{label}</button>)}
              <label>备注（可选）<textarea maxLength={1000} disabled={!entry} value={entry?.note || ""} placeholder={entry ? "" : "先选结论再写备注"} onChange={(e) => apply((s) => noteCandidate(s, recall.series, candidate.id, e.target.value, now()))} /></label>
            </fieldset>
            <button className="pr-back" onClick={backToList}>返回列表</button>
          </article>}
        </div>}
    </section>

    <section className="pr-card" aria-labelledby="pr-summary-title">
      <h2 id="pr-summary-title">④ 复核结果</h2>
      {stats.compared ? <p>本召回有模型初判且你已复核的 {stats.compared} 条里，与模型一致 {stats.agree} 条。</p> : <p>复核有模型初判的投诉后，这里会显示你和模型的一致情况。</p>}
      {stats.disagreements.length > 0 && <ul className="pr-disagree">{stats.disagreements.map((d) => {
        const c = recall.candidates.find((x) => x.id === d.id);
        return <li key={d.id}><button onClick={() => { setBucket(c.bucket); choose(d.id); }}>投诉 {d.id}</button>：模型“{MARKS[d.model]}”，你“{MARKS[d.human]}”</li>;
      })}</ul>}
      <p className="pr-muted">这些复核就是校准模型初判的标注。下载后可用于比较提示词版本。</p>
      <button onClick={download} disabled={!Object.keys(state.marks).length}>下载复核结果</button>
    </section>
  </section>;
}
