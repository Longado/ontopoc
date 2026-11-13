import { useState } from "react";
import { NewerLink } from "./CodeMeaningForm.jsx";
import { REPEAT_CHOICES, repeatBody, repeatProblem } from "./openItemsModel.js";

/** A repeated key's open item: choose how the rows are read; "只留最新的一行" asks by which column. Nothing is chosen for the person. */
export function RepeatRuleForm({ item, client }) {
  const [form, setForm] = useState({ rule: "", column: "" });
  const problem = repeatProblem(form);
  const columns = item.repeat.columns;
  return <div className="os-repeat">
    <fieldset className="os-repeat-choices">
      <legend className="pr-muted">这些行怎么算</legend>
      {REPEAT_CHOICES.map(([rule, label, hint]) => <label key={rule} className="os-answer-choice">
        <input type="radio" name={`repeat-${item.id}`} checked={form.rule === rule} onChange={() => setForm({ ...form, rule })} />
        <span>{label}<small className="os-code-note">{hint}</small></span>
      </label>)}
    </fieldset>
    {form.rule === "keep_latest" && <label className="os-repeat-column">按哪一列定最新
      <select className="os-select" value={form.column} onChange={(e) => setForm({ ...form, column: e.target.value })}>
        <option value="">{columns.length ? "选一列（只列出数字或日期列）" : "这几行里没有一列能分出先后"}</option>
        {columns.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    </label>}
    {client.newer ? <NewerLink client={client} /> : <div className="os-code-save">
      <label>确认人<input value={client.by} maxLength={40} onChange={(e) => client.setBy(e.target.value)} /></label>
      <button type="button" className="pr-primary" disabled={client.busy || !client.can || Boolean(problem)} title={problem || client.why || undefined}
        onClick={() => client.onSaveRepeat(item, repeatBody(form))}>{client.busy ? "保存中…" : "确认"}</button>
    </div>}
    {client.error?.key === item.id && <p role="alert" className="pr-error">{client.error.text}</p>}
  </div>;
}
