import React, { useState } from "react";
import { confirmPipeline, reviewPipeline } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { changeTitle, ChangeRow } from "./PipelineViews.jsx";
import { markedIds, numberText, progressOf, statRows, toggleMark, versionsText } from "./pipelineModel.js";
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
  if (detail.state === "confirmed") return "这条管道已经确认了";
  if (detail.editors?.includes(me)) return "这条管道的定义你改过，要另一位来确认";
  if (detail.waiting_on?.length) return `管道用到的 ${detail.waiting_on.map((w) => `“${w.name}”`).join("、")} 还没有确认，要先确认它们`;
  return "你现在不能确认这条管道";
}

/** What the second person reads before confirming: each changed step with before and after, the statistics of its output then and now, a mark for each step seen. */
export function PipelineConfirm({ detail, reload }) {
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
          {review.changes.map((c) => (
            <section key={`${c.id}${c.change}`} className="card confirm-step">
              <ChangeRow change={c} titleOf={changeTitle} />
              {c.change !== "DEL" && (
                <p className="muted small">这一步的结果：{review.rows_before?.[c.id] != null ? `${numberText(review.rows_before[c.id])} 行 → ` : ""}{numberText(review.rows_now[c.id])} 行</p>
              )}
              {c.change !== "DEL" && <StatsTable before={review.stats_before?.[c.id]} after={review.stats_now[c.id]} />}
              {Object.keys(review.failures ?? {}).includes(c.id) && <p className="warn small">这一步有 {Object.entries(review.failures[c.id]).map(([k, n]) => `${k} ${n}`).join("，")}</p>}
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
          {detail.state === "confirmed" && <p><a href={hrefFor({ page: "pipeline", name: detail.name, view: "edit" })}>回到管道</a></p>}
        </>
      )}
    </div>
  );
}
