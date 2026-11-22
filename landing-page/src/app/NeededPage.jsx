import React, { useState } from "react";
import { addNeeded, confirmNeeded, deleteNeeded, getNeeded, runNeeded, updateNeeded } from "./api.js";
import { useT } from "./i18n/index.js";
import { adoptable, canConfirm, confirmHint, expectPayload, expectText, lastRunText, outcomeWord, planText, resultLines, runAllowed, stateText } from "./neededModel.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";
import "./needed.css";

const MAX_QUESTION = 300;
const MAX_NOTE = 120;

/** The team's questions we need (needed_questions.py): write a question and what it should give, have another person confirm that, run the list and read what each
 * question came back as. Builders and admins whom no rule limits; the service refuses anyone else and says why. */
export function NeededPage() {
  const t = useT();
  const [state, reload] = useLoad(getNeeded, []);
  const listing = state.data;
  return (
    <main className="page needed">
      <PageHeader title={t("needed.title")} sub={t("needed.sub")} />
      {state.status === "error" && <p className="error" role="alert">{state.error}</p>}
      {state.status === "loading" && !listing && <p className="muted">{t("needed.loading")}</p>}
      {listing && (
        <>
          <RunBox listing={listing} onDone={reload} />
          {listing.questions.length === 0 && <EmptyState icon="check-circle" title={t("needed.empty.title")} text={t("needed.empty.text")} />}
          {listing.questions.length > 0 && (
            <ul className="nq-list">
              {listing.questions.map((q) => <Question key={q.id} item={q} twoPerson={listing.two_person} onChange={reload} />)}
            </ul>
          )}
          {listing.questions.length < listing.limits.questions && <QuestionForm onDone={reload} />}
        </>
      )}
    </main>
  );
}

/** How many times to ask, what the run will cost before it starts, the button, and the last run in one line. */
function RunBox({ listing, onDone }) {
  const t = useT();
  const [repeats, setRepeats] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const allowed = runAllowed(listing, repeats);
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      await runNeeded(repeats);
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const run = listing.last_run;
  return (
    <section className="card nq-run" aria-labelledby="nq-run-title">
      <h2 id="nq-run-title">{t("needed.run.title")}</h2>
      {listing.questions.length > 0 && <p className="nq-plan">{planText(listing, repeats)}</p>}
      <div className="nq-run-row">
        <label className="nq-repeats">
          <span className="caption">{t("needed.run.repeats")}</span>
          <select value={repeats} onChange={(e) => setRepeats(Number(e.target.value))} disabled={busy}>
            {Array.from({ length: listing.limits.repeats }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{t("needed.times", { count: n })}</option>)}
          </select>
        </label>
        <button className="primary" type="button" onClick={start} disabled={busy || !allowed.ok}>{t("needed.run.button")}</button>
      </div>
      {busy && <p className="muted small" role="status">{t("needed.run.running")}</p>}
      {!busy && !allowed.ok && allowed.why && <p className="muted small">{allowed.why}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {run && <p className="muted small">{lastRunText(run)}</p>}
      {run?.note && <p className="small nq-warn">{t("needed.last.stopped", { note: run.note })}</p>}
      {run?.stale_prompt && <p className="small nq-warn">{t("needed.last.stalePrompt")}</p>}
    </section>
  );
}

/** One question: its words, what it should give and where that stands, the buttons this person may use, and what it came back as in the last run. */
function Question({ item, twoPerson, onChange }) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const act = async (call) => {
    setBusy(true);
    setError("");
    try {
      await call();
      onChange();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const result = item.result;
  const adopt = adoptable(result);
  const hint = confirmHint(item, twoPerson);
  return (
    <li className="card nq-item">
      <p className="nq-question">{item.question}</p>
      <p className="nq-expect">
        <span>{expectText(item.expect)}</span>
        {item.note && <span className="muted"> · {item.note}</span>}
      </p>
      <p className={`small nq-state nq-state-${item.state}`}>{stateText(item)}</p>
      {hint && <p className="muted small">{hint}</p>}
      {result && (
        <div className="nq-result">
          <span className={`nq-chip nq-${result.outcome}`}>{outcomeWord(result.outcome)}</span>
          {resultLines(result).map((line, i) => <p key={i} className={i === 1 && result.answer?.query_text === line ? "nq-query" : "nq-line"}>{line}</p>)}
        </div>
      )}
      {editing ? (
        <QuestionForm item={item} onDone={() => { setEditing(false); onChange(); }} onCancel={() => setEditing(false)} />
      ) : (
        <div className="nq-actions">
          {canConfirm(item, twoPerson) && <button className="primary" type="button" disabled={busy} onClick={() => act(() => confirmNeeded(item))}>{t("needed.act.confirm")}</button>}
          {adopt != null && <button className="secondary" type="button" disabled={busy} onClick={() => act(() => updateNeeded(item, { expect: { kind: "number", value: adopt } }))}>{t("needed.act.adopt", { number: adopt })}</button>}
          <button className="plain" type="button" disabled={busy} onClick={() => setEditing(true)}>{t("needed.act.edit")}</button>
          {asking ? (
            <span className="nq-ask">
              <span className="small">{t("needed.act.confirmDelete")}</span>
              <button className="danger" type="button" disabled={busy} onClick={() => act(() => deleteNeeded(item))}>{t("needed.act.delete")}</button>
              <button className="plain" type="button" onClick={() => setAsking(false)}>{t("needed.form.cancel")}</button>
            </span>
          ) : (
            <button className="plain" type="button" disabled={busy} onClick={() => setAsking(true)}>{t("needed.act.delete")}</button>
          )}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </li>
  );
}

/** A new question, or one being changed: the words, what it should give (not known yet, a number, or that it must be refused) and where the number comes from. */
function QuestionForm({ item, onDone, onCancel }) {
  const t = useT();
  const [question, setQuestion] = useState(item?.question ?? "");
  const [kind, setKind] = useState(item?.expect?.kind ?? "none");
  const [value, setValue] = useState(item?.expect?.kind === "number" ? String(item.expect.value) : "");
  const [note, setNote] = useState(item?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const fields = { question, expect: expectPayload({ kind, value }), note: note.trim() || null };
    try {
      if (item) await updateNeeded(item, fields);
      else await addNeeded(fields);
      if (!item) {
        setQuestion("");
        setKind("none");
        setValue("");
        setNote("");
      }
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className={item ? "nq-form" : "card nq-form"} onSubmit={save}>
      {!item && <h2>{t("needed.form.title")}</h2>}
      <label className="field">
        <span className="caption">{t("needed.form.question")}</span>
        <textarea rows={2} maxLength={MAX_QUESTION} placeholder={t("needed.form.questionPlaceholder")} value={question} onChange={(e) => setQuestion(e.target.value)} />
      </label>
      <fieldset className="nq-kinds">
        <legend className="caption">{t("needed.form.expect")}</legend>
        {["none", "number", "refused"].map((k) => (
          <label key={k} className="nq-kind">
            <input type="radio" name={`kind-${item?.id ?? "new"}`} value={k} checked={kind === k} onChange={() => setKind(k)} />
            <span>{t(`needed.form.kind.${k}`)}</span>
          </label>
        ))}
      </fieldset>
      {kind === "number" && (
        <label className="field">
          <span className="caption">{t("needed.form.value")}</span>
          <input type="text" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
      )}
      <label className="field">
        <span className="caption">{t("needed.form.note")}</span>
        <input type="text" maxLength={MAX_NOTE} placeholder={t("needed.form.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {item && <p className="muted small">{t("needed.form.changeNote")}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="nq-actions">
        <button className="primary" type="submit" disabled={busy || !question.trim() || (kind === "number" && !value.trim())}>
          {item ? (busy ? t("needed.form.saving") : t("needed.form.save")) : busy ? t("needed.form.adding") : t("needed.form.add")}
        </button>
        {onCancel && <button className="plain" type="button" onClick={onCancel}>{t("needed.form.cancel")}</button>}
      </div>
    </form>
  );
}
