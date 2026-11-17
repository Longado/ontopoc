import React, { useEffect, useRef, useState } from "react";
import { checkExpression, getPipelineOptions, trialExpression } from "./api.js";
import { typeLabel } from "./format.js";
import { SIMPLE_OPERATORS, fieldRef, insertAt, simpleExpression } from "./pipelineModel.js";
import { t } from "./i18n/index.js";
import { Select } from "./Select.jsx";

let optionsCache = null;
const loadOptions = () => (optionsCache ??= getPipelineOptions().catch((e) => {
  optionsCache = null;
  throw e;
}));

/** The expression of an operator: its text here, and a dialog with the three columns (expression, functions, fields), a 试算 strip on the first rows and the simple form. */
export function ExpressionEditor({ where, cols, value, onChange }) {
  const ref = useRef(null);
  const area = useRef(null);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(value);
  const [options, setOptions] = useState(null);
  const [checked, setChecked] = useState(null);
  const [trial, setTrial] = useState(null);
  const [error, setError] = useState("");
  const [simple, setSimple] = useState({ left: "", op: "*", right: "", rightIsField: false });
  useEffect(() => {
    if (open) ref.current.showModal();
  }, [open]);
  const show = () => {
    setText(value);
    setChecked(null);
    setTrial(null);
    setError("");
    setOpen(true);
    loadOptions().then(setOptions, (e) => setError(e.message));
  };
  const close = () => {
    ref.current.close();
    setOpen(false);
  };
  const insert = (what) => {
    const el = area.current;
    const at = insertAt(text, el?.selectionStart, el?.selectionEnd, what);
    setText(at.text);
    setChecked(null);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at.caret, at.caret);
    });
  };
  const run = async (go, set) => {
    setError("");
    try {
      set(await go());
    } catch (e) {
      setError(e.message);
    }
  };
  const written = simpleExpression(simple);
  return (
    <div className="expression">
      <div className="expression-line">
        <code>{value || <span className="faint">{t("steps.expr.none")}</span>}</code>
        <button className="secondary" onClick={show}>{t("steps.expr.open")}</button>
      </div>
      {open && (
        <dialog ref={ref} className="upload wide-dialog" onCancel={(e) => { e.preventDefault(); close(); }}>
          <div className="dialog-body">
            <h2>{t("steps.expr.title")}</h2>
            <div className="expr-columns">
              <div className="expr-main">
                <label className="caption" htmlFor="expr-text">{t("steps.expr.title")}</label>
                <textarea id="expr-text" ref={area} value={text} rows={5} spellCheck={false} onChange={(e) => { setText(e.target.value); setChecked(null); }} />
                <div className="inline">
                  <button className="secondary" onClick={() => run(() => checkExpression(where.name, where.spec, where.stepId, where.index, text), setChecked)}>{t("steps.expr.check")}</button>
                  <button className="secondary" onClick={() => run(() => trialExpression(where.name, where.spec, where.stepId, where.index, text), setTrial)}>{t("steps.expr.trial")}</button>
                </div>
                {checked && (checked.ok
                  ? <p className="ok">{t("steps.expr.ok", { type: typeLabel(checked.column_type) })}</p>
                  : checked.errors.map((e, i) => <p key={i} className="error">{e.message}{e.pos ? t("steps.expr.pos", { n: e.pos + 1 }) : ""}</p>))}
              </div>
              <div className="expr-list" aria-label={t("steps.expr.functions")}>
                <p className="caption">{t("steps.expr.functionsHint")}</p>
                {options?.functions.map((g) => (
                  <div key={g.group}>
                    <p className="group-name">{g.group}</p>
                    {g.functions.map((f) => <button key={f.name} className="plain fn" title={f.text} onClick={() => insert(f.template)}>{f.name}<span className="muted small">{f.text}</span></button>)}
                  </div>
                ))}
              </div>
              <div className="expr-list" aria-label={t("steps.expr.fields")}>
                <p className="caption">{t("steps.expr.fieldsHint")}</p>
                {cols.map((c) => <button key={c.name} className="plain fn" onClick={() => insert(fieldRef(c.name))}>{c.name}<span className="muted small">{typeLabel(c.type)}</span></button>)}
              </div>
            </div>
            <div className="trial">
              <p className="caption">{t("steps.expr.trialHint")}</p>
              {trial?.ok === false && trial.errors.map((e, i) => <p key={i} className="error">{e.message}</p>)}
              {trial?.ok && (
                <>
                  <p>{t("steps.expr.tried", { tried: trial.rows_tried, errors: trial.errors })}</p>
                  <div className="table-wrap">
                    <table>
                      <thead><tr>{Object.keys(trial.rows[0]?.fields ?? {}).map((f) => <th key={f}>{f}</th>)}<th>{t("steps.expr.result")}</th></tr></thead>
                      <tbody>{trial.rows.slice(0, 5).map((r, i) => <tr key={i}>{Object.values(r.fields).map((v, k) => <td key={k}>{String(v ?? t("steps.expr.null"))}</td>)}<td><strong>{String(r.value ?? t("steps.expr.null"))}</strong></td></tr>)}</tbody>
                    </table>
                  </div>
                  {trial.notices.map((n, i) => <p key={i} className="warn">{n.text}</p>)}
                </>
              )}
            </div>
            <div className="simple">
              <p className="caption">{t("steps.expr.simple")}</p>
              <div className="inline wide">
                <Select label={t("steps.expr.fieldA")} value={simple.left} onChange={(left) => setSimple({ ...simple, left })}>
                  <option value="">{t("steps.expr.fieldA")}</option>
                  {cols.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                </Select>
                <Select label={t("steps.expr.operator")} value={simple.op} onChange={(op) => setSimple({ ...simple, op })}>
                  {SIMPLE_OPERATORS.map((o) => <option key={o} value={o}>{o}</option>)}
                </Select>
                <Select label={t("steps.expr.rightKind")} value={simple.rightIsField ? "field" : "number"} onChange={(k) => setSimple({ ...simple, rightIsField: k === "field", right: "" })}>
                  <option value="number">{t("steps.expr.number")}</option>
                  <option value="field">{t("steps.expr.fields")}</option>
                </Select>
                {simple.rightIsField ? (
                  <Select label={t("steps.expr.fieldB")} value={simple.right} onChange={(right) => setSimple({ ...simple, right })}>
                    <option value="">{t("steps.expr.fieldB")}</option>
                    {cols.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </Select>
                ) : <input type="text" aria-label={t("steps.expr.number")} value={simple.right} onChange={(e) => setSimple({ ...simple, right: e.target.value })} />}
                <button className="secondary" disabled={!written} onClick={() => { setText(written); setChecked(null); }}>{t("steps.expr.write")}</button>
              </div>
              {written && <p className="muted small">{written}</p>}
            </div>
          </div>
          <div className="actions">
            {error ? <span className="error">{error}</span> : <span></span>}
            <button className="plain" onClick={close}>{t("steps.expr.cancel")}</button>
            <button className="primary" onClick={() => { onChange(text); close(); }}>{t("steps.expr.use")}</button>
          </div>
        </dialog>
      )}
    </div>
  );
}
