import React, { useState } from "react";
import { deleteAssistantTurn, getAssistantTurn } from "./api.js";
import { draftAgain, outcomeLine } from "./assistantHistoryModel.js";
import { meaningsCard, planCard, proposalCard } from "./assistantModel.js";
import { timeText } from "./format.js";
import { useT } from "./i18n/index.js";
import { useLoad } from "./useLoad.js";

/** A mode's name for a chip: the translated word, or the mode itself for a mode this page has no word for yet. */
export function modeLabel(t, mode) {
  const key = `ask.assistant.mode.${mode}`;
  const word = t(key);
  return word === key ? mode : word;
}

const line = (x) => x.text ?? x.key;

function Lists({ done, notDone }) {
  const t = useT();
  return (
    <div className="as-checked">
      <div>
        <h4>{t("ask.assistant.card.done")}</h4>
        <ul className="as-list done">{done.length ? done.map((x, i) => <li key={i}>{line(x)}</li>) : <li className="muted">{t("ask.assistant.card.none")}</li>}</ul>
      </div>
      <div>
        <h4>{t("ask.assistant.card.notDone")}</h4>
        <ul className="as-list not">{notDone.length ? notDone.map((x, i) => <li key={i}>{line(x)}</li>) : <li className="muted">{t("ask.assistant.card.none")}</li>}</ul>
      </div>
    </div>
  );
}

/** The stored card, read-only: the same plan or proposal model the live card uses, shown as plain rows. Nothing here runs, saves or applies. */
function CardBody({ mode, card }) {
  const t = useT();
  if (card.truncated) return <p className="muted">{t("ask.past.truncated")}</p>;
  if (mode === "pipeline") {
    const c = planCard(card, {});
    return (
      <dl className="as-rows">
        <div className="as-row"><dt>{t("ask.assistant.card.result")}</dt><dd><ol className="as-chain">{c.steps.map((s, i) => <li key={s.id}><span className="as-num">{i + 1}</span><div><p><strong>{s.summary}</strong></p>{s.operators.map((o, k) => <p key={k} className="muted small">{o}</p>)}</div></li>)}</ol></dd></div>
        <div className="as-row"><dt>{t("ask.assistant.card.assume")}</dt><dd>{c.assumptions.length ? <ul className="as-assume">{c.assumptions.map((a, i) => <li key={i}>{a.text}</li>)}</ul> : <span className="muted">{t("ask.assistant.card.none")}</span>}</dd></div>
        <div className="as-row"><dt>{t("ask.assistant.card.checked")}</dt><dd><Lists done={c.done} notDone={c.notDone} /></dd></div>
      </dl>
    );
  }
  if (mode === "model") {
    const c = proposalCard(card.result ?? card, []);
    return (
      <dl className="as-rows">
        <div className="as-row"><dt>{t("ask.assistant.card.result")}</dt><dd><ul className="as-types">{c.types.map((x) => <li key={x.id}><strong>{x.name}</strong> <code>{x.id}</code></li>)}</ul></dd></div>
        {c.assumptions.length > 0 && <div className="as-row"><dt>{t("ask.assistant.card.assume")}</dt><dd><ul className="as-assume">{c.assumptions.map((a) => <li key={a.id}>{a.text}</li>)}</ul></dd></div>}
        {c.rejected.length > 0 && <div className="as-row"><dt>{t("ask.assistant.model.rejected", { count: c.rejected.length })}</dt><dd><ul className="as-rejected">{c.rejected.map((r, i) => <li key={i}><strong>{r.name}</strong> <span className="muted">{r.reason}</span></li>)}</ul></dd></div>}
        <div className="as-row"><dt>{t("ask.assistant.card.checked")}</dt><dd><Lists done={c.done} notDone={c.notDone} /></dd></div>
      </dl>
    );
  }
  if (mode === "query") return <pre className="as-query">{card.query_text}</pre>;
  if (mode === "meanings") {
    const c = meaningsCard(card, {});
    return (
      <dl className="as-rows">
        <div className="as-row"><dt>{t("ask.assistant.card.result")}</dt><dd>{c.columns.map((col) => <div key={col.column}><p className="as-type-head"><strong>{col.column}</strong></p><ul className="as-assume">{col.values.filter((v) => v.hasDraft).map((v) => <li key={v.value}><code>{v.value}</code> {v.label}</li>)}</ul></div>)}</dd></div>
        {(card.skipped ?? []).length > 0 && <div className="as-row"><dt>{t("ask.past.skipped")}</dt><dd><ul className="as-rejected">{card.skipped.map((x) => <li key={x.column}><strong>{x.column}</strong> <span className="muted">{x.reason}</span></li>)}</ul></dd></div>}
        <div className="as-row"><dt>{t("ask.assistant.card.checked")}</dt><dd><Lists done={card.self_check?.done ?? []} notDone={card.self_check?.not_done ?? []} /></dd></div>
      </dl>
    );
  }
  const assumptions = Array.isArray(card.assumptions) ? card.assumptions : [];   // any other mode keeps its assumptions and self-check in the same shape
  return (
    <dl className="as-rows">
      {assumptions.length > 0 && <div className="as-row"><dt>{t("ask.assistant.card.assume")}</dt><dd><ul className="as-assume">{assumptions.map((a, i) => <li key={i}>{a.text}</li>)}</ul></dd></div>}
      <div className="as-row"><dt>{t("ask.assistant.card.checked")}</dt><dd><Lists done={card.self_check?.done ?? []} notDone={card.self_check?.not_done ?? []} /></dd></div>
    </dl>
  );
}

/** A past builder-mode turn, read-only: its message, its card (or why it is hidden), what happened next, "Draft again" and delete. */
export function PastTurn({ turnId, onDraftAgain, onDeleted }) {
  const t = useT();
  const [turn] = useLoad(() => getAssistantTurn(turnId), [turnId]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  if (turn.status === "error") return <p className="error" role="alert">{turn.error}</p>;
  if (turn.status !== "ready") return <p className="muted">{t("ask.past.loading")}</p>;
  const x = turn.data;
  const out = outcomeLine(x.outcome);
  const scope = [...(x.scope?.datasets ?? []), ...(x.scope?.types ?? []), ...(x.scope?.target ? [x.scope.target] : [])].map((s) => (s.hidden ? t("ask.past.hidden") : s.label || s.name));
  const remove = async () => {
    try {
      await deleteAssistantTurn(turnId);
      onDeleted();
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <>
      <div className="msg msg-user"><div className="bubble"><span className="bubble-tag">{modeLabel(t, x.mode)}</span>{x.mode === "query" ? <pre>{x.message}</pre> : x.message}</div></div>
      <div className="msg msg-bot">
        <span className="bot-mark" aria-hidden="true" />
        <div className="bot-body" aria-label={t("ask.chat.assistant")}>
          <section className="as-card frozen" aria-label={t("ask.past.aria")}>
            <header className="as-head">
              <span className="as-kind">{modeLabel(t, x.mode)}</span>
              <span className="as-scope muted">{[timeText(x.asked_at), ...scope].join(t("ask.sep"))}</span>
              <span className={`as-state ${out ? out.key : "pending"}`}>{out ? t(`ask.past.outcome.${out.key}`, { name: out.name }) : t("ask.past.outcome.unknown")}</span>
            </header>
            {x.withheld ? <p className="as-note" role="status">{x.reason}</p> : <CardBody mode={x.mode} card={x.card} />}
            {error && <p className="error" role="alert">{error}</p>}
            <footer className="as-actions">
              <button className="primary" onClick={() => onDraftAgain(draftAgain(x))}>{t("ask.past.again")}</button>
              {asking ? (
                <>
                  <button className="secondary" onClick={remove}>{t("ask.past.deleteYes")}</button>
                  <button className="secondary" onClick={() => setAsking(false)}>{t("ask.past.deleteNo")}</button>
                </>
              ) : <button className="secondary" onClick={() => setAsking(true)}>{t("ask.past.delete")}</button>}
              <span className="muted small">{t("ask.past.note")}</span>
            </footer>
          </section>
        </div>
      </div>
    </>
  );
}
