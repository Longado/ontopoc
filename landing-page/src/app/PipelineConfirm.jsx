import React, { useState } from "react";
import { aiExplain, confirmPipeline, reviewPipeline } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { timeText } from "./format.js";
import { changeTitle, ChangeRow } from "./PipelineViews.jsx";
import { aiNodeLine, failureLine, friendlyError, markedIds, numberText, progressOf, statRows, toggleMark, versionsText } from "./pipelineModel.js";
import { hrefFor } from "./routeModel.js";
import { useLoad } from "./useLoad.js";

const storeKey = (name) => `pipeline-seen:${name}`;
const readMarks = (name) => {
  try {
    return JSON.parse(window.sessionStorage.getItem(storeKey(name)) ?? "null");
  } catch {
    return null;
  }
};

function StatsTable({ before, after }) {
  const rows = statRows(before, after);
  if (!rows.length) return null;
  return (
    <div className="table-wrap">
      <table className="wraps">
        <thead><tr><th>列</th><th>确认过的那次</th><th>现在</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.name} className={r.changed ? "changed" : ""}><td>{r.name}</td><td className="muted">{r.before}</td><td>{r.after}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

/** Why this person cannot confirm, when they cannot. */
function whyNot(detail, me) {
  if (detail.editors?.includes(me)) return "这条管道的定义你改过，要另一位来确认";
  if (detail.waiting_on?.length) return `管道用到的 ${detail.waiting_on.map((w) => `“${w.name}”`).join("、")} 还没有确认，要先确认它们`;
  return "你现在不能确认这条管道";
}

/** A confirmed pipeline has nothing left to confirm: which version, who and when. */
function Confirmed({ detail }) {
  return (
    <div className="pl-page">
      <p>第 {detail.confirmed_definition_version ?? detail.definition_version} 版已确认{detail.confirmed_by && `（${detail.confirmed_by}，${timeText(detail.confirmed_at)}）`}</p>
      <p><a href={hrefFor({ page: "pipeline", name: detail.name, view: "edit" })}>回到管道</a></p>
    </div>
  );
}

/** What the second person reads before confirming: each changed step with before and after, the statistics of its output then and now, a mark for each step seen. Once confirmed: only who confirmed which version. */
export function PipelineConfirm({ detail, reload }) {
  return detail.state === "confirmed" ? <Confirmed detail={detail} /> : <Review detail={detail} reload={reload} />;
}

/** 解释: a plain description of the steps that changed, written by the model from their settings. A reading aid, labelled AI-written; the settings below are what is confirmed. */
function Explain({ detail, ids }) {
  const [state, setState] = useState({ status: "idle" });
  const go = async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "ready", data: await aiExplain(detail.name, detail.spec, ids) });
    } catch (e) {
      setState({ status: "error", error: e.message });
    }
  };
  return (
    <div className="explain">
      <button className="secondary" onClick={go} disabled={!ids.length || state.status === "loading"}>{state.status === "loading" ? "AI 在写" : "解释这些步骤"}</button>
      {state.status === "error" && <p className="error">{friendlyError(state.error, detail.spec.steps)}</p>}
      {state.data && <div className="ai-draft"><p className="caption">{state.data.label}</p><p>{state.data.text}</p></div>}
    </div>
  );
}

function Review({ detail, reload }) {
  const { user } = useAuth();
  const [state] = useLoad(() => reviewPipeline(detail.name), [detail.name, detail.version]);
  const [marks, setMarks] = useState(() => readMarks(detail.name));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const review = state.data;
  const version = detail.definition_version;
  const seen = markedIds(marks, version);
  const progress = review ? progressOf(review.changes, marks, version) : { seen: 0, total: 0 };
  const mark = (id) => {
    const next = toggleMark(marks, version, id);
    setMarks(next);
    window.sessionStorage.setItem(storeKey(detail.name), JSON.stringify(next));
  };
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmPipeline(detail.name, detail.version, detail.inputs_now);
      window.sessionStorage.removeItem(storeKey(detail.name));
      reload();
    } catch (e) {
      setError(e.message);
      if (e.code === 409) reload();
    }
    setBusy(false);
  };
  const ready = review && progress.seen === progress.total && detail.can_confirm;
  return (
    <div className="pl-page">
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !review && <p className="muted">按现在的数据把管道算一遍（不写数据）</p>}
      {review && (
        <>
          <p>{review.compared_with ? `和第 ${review.compared_with} 版（上次确认的）比，改了这些：` : "这条管道还没有人确认过，下面是它的全部步骤："} 按 {versionsText(review.inputs_now)} 算。</p>
          <div className="bar" aria-hidden="true"><span style={{ width: `${progress.total ? (progress.seen / progress.total) * 100 : 0}%` }} /></div>
          <p className="muted small">已看过 {progress.seen} / {progress.total} 步。定义再被改，已看过的标记会清掉。</p>
          {!review.changes.length && <p className="muted">和上次确认的相比，步骤没有变化。</p>}
          {review.changes.some((c) => c.change !== "DEL") && <Explain detail={detail} ids={review.changes.filter((c) => c.change !== "DEL" && c.after.type !== "output").map((c) => c.id)} />}
          {review.ai_nodes?.length > 0 && (
            <div className="verdict">
              <p className="caption">AI 步骤的样本审核（它们写出的列标着“AI 生成”）</p>
              <ul className="plain-list">{review.ai_nodes.map((n) => <li key={n.id} className={n.review.passed ? "" : "warn"}>{aiNodeLine(n)}</li>)}</ul>
            </div>
          )}
          {review.changes.map((c) => (
            <section key={`${c.id}${c.change}`} className="card confirm-step">
              <ChangeRow change={c} steps={detail.spec.steps} titleOf={changeTitle} />
              {c.change !== "DEL" && (
                <p className="muted small">这一步的结果：{review.rows_before?.[c.id] != null ? `${numberText(review.rows_before[c.id])} 行 → ` : ""}{numberText(review.rows_now[c.id])} 行</p>
              )}
              {c.change !== "DEL" && <StatsTable before={review.stats_before?.[c.id]} after={review.stats_now[c.id]} />}
              {review.failures?.[c.id] && <p className="warn small">按现在的数据：{Object.entries(review.failures[c.id]).map(([k, n]) => failureLine(k, n)).join("；")}</p>}
              <label className="check"><input type="checkbox" checked={seen.includes(c.id)} onChange={() => mark(c.id)} />已看过这一步</label>
            </section>
          ))}
          <div className="inline wide">
            {detail.can_confirm
              ? <button className="primary" disabled={!ready || busy} onClick={confirm}>确认这条管道</button>
              : <span className="warn">{whyNot(detail, user?.display_name)}</span>}
            {detail.can_confirm && !ready && <span className="muted small">每一步都看过，才能确认</span>}
            {error && <span className="error">{error}</span>}
          </div>
        </>
      )}
    </div>
  );
}
