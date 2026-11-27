import React, { useState } from "react";
import { confirmView, createView, getTypeViews } from "./api.js";
import { Select } from "./Select.jsx";
import { State } from "./TypesPage.jsx";
import { t } from "./i18n/index.js";
import { alsoCalled, confirmersText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { FORMULA_OP, OP_LABEL, confirmWords, emptyViewForm, formulaOption, newValueChoices, newValueText, rowsText, viewPayload, viewProblem, viewWaitingText } from "./viewModel.js";

function ViewCard({ view, mayBuild, onChanged }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState({});   // {"column|value": "in" | "out"}: what to do with each new value
  const choices = newValueChoices(view.new_values, picked);
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmView(view.id, view.version, view.seen, choices);
      onChanged();
    } catch (e) {
      setError(e.message);
      if (e.code === 409) onChanged();   // what was read has moved: show what is there now
    }
    setBusy(false);
  };
  const line = stateLine(view, t("types.view.noun"));
  return (
    <section className="card">
      <div className="page-head">
        <h2 className="item-title">{view.name}</h2>
        <State item={view} />
      </div>
      {alsoCalled(view.other_names) && <p className="muted small">{alsoCalled(view.other_names)}</p>}
      <p>{view.says}</p>
      {view.caliber && <p className="small">{view.caliber}</p>}
      <p className="facts">
        <span>{view.problems.length ? t("types.view.unreadable") : t("types.view.keeps", { rows: rowsText(view) })}</span>
        {view.anchored && view.state === "needs_look" && <span className="muted">{t("types.view.atConfirm", { rows: view.anchored.rows, of: view.anchored.of })}</span>}
        {view.description && <span>{view.description}</span>}
      </p>
      {view.problems.map((p) => <p key={p} className="warn">{p}</p>)}
      {line && <p className="muted small">{line}</p>}
      {viewWaitingText(view) && <p className="warn">{viewWaitingText(view)}</p>}
      {confirmersText(view) && <p className="muted small">{confirmersText(view)}</p>}
      {view.state === "needs_look" && view.reason && (
        <div className="reason">
          <strong>{t("types.page.whyLook")}</strong>
          <p>{view.reason}</p>
        </div>
      )}
      {mayBuild && view.can_confirm && view.new_values?.map((v) => {
        const key = `${v.column}|${v.value}`;
        return (
          <fieldset key={key} className="new-value">
            <legend>{newValueText(v)}</legend>
            <label><input type="radio" name={`new-${view.id}-${key}`} checked={picked[key] === "in"} onChange={() => setPicked({ ...picked, [key]: "in" })} /> {t("types.view.include")}</label>
            <label><input type="radio" name={`new-${view.id}-${key}`} checked={picked[key] === "out"} onChange={() => setPicked({ ...picked, [key]: "out" })} /> {t("types.view.exclude")}</label>
          </fieldset>
        );
      })}
      {mayBuild && view.can_confirm && <div className="inline"><button className="primary" onClick={confirm} disabled={busy || !choices}>{confirmWords(choices)}</button></div>}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

/** One row of conditions: a code column, is / is not, and one of the meanings written for it. */
function Condition({ row, codes, onChange, onRemove, only }) {
  const labels = codes.find((c) => c.column === row.column)?.labels ?? [];
  return (
    <div className="inline wide">
      <Select label={t("types.derived.condColumn")} value={row.column} onChange={(column) => onChange({ ...row, column, label: "" })}>
        <option value="">{t("types.derived.pickColumn")}</option>
        {codes.map((c) => <option key={c.column} value={c.column}>{c.name}</option>)}
      </Select>
      <Select label={t("types.derived.condOp")} value={row.op} onChange={(op) => onChange({ ...row, op })}>
        {Object.entries(OP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </Select>
      <Select label={t("types.derived.condMeaning")} value={row.label} disabled={!row.column} onChange={(label) => onChange({ ...row, label })}>
        <option value="">{t("types.derived.pickMeaning")}</option>
        {labels.map((l) => <option key={l} value={l}>{l}</option>)}
      </Select>
      {!only && <button className="plain" onClick={onRemove}>{t("types.derived.remove")}</button>}
    </div>
  );
}

/** One row comparing a per-row formula (a derived property of this type) with a number. */
function Formula({ row, formulas, onChange, onRemove }) {
  return (
    <div className="inline wide">
      <Select label={t("types.view.formula")} value={row.property} onChange={(property) => onChange({ ...row, property })}>
        <option value="">{t("types.view.pickFormula")}</option>
        {formulas.map((f) => <option key={f.property} value={f.property}>{formulaOption(f)}</option>)}
      </Select>
      <Select label={t("types.derived.condOp")} value={row.op} onChange={(op) => onChange({ ...row, op })}>
        {Object.entries(FORMULA_OP).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </Select>
      <label className="field">
        <span className="caption">{t("types.view.formulaValue")}</span>
        <input type="number" value={row.value} onChange={(e) => onChange({ ...row, value: e.target.value })} />
      </label>
      <button className="plain" onClick={onRemove}>{t("types.derived.remove")}</button>
    </div>
  );
}

function NewView({ type, form: options, onSaved }) {
  const [form, setForm] = useState({ ...emptyViewForm(), otherNames: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const problem = viewProblem(form);
  const orderable = options.columns.filter((c) => c.orderable);
  const toggleKey = (name, on) => setForm({ ...form, latest: { ...form.latest, key: on ? [...form.latest.key, name] : form.latest.key.filter((k) => k !== name) } });
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await createView(viewPayload(type, form));
      setForm({ ...emptyViewForm(), otherNames: "" });
      onSaved();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  return (
    <section>
      <h2 className="section">{t("types.view.newTitle")}</h2>
      <label className="field">
        <span className="caption">{t("types.view.name")}</span>
        <input type="text" value={form.name} maxLength={40} placeholder={t("types.view.namePlaceholder")} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </label>
      <label className="field">
        <span className="caption">{t("types.otherNames")}</span>
        <input type="text" value={form.otherNames} placeholder={t("types.otherNamesPlaceholder")} onChange={(e) => setForm({ ...form, otherNames: e.target.value })} />
        <span className="muted small">{t("types.otherNamesHint")}</span>
      </label>
      <div className="field">
        <span className="caption">{t("types.view.keepOnly")}</span>
        {form.filters.map((row, i) => (
          <Condition key={i} row={row} codes={options.codes} only={form.filters.length === 1}
            onChange={(next) => setForm({ ...form, filters: form.filters.map((r, j) => (j === i ? next : r)) })}
            onRemove={() => setForm({ ...form, filters: form.filters.filter((_, j) => j !== i) })} />
        ))}
        {form.filters.length < 5 && <button className="plain" style={{ alignSelf: "flex-start" }} onClick={() => setForm({ ...form, filters: [...form.filters, { column: "", op: "is_not", label: "" }] })}>{t("types.view.addCondition")}</button>}
        {options.codes.every((c) => !c.labels.length) && <p className="muted small">{t("types.view.noCodes")}</p>}
      </div>
      {options.formulas?.length > 0 && (
        <div className="field">
          <span className="caption">{t("types.view.formulas")}</span>
          {form.derived.map((row, i) => (
            <Formula key={i} row={row} formulas={options.formulas}
              onChange={(next) => setForm({ ...form, derived: form.derived.map((r, j) => (j === i ? next : r)) })}
              onRemove={() => setForm({ ...form, derived: form.derived.filter((_, j) => j !== i) })} />
          ))}
          {form.filters.length + form.derived.length < 5 && <button className="plain" style={{ alignSelf: "flex-start" }} onClick={() => setForm({ ...form, derived: [...form.derived, { property: "", op: "equals", value: "1" }] })}>{t("types.view.addFormula")}</button>}
          <p className="muted small">{t("types.view.formulaNote")}</p>
        </div>
      )}
      <div className="field">
        <label className="check">
          <input type="checkbox" checked={form.latest.on} onChange={(e) => setForm({ ...form, latest: { ...form.latest, on: e.target.checked } })} />
          {t("types.view.latestOn")}
        </label>
        {form.latest.on && (
          <>
            <span className="caption">{t("types.view.idCaption")}</span>
            <div className="inline wide" style={{ flexWrap: "wrap" }}>
              {options.columns.map((c) => (
                <label key={c.name} className="check">
                  <input type="checkbox" checked={form.latest.key.includes(c.name)} onChange={(e) => toggleKey(c.name, e.target.checked)} aria-label={t("types.view.idAria", { name: c.name })} />
                  {c.name}
                </label>
              ))}
            </div>
            <span className="caption">{t("types.view.orderCaption")}</span>
            <Select label={t("types.derived.latestOrder")} value={form.latest.order} onChange={(order) => setForm({ ...form, latest: { ...form.latest, order } })}>
              <option value="">{t("types.derived.pickColumn")}</option>
              {orderable.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </Select>
          </>
        )}
      </div>
      <div className="inline">
        <button className="primary" onClick={save} disabled={busy || !!problem}>{t("types.view.save")}</button>
        {problem && <span className="muted small">{problem}</span>}
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

export function TypeViews({ type, mayBuild }) {
  const [state, reload] = useLoad(() => getTypeViews(type.id), [type.id]);
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">{t("common.loading")}</p>;
  const { views, form } = state.data;
  return (
    <>
      {!views.length && <p className="muted">{t("types.view.empty")}</p>}
      <div className="cards">
        {views.map((v) => <ViewCard key={`${v.id}@${v.version}`} view={v} mayBuild={mayBuild} onChanged={reload} />)}
      </div>
      {mayBuild && form && <NewView type={type.id} form={form} onSaved={reload} />}
    </>
  );
}
