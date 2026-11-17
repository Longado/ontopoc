import React, { useState } from "react";
import { aiExplain, confirmPipeline, reviewPipeline } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { formatDateTime, t } from "./i18n/index.js";
import { PIcon } from "./PipelineIcons.jsx";
import { changeTitle, ChangeRow } from "./PipelineViews.jsx";
import { aiNodeLine, failureLine, friendlyError, labelledRow, markedIds, numberText, progressOf, rowsText, statRows, toggleMark, versionsText } from "./pipelineModel.js";
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
    <div className="pl-resource compact">
      <table className="wraps">
        <thead><tr><th>{t("pipeline.confirm.col")}</th><th>{t("pipeline.confirm.thenCol")}</th><th>{t("pipeline.confirm.nowCol")}</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.name} className={r.changed ? "changed" : ""}><td>{r.name}</td><td className="muted">{r.before}</td><td>{r.after}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

/** Why this person cannot confirm, when they cannot. */
function whyNot(detail, me) {
  if (detail.editors?.includes(me)) return t("pipeline.confirm.why.editor");
  if (detail.waiting_on?.length) return t("pipeline.confirm.why.waiting", { names: detail.waiting_on.map((w) => `“${w.name}”`).join(", ") });
  return t("pipeline.confirm.why.other");
}

/** A confirmed pipeline has nothing left to confirm: which version, who and when. */
function Confirmed({ detail }) {
  return (
    <div className="pl-page">
      <div className="pl-note ok big"><PIcon name="success" size={18} /><span>{t("pipeline.confirm.done", { version: detail.confirmed_definition_version ?? detail.definition_version })}{detail.confirmed_by && ` (${detail.confirmed_by}, ${formatDateTime(detail.confirmed_at)})`}</span></div>
      <p className="pl-backline"><a href={hrefFor({ page: "pipeline", name: detail.name, view: "edit" })}>&larr; {t("pipeline.confirm.back")}</a></p>
    </div>
  );
}

/** The rows the sample review was made on: what each said, what its labeller expected and what the step answered, mismatches first. Read this before trusting the count. */
function LabelledRows({ node }) {
  const rows = node.rows.map(labelledRow).sort((a, b) => Number(a.matched) - Number(b.matched));
  if (!rows.length) return <p className="muted small">{t("pipeline.confirm.noLabelled", { name: node.name })}</p>;
  return (
    <details className="labelled" open>
      <summary>{t("pipeline.confirm.labelled", { name: node.name, count: rows.length, off: rows.filter((r) => r.checked && !r.matched).length })}</summary>
      <div className="pl-resource compact">
        <table className="wraps">
          <thead><tr><th>{t("pipeline.confirm.lbl.row")}</th><th>{t("pipeline.confirm.lbl.expected")}</th><th>{t("pipeline.confirm.lbl.answered")}</th><th>{t("pipeline.confirm.lbl.who")}</th></tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i} className={r.checked && !r.matched ? "changed" : ""}><td>{r.text}</td><td>{r.expected}</td><td>{r.answered}</td><td className="muted">{r.who}</td></tr>)}</tbody>
        </table>
      </div>
    </details>
  );
}

/** What the second person reads before confirming: each changed step with before and after, the statistics of its output then and now, a mark for each step seen. Once confirmed: only who
 * confirmed which version. */
export function PipelineConfirm({ detail, reload }) {
  return detail.state === "confirmed" ? <Confirmed detail={detail} /> : <Review detail={detail} reload={reload} />;
}

/** "Explain": a plain description of the steps that changed, written by the model from their settings. A reading aid, labelled AI-written; the settings below are what is confirmed. */
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
      <button type="button" className="secondary pl-btn" onClick={go} disabled={!ids.length || state.status === "loading"}><PIcon name="sparkle" /> {state.status === "loading" ? t("pipeline.confirm.explaining") : t("pipeline.confirm.explain")}</button>
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
      {state.status === "loading" && !review && <div className="pl-skeleton table" aria-label={t("pipeline.loading")}><i /><i /><i /></div>}
      {state.status === "loading" && !review && <p className="muted">{t("pipeline.confirm.computing")}</p>}
      {review && (
        <>
          <div className="pl-review-head">
            <p>{review.compared_with ? t("pipeline.confirm.comparedWith", { version: review.compared_with }) : t("pipeline.confirm.firstTime")} {t("pipeline.confirm.basedOn", { inputs: versionsText(review.inputs_now) })}</p>
            <div className="pl-progress" role="progressbar" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.seen}><span style={{ width: `${progress.total ? (progress.seen / progress.total) * 100 : 0}%` }} /></div>
            <p className="muted small">{t("pipeline.confirm.progress", { seen: progress.seen, total: progress.total })}</p>
          </div>
          {!review.changes.length && <p className="muted">{t("pipeline.confirm.noChanges")}</p>}
          {review.changes.some((c) => c.change !== "DEL") && <Explain detail={detail} ids={review.changes.filter((c) => c.change !== "DEL" && c.after.type !== "output").map((c) => c.id)} />}
          {review.ai_nodes?.length > 0 && (
            <div className="verdict">
              <p className="caption">{t("pipeline.confirm.aiReview")}</p>
              <ul className="pl-lines">{review.ai_nodes.map((n) => <li key={n.id} className={n.review.passed ? "" : "warn"}>{aiNodeLine(n)}</li>)}</ul>
              {review.ai_nodes.map((n) => <LabelledRows key={n.id} node={n} />)}
            </div>
          )}
          {review.changes.map((c) => (
            <section key={`${c.id}${c.change}`} className={`pl-confirm-step${seen.includes(c.id) ? " seen" : ""}`}>
              <ChangeRow change={c} steps={detail.spec.steps} titleOf={changeTitle} />
              {c.change !== "DEL" && (
                <p className="muted small">{t("pipeline.confirm.result")} {review.rows_before?.[c.id] != null ? `${rowsText(review.rows_before[c.id])} → ` : ""}{rowsText(review.rows_now[c.id])}</p>
              )}
              {c.change !== "DEL" && <StatsTable before={review.stats_before?.[c.id]} after={review.stats_now[c.id]} />}
              {review.failures?.[c.id] && <p className="warn small">{t("pipeline.confirm.nowData")} {Object.entries(review.failures[c.id]).map(([k, n]) => failureLine(k, n)).join("; ")}</p>}
              <label className="check"><input type="checkbox" checked={seen.includes(c.id)} onChange={() => mark(c.id)} />{t("pipeline.confirm.seen")}</label>
            </section>
          ))}
          <div className="pl-confirm-bar">
            {detail.can_confirm
              ? <button type="button" className="primary" disabled={!ready || busy} onClick={confirm}>{t("pipeline.confirm.confirm")}</button>
              : <span className="warn">{whyNot(detail, user?.display_name)}</span>}
            {detail.can_confirm && !ready && <span className="muted small">{t("pipeline.confirm.allSeen")}</span>}
            {error && <span className="error">{error}</span>}
          </div>
        </>
      )}
    </div>
  );
}
