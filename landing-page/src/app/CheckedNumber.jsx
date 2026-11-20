import React, { useId, useState } from "react";
import { getAnswerCheck, recordCheck } from "./api.js";
import { answerNumber, checkDetail, checkLine, checkWord } from "./checkedModel.js";
import { useT } from "./i18n/index.js";
import { useLoad } from "./useLoad.js";
import "./checked.css";

/** A checked number as its reader is told: the mark (一致 / 变了 / 拒答 / 不一致), who checked it when, and for a builder the team's number, its source and what moved or why it refuses. */
export function CheckMark({ check }) {
  const t = useT();
  const detail = checkDetail(check);
  return (
    <div className="ck">
      <p className="ck-head">
        <span className={`ck-chip ck-${check.status}`}>{t("boards.check.mark", { word: checkWord(check.status) })}</span>
        <span className="ck-line">{checkLine(check)}</span>
      </p>
      {detail && <p className="ck-detail">{detail}</p>}
    </div>
  );
}

/** A builder's button to mark the number shown as checked (or check it again), and its small form: the number the team trusts (the one shown unless typed) and where it comes from. */
export function CheckForm({ number, target, again, onDone }) {
  const t = useT();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!open) {
    return <button type="button" className="plain ck-open" onClick={() => { setValue(String(number)); setError(""); setOpen(true); }}>{again ? t("boards.check.again") : t("boards.check.open")}</button>;
  }
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const check = await recordCheck({ ...target, value, note });
      setOpen(false);
      setNote("");
      onDone?.(check);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="ck-form" onSubmit={save}>
      <label className="field">
        <span className="caption">{t("boards.check.value")}</span>
        <input type="text" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} aria-describedby={`${id}-hint`} />
      </label>
      <p id={`${id}-hint`} className="muted small">{t("boards.check.valueHint")}</p>
      <label className="field">
        <span className="caption">{t("boards.check.note")}</span>
        <input type="text" maxLength={120} placeholder={t("boards.check.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="ck-actions">
        <button className="primary" type="submit" disabled={busy || !note.trim()}>{busy ? t("boards.check.saving") : t("boards.check.save")}</button>
        <button type="button" className="plain" onClick={() => setOpen(false)}>{t("boards.check.cancel")}</button>
      </div>
    </form>
  );
}

/** Under one of the person's own saved answers that is one number (builders): its check, worked out again by the service, and the button to check it (again). Nothing under anything else. */
export function AnswerCheck({ record }) {
  const number = answerNumber(record);
  return number == null ? null : <SavedAnswerCheck id={record.id} number={number} />;
}

function SavedAnswerCheck({ id, number }) {
  const [state, reload] = useLoad(() => getAnswerCheck(id), [id]);
  if (!state.data) return null;
  const check = state.data.check;
  return (
    <>
      {check && <CheckMark check={check} />}
      <CheckForm number={number} target={{ question: id }} again={Boolean(check)} onDone={reload} />
    </>
  );
}
