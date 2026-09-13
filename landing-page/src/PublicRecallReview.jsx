import { useEffect, useRef, useState } from "react";
import {
  BUCKETS, DATASET_KEY, FLAG_LABELS, INDEX_URL, MARKS, ROLE_LABELS, VERDICT_TO_MARK, confirmOntology, defaultRecallId, displayValue, emptyState,
  exportState, fieldLabel, highlight, markCandidate, markOf, nextSelection, noteCandidate, orderCandidates, restoreState, storageKey,
  packUrl, pickDataset, summarize, timingLabel, validateIndex, validatePack, visibleCandidates,
} from "./publicReviewModel.js";
import "./PublicRecallReview.css";

const now = () => new Date().toISOString();
const narrow = () => window.matchMedia?.("(max-width: 760px)").matches;
const TRANSFORM_NOTE = { colon_hierarchy: "（按层级拆分）", split_comma: "（逗号分隔多项）" };
const TABS = [["ontology", "本体"], ["recalls", "召回"], ["review", "复核"], ["results", "结果"]];

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

function Field({ label, children }) {
  return <div className="pr-field"><dt>{label}</dt><dd>{children}</dd></div>;
}

function OntologyTab({ ontology, confirmedAt, onConfirm }) {
  const label = Object.fromEntries(ontology.object_types.map((t) => [t.key, t.label || t.key]));
  const shared = Object.entries(ontology.metrics.shared_across_sources).filter(([, n]) => n > 0).map(([k, n]) => `${label[k]} ${n} 个`);
  return <>
    <section className="pr-card">
      <h2>核验结果</h2>
      <dl className="pr-fields">
        <Field label="状态">通过（第 {ontology.attempts} 次提交）</Field>
        <Field label="两个来源靠这些对象连上">{shared.join("、")}</Field>
        <Field label="名称对应">{ontology.value_aliases.length} 条通过，{ontology.rejected_aliases.length} 条被拒</Field>
        <Field label="确认">{confirmedAt ? `已确认 · ${confirmedAt.slice(0, 16).replace("T", " ")}（本机记录，不是审批）` : "待确认"}</Field>
      </dl>
      <p className="pr-muted">模型只看了字段名和示例值；每一项都已由代码拿全部记录核验。确认后才能复核投诉。</p>
      {!confirmedAt && <button className="pr-primary" onClick={onConfirm}>确认本体和名称对应，开始复核</button>}
    </section>
    <section className="pr-card">
      <h2>对象类型</h2>
      <div className="pr-types">{ontology.object_types.map((t) => <article key={t.key} className="pr-type">
        <span className={`pr-tag pr-role-${t.role}`}>{ROLE_LABELS[t.role] || t.role}</span>
        <h3>{t.label || t.key}</h3>
        <p>{t.sources.map((s) => `${s.source}：${s.fields.join(" + ")}${TRANSFORM_NOTE[s.transform] || ""}${s.where ? `，只取 ${[].concat(s.where).map((w) => `${w.path} = ${w.equals}`).join(" 且 ")}` : ""}`).join("；")}</p>
        {t.time_field && <p>时间：{t.time_field.source}.{t.time_field.path}</p>}
        {t.rationale && <small>{t.rationale}</small>}
      </article>)}</div>
    </section>
    <section className="pr-card">
      <h2>关系</h2>
      <ul className="pr-rows">{ontology.relations.map((r) => <li key={r.key}><b>{label[r.from]} → {label[r.to]}</b><span>{r.meaning}</span><code>{r.source}</code></li>)}</ul>
    </section>
    <section className="pr-card">
      <h2>两个来源的名称对应</h2>
      {ontology.value_aliases.length ? <ul className="pr-rows">{ontology.value_aliases.map((a) => <li key={`${a.source}.${a.value}`}>
        <b>{a.source} “{a.value}” → {a.target_source} “{a.target_value}”</b><span>{a.reasoning}</span><code>多连上 {a.records_linked} 条</code></li>)}</ul>
        : <p className="pr-muted">没有通过核验的名称对应。</p>}
      {ontology.rejected_aliases.length > 0 && <details><summary>被代码拒绝的对应（{ontology.rejected_aliases.length} 条）</summary><ul>{ontology.rejected_aliases.map((a, i) => <li key={i}>“{a.value}” → “{a.target_value}”：{a.reason}</li>)}</ul></details>}
    </section>
    <section className="pr-card">
      <h2>数据缺口与未用字段</h2>
      <details open><summary>模型指出的数据缺口（{ontology.data_gaps.length} 条）</summary><ul>{ontology.data_gaps.map((g) => <li key={g}>{g}</li>)}</ul></details>
      <details><summary>未使用的字段（{ontology.ignored_fields.length} 个）</summary><ul>{ontology.ignored_fields.map((f) => <li key={`${f.source}.${f.path}`}>{f.source}.{f.path}：{f.reason}</li>)}</ul></details>
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
    setTab("ontology"); setBucket("outside_all"); setSelected("");
    const entry = index.datasets.find((d) => d.id === datasetId);
    readJson(packUrl(entry), `数据集 ${entry.label} `)
      .then((data) => {
        if (!active) return;
        const p = validatePack(data);
        setPack(p);
        setRecallId(defaultRecallId(p));
        try {
          const restored = restoreState(localStorage.getItem(storageKey(p)), p);
          setState(restored);
          if (restored.confirmed_at) setTab("recalls");
        } catch { setStorageBlocked(true); setState(emptyState(p)); setStorageNote("本机已有复核记录无法读取，原记录保留未覆盖；本次复核不会自动保存。"); }
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

  function apply(change) {
    try { setState((s) => change(s)); setError(""); } catch (e) { setError(e.message); }
  }
  function choose(id) {
    setSelected(id);
    if (narrow()) requestAnimationFrame(() => detailRef.current?.scrollIntoView({ block: "start" }));
  }
  function openRecall(id) { setRecallId(id); setSelected(""); setTab("review"); }
  function backToList() {
    listRef.current?.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: "center" });
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(exportState(pack, state, now()), null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `${datasetId}-review.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className="pr-page" aria-labelledby="pr-title">
    {language === "en" && <p className="pr-note" lang="en">This scenario page is available in Chinese only for now.</p>}
    <header className="pr-head">
      <div className="pr-head-line">
        <h1 id="pr-title">汽车召回范围研判</h1>
        <span className={`pr-status ${state.confirmed_at ? "pr-status-ok" : "pr-status-wait"}`}>{state.confirmed_at ? "本体已确认" : "本体待确认"}</span>
        {datasetPicker}
        <span className="pr-meta">NHTSA · {pack.source.events} 个召回 · {pack.source.record_counts.complaints} 条投诉 · {pack.source.retrieved_from.slice(0, 10)} 取数</span>
      </div>
      <nav className="pr-tabs" role="tablist" aria-label="研判步骤">{TABS.map(([key, label]) => <button key={key} type="button" role="tab" id={`pr-tab-${key}`}
        aria-selected={tab === key} aria-controls="pr-panel" onClick={() => setTab(key)}>{label}{key === "review" && <small>{recall.id}</small>}{key === "results" && reviewedAll > 0 && <small>{reviewedAll}</small>}</button>)}</nav>
    </header>
    <p className="pr-boundary">{pack.boundary} 模型 {pack.run.model}，原文判断提示词 {pack.run.matcher_prompt_version}；初判仅供参考。</p>

    <div id="pr-panel" role="tabpanel" aria-labelledby={`pr-tab-${tab}`} className="pr-panel">
      {tab === "ontology" && <OntologyTab ontology={pack.ontology} confirmedAt={state.confirmed_at}
        onConfirm={() => { apply((s) => confirmOntology(s, now())); setTab("recalls"); }} />}

      {tab === "recalls" && <section className="pr-card">
        <h2>选择一个召回</h2>
        <p className="pr-muted">按部件分组，组内按日期排列。原文写明“修复后再召回”的召回连成一个系列，系列内共用复核结论和模型初判。点一个召回进入复核。</p>
        <div className="pr-groups">{pack.groups.map((g) => <div key={g.id} className="pr-group">
          <h3>{g.id}</h3>
          <div className="pr-recalls">{g.recalls.map((id) => byId[id]).map((r) => <button key={r.id} aria-pressed={r.id === recallId} onClick={() => openRecall(r.id)}>
            <strong>{r.id}<span className="pr-date"> · {r.date}</span></strong>
            {r.references.length > 0 && <span className="pr-chain">接续召回 {r.references.join("、")}</span>}
            <small>覆盖 {r.covered.length} 个车型年款 · 范围外 {r.counts.outside_all} 条{r.text_checked ? " · 已有模型初判" : ""}</small>
          </button>)}</div>
        </div>)}</div>
      </section>}

      {tab === "review" && <>
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
          <div className="pr-buckets" role="group" aria-label="候选分类">{Object.entries(BUCKETS).map(([key, label]) => <button key={key} aria-pressed={bucket === key} onClick={() => setBucket(key)}>{label}<b>{recall.counts[key]}</b></button>)}</div>
          <p className="pr-muted">排序：召回后提交的在前，其次是起火、碰撞，再按提交日期由新到旧。{storageNote} 本召回已复核 {stats.reviewed}/{stats.total}。</p>
          {!state.confirmed_at && <p className="pr-note">先在“本体”里确认，才能复核。</p>}
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
                {candidate.via_alias && <p className="pr-note">这条投诉是经“名称对应”连上本召回的部件，请在“本体”里看这条对应是否成立。</p>}
                {candidate.other_events.length > 0 && <p className="pr-muted">已被召回 {candidate.other_events.map((id) => `${id}（${byId[id]?.date || "?"}${byId[id]?.series === recall.series ? "，同一系列" : ""}）`).join("、")} 覆盖</p>}
                <dl className="pr-kv">{signal.fields.map((f, i) => <div key={`${f.path}#${i}`}><dt>{fieldLabel(f.path)}</dt><dd><Evidence text={displayValue(f.value)} evidence={candidate.text_check?.evidence} /></dd></div>)}</dl>
                <div className="pr-model">{candidate.text_check ? <><strong>模型初判：{MARKS[VERDICT_TO_MARK[candidate.text_check.verdict]]}</strong><p>{candidate.text_check.reasoning}</p></> : <strong>这个召回没有模型初判</strong>}</div>
                <fieldset className="pr-marks" disabled={!state.confirmed_at}><legend>你的复核（点选即保存{seriesMembers.length > 1 ? "，同一系列共用" : ""}）</legend>
                  {Object.entries(MARKS).map(([key, label]) => <button key={key} type="button" aria-pressed={entry?.mark === key} onClick={() => apply((s) => markCandidate(s, recall.series, candidate.id, key, now()))}>{label}</button>)}
                  <label htmlFor="pr-note">备注（可选）</label>
                  <textarea id="pr-note" maxLength={1000} disabled={!entry} value={entry?.note || ""} placeholder={entry ? "" : "先选结论再写备注"} onChange={(e) => apply((s) => noteCandidate(s, recall.series, candidate.id, e.target.value, now()))} />
                </fieldset>
                <button className="pr-back" onClick={backToList}>返回列表</button>
              </article>}
            </div>}
        </section>
      </>}

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
          <p className="pr-muted">每行带车型、部件、投诉日期、起火碰撞、召回前后与所属系列；这些复核就是校准模型初判的标注。</p>
          <button className="pr-primary" onClick={download} disabled={!reviewedAll}>下载复核结果</button>
        </section>
      </>}
    </div>
  </section>;
}
