import React, { useEffect, useRef, useState } from "react";
import { checkExpression, getPipelineOptions, trialExpression } from "./api.js";
import { typeLabel } from "./format.js";
import { SIMPLE_OPERATORS, fieldRef, insertAt, simpleExpression } from "./pipelineModel.js";
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
        <code>{value || <span className="faint">还没有写表达式</span>}</code>
        <button className="secondary" onClick={show}>打开表达式编辑器</button>
      </div>
      {open && (
        <dialog ref={ref} className="upload wide-dialog" onCancel={(e) => { e.preventDefault(); close(); }}>
          <div className="dialog-body">
            <h2>表达式</h2>
            <div className="expr-columns">
              <div className="expr-main">
                <label className="caption" htmlFor="expr-text">表达式</label>
                <textarea id="expr-text" ref={area} value={text} rows={5} spellCheck={false} onChange={(e) => { setText(e.target.value); setChecked(null); }} />
                <div className="inline">
                  <button className="secondary" onClick={() => run(() => checkExpression(where.name, where.spec, where.stepId, where.index, text), setChecked)}>校验</button>
                  <button className="secondary" onClick={() => run(() => trialExpression(where.name, where.spec, where.stepId, where.index, text), setTrial)}>试算</button>
                </div>
                {checked && (checked.ok
                  ? <p className="ok">表达式没有问题，结果是{typeLabel(checked.column_type)}</p>
                  : checked.errors.map((e, i) => <p key={i} className="error">{e.message}{e.pos ? `（第 ${e.pos + 1} 个字符）` : ""}</p>))}
              </div>
              <div className="expr-list" aria-label="函数">
                <p className="caption">函数，点一下写进表达式</p>
                {options?.functions.map((g) => (
                  <div key={g.group}>
                    <p className="group-name">{g.group}</p>
                    {g.functions.map((f) => <button key={f.name} className="plain fn" title={f.text} onClick={() => insert(f.template)}>{f.name}<span className="muted small">{f.text}</span></button>)}
                  </div>
                ))}
              </div>
              <div className="expr-list" aria-label="字段">
                <p className="caption">字段，点一下写进表达式</p>
                {cols.map((c) => <button key={c.name} className="plain fn" onClick={() => insert(fieldRef(c.name))}>{c.name}<span className="muted small">{typeLabel(c.type)}</span></button>)}
              </div>
            </div>
            <div className="trial">
              <p className="caption">试算：表达式在前 100 行里的结果，只看前 5 行；这是样本，不是全部数据</p>
              {trial?.ok === false && trial.errors.map((e, i) => <p key={i} className="error">{e.message}</p>)}
              {trial?.ok && (
                <>
                  <p>{trial.rows_tried} 行里 {trial.errors} 行算不出结果（所用的字段都有值，结果却是空）</p>
                  <div className="table-wrap">
                    <table>
                      <thead><tr>{Object.keys(trial.rows[0]?.fields ?? {}).map((f) => <th key={f}>{f}</th>)}<th>结果</th></tr></thead>
                      <tbody>{trial.rows.slice(0, 5).map((r, i) => <tr key={i}>{Object.values(r.fields).map((v, k) => <td key={k}>{String(v ?? "空")}</td>)}<td><strong>{String(r.value ?? "空")}</strong></td></tr>)}</tbody>
                    </table>
                  </div>
                  {trial.notices.map((n, i) => <p key={i} className="warn">{n.text}</p>)}
                </>
              )}
            </div>
            <div className="simple">
              <p className="caption">不想写表达式：选两边和运算</p>
              <div className="inline wide">
                <Select label="字段 A" value={simple.left} onChange={(left) => setSimple({ ...simple, left })}>
                  <option value="">字段 A</option>
                  {cols.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                </Select>
                <Select label="运算" value={simple.op} onChange={(op) => setSimple({ ...simple, op })}>
                  {SIMPLE_OPERATORS.map((o) => <option key={o} value={o}>{o}</option>)}
                </Select>
                <Select label="右边是字段还是数字" value={simple.rightIsField ? "field" : "number"} onChange={(k) => setSimple({ ...simple, rightIsField: k === "field", right: "" })}>
                  <option value="number">数字</option>
                  <option value="field">字段</option>
                </Select>
                {simple.rightIsField ? (
                  <Select label="字段 B" value={simple.right} onChange={(right) => setSimple({ ...simple, right })}>
                    <option value="">字段 B</option>
                    {cols.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </Select>
                ) : <input type="text" aria-label="数字" value={simple.right} onChange={(e) => setSimple({ ...simple, right: e.target.value })} />}
                <button className="secondary" disabled={!written} onClick={() => { setText(written); setChecked(null); }}>写成表达式</button>
              </div>
              {written && <p className="muted small">{written}</p>}
            </div>
          </div>
          <div className="actions">
            {error ? <span className="error">{error}</span> : <span></span>}
            <button className="plain" onClick={close}>取消</button>
            <button className="primary" onClick={() => { onChange(text); close(); }}>用这个表达式</button>
          </div>
        </dialog>
      )}
    </div>
  );
}
