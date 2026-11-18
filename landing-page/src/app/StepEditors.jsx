import React, { useEffect, useRef, useState } from "react";
import { operatorColumns } from "./api.js";
import { LlmEditor } from "./LlmEditor.jsx";
import { FilterForm, OperatorForm } from "./OperatorForms.jsx";
import {
  HOW_LABEL, NULL_KEYS_LABEL, OPERATOR_PARAMS, addOperator, allIssues, catalogView, copyOperator, doubledGroupLines, failureLines, friendlyError, joinVerdictLines, moveOperator, newOperator, suggestJoinKeys,
  branchReaders, newBranchId, operatorName, operatorTitle, readableSteps, removeOperator, renameBranch, setOperator, splitLines, stepTitle, unionLines, updateStep,
} from "./pipelineModel.js";
import { t } from "./i18n/index.js";
import { Select } from "./Select.jsx";

const earlier = (draft, step) => draft.steps.slice(0, draft.steps.findIndex((s) => s.id === step.id));
/** The options of a "reads which step" picker: the steps before this one, a split by its branches. */
const readOptions = (draft, step, skip = []) => readableSteps(earlier(draft, step)).filter((r) => !skip.includes(r.id)).map((r) => <option key={r.id} value={r.id}>{r.label}</option>);

function InputEditor({ step, draft, setDraft, datasets }) {
  const known = datasets.find((d) => d.name === step.dataset);
  const set = (patch) => setDraft(updateStep(draft, step.id, patch));
  return (
    <div className="op-form">
      <div className="field">
        <span className="caption">{t("steps.edit.input.dataset")}</span>
        <Select label={t("steps.edit.input.datasetLabel")} value={step.dataset ?? ""} onChange={(dataset) => set({ dataset, version: undefined })}>
          {!known && <option value={step.dataset ?? ""}>{step.dataset || t("steps.edit.input.pick")}</option>}
          {datasets.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
        </Select>
      </div>
      <div className="field">
        <span className="caption">{t("steps.edit.input.version")}</span>
        <Select label={t("steps.edit.input.versionLabel")} value={step.version ? String(step.version) : ""} onChange={(v) => set({ version: v ? Number(v) : undefined })}>
          <option value="">{known ? t("steps.edit.input.currentN", { version: known.version }) : t("steps.edit.input.current")}</option>
          {known && Array.from({ length: known.version }, (_, i) => known.version - i).map((v) => <option key={v} value={v}>{t("steps.edit.input.pinned", { version: v })}</option>)}
        </Select>
      </div>
      <p className="hint">{t("steps.edit.input.hint")}</p>
    </div>
  );
}

function JoinEditor({ step, draft, setDraft, nodes }) {
  const columnsOf = (id) => (nodes[id]?.column_types ?? []).map((c) => c.name);
  const left = columnsOf(step.left);
  const right = columnsOf(step.right);
  const set = (patch) => setDraft(updateStep(draft, step.id, patch));
  const setPair = (i, pair) => set({ on: step.on.map((p, k) => (k === i ? pair : p)) });
  const chosen = step.right_columns ?? right;
  const toggleRight = (name, on) => {
    const next = on ? [...chosen, name] : chosen.filter((n) => n !== name);
    set({ right_columns: right.every((n) => next.includes(n)) ? undefined : right.filter((n) => next.includes(n)) });
  };
  const verdict = joinVerdictLines(nodes[step.id]?.join);
  const suggest = suggestJoinKeys(nodes[step.left]?.column_types, nodes[step.right]?.column_types);
  const untouched = step.on.every((p) => !p.left && !p.right);
  useEffect(() => {
    if (untouched && suggest.best) set({ on: [suggest.best] });   // two inputs with a key of the same name: it is put in; the person can change it
  }, [untouched, suggest.best?.left, step.left, step.right]);
  const unused = [suggest.best, ...suggest.others].filter((s) => s && !step.on.some((p) => p.left === s.left && p.right === s.right));
  return (
    <div className="op-form">
      <div className="field"><span className="caption">{t("steps.edit.join.left")}</span>
        <Select label={t("steps.edit.join.left")} value={step.left ?? ""} onChange={(v) => set({ left: v, on: [suggestJoinKeys(nodes[v]?.column_types, nodes[step.right]?.column_types).best ?? { left: "", right: "" }] })}>{readOptions(draft, step)}</Select>
      </div>
      <div className="field"><span className="caption">{t("steps.edit.join.how")}</span>
        <Select label={t("steps.edit.join.how")} value={step.how} onChange={(how) => set({ how })}>
          {Object.entries(HOW_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </div>
      <div className="field"><span className="caption">{t("steps.edit.join.right")}</span>
        <Select label={t("steps.edit.join.right")} value={step.right ?? ""} onChange={(v) => set({ right: v, on: [suggestJoinKeys(nodes[step.left]?.column_types, nodes[v]?.column_types).best ?? { left: "", right: "" }], right_columns: undefined })}>{readOptions(draft, step, [step.left])}</Select>
      </div>
      {step.how === "semi" && <p className="hint">{t("steps.edit.join.semi")}</p>}
      {step.how === "anti" && <p className="hint">{t("steps.edit.join.anti")}</p>}
      <fieldset className="keys">
        <legend>{t("steps.edit.join.keys")}</legend>
        {step.on.map((pair, i) => (
          <div className="inline wide op-row" key={i}>
            <Select label={t("steps.edit.join.leftCol")} value={pair.left} onChange={(v) => setPair(i, { ...pair, left: v })}><option value="">{t("steps.edit.join.leftCol")}</option>{left.map((n) => <option key={n} value={n}>{n}</option>)}</Select>
            <span>=</span>
            <Select label={t("steps.edit.join.rightCol")} value={pair.right} onChange={(v) => setPair(i, { ...pair, right: v })}><option value="">{t("steps.edit.join.rightCol")}</option>{right.map((n) => <option key={n} value={n}>{n}</option>)}</Select>
            <button className="plain" disabled={step.on.length === 1} onClick={() => set({ on: step.on.filter((_, k) => k !== i) })}>{t("steps.edit.delete")}</button>
          </div>
        ))}
        <button className="plain" onClick={() => set({ on: [...step.on, { left: "", right: "" }] })}>{t("steps.edit.join.addPair")}</button>
        {unused.length > 0 && (
          <p className="hint">{t("steps.edit.join.sharedCols")}{unused.map((s) => <button key={s.left} className="plain" onClick={() => set({ on: [...step.on.filter((p) => p.left || p.right), s] })}>{t("steps.edit.join.use", { left: s.left, right: s.right })}</button>)}</p>
        )}
        {untouched && !suggest.best && step.left && step.right && <p className="todo-note">{t("steps.edit.join.noSameKey")}</p>}
      </fieldset>
      <div className="ways">
        {Object.entries(NULL_KEYS_LABEL).map(([k, v]) => (
          <label key={k}><input type="radio" name={`null-${step.id}`} checked={(step.null_keys ?? "no_match") === k} onChange={() => set({ null_keys: k })} />{v}</label>
        ))}
      </div>
      {(step.how === "inner" || step.how === "left") && right.length > 0 && (
        <fieldset className="keys">
          <legend>{t("steps.edit.join.bringRight")}</legend>
          {right.map((n) => <label key={n}><input type="checkbox" checked={chosen.includes(n)} onChange={(e) => toggleRight(n, e.target.checked)} />{n}</label>)}
        </fieldset>
      )}
      {verdict.length > 0 && (
        <div className="verdict">
          <p className="caption">{t("steps.edit.whatItDid")}</p>
          <ul className="plain-list">{verdict.map((l, i) => <li key={i} className={i > 0 && new RegExp(t("steps.edit.join.warnRe"), "i").test(l) ? "warn" : ""}>{l}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

/** The operator forms read the columns an operator sees: fetched again when anything before it changes. */
function OperatorEditor({ name, draft, step, index, onChange }) {
  const before = updateStep(draft, step.id, { operators: step.operators.slice(0, index) });
  const key = JSON.stringify(before);
  const [state, setState] = useState({ key: "", cols: null, error: "" });
  useEffect(() => {
    let live = true;
    operatorColumns(name, before, step.id, null).then((b) => live && setState({ key, cols: b.columns, error: "" }), (e) => live && setState({ key, cols: null, error: e.message }));
    return () => { live = false; };
  }, [key]);
  if (state.error) return Object.keys(allIssues(draft.steps)).length ? <p className="todo-note">{t("steps.edit.op.upstream")}</p> : <p className="error">{t("steps.edit.op.cantRead", { error: friendlyError(state.error, draft.steps) })}</p>;
  if (!state.cols) return <p className="muted">{t("steps.edit.loading")}</p>;
  return <OperatorForm op={step.operators[index]} cols={state.cols} onChange={onChange} where={{ name, spec: before, stepId: step.id, index, from: step.from }} />;
}

function OperatorPicker({ catalog, onPick, onClose }) {
  const ref = useRef(null);
  const [category, setCategory] = useState(null);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState(null);
  useEffect(() => { ref.current.showModal(); }, []);
  const { categories, items } = catalogView(catalog, category, query);
  const shown = items.find((c) => c.op === picked) ?? items[0];
  return (
    <dialog ref={ref} className="upload wide-dialog" onCancel={(e) => { e.preventDefault(); onClose(); }}>
      <div className="dialog-body">
        <h2>{t("steps.edit.picker.title")}</h2>
        <input type="text" aria-label={t("steps.edit.picker.searchLabel")} placeholder={t("steps.edit.picker.searchPh")} value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="picker">
          <div className="picker-cats" role="tablist" aria-label={t("steps.edit.picker.cats")}>
            <button role="tab" aria-selected={category === null} className={`plain${category === null ? " on" : ""}`} onClick={() => setCategory(null)}>{t("steps.edit.picker.all")}</button>
            {categories.map((c) => <button key={c} role="tab" aria-selected={category === c} className={`plain${category === c ? " on" : ""}`} onClick={() => setCategory(c)}>{c}</button>)}
          </div>
          <ul className="picker-list">
            {items.map((c) => <li key={c.op}><button className={`plain${shown?.op === c.op ? " on" : ""}`} onClick={() => setPicked(c.op)}>{c.name}</button></li>)}
            {!items.length && <li className="muted">{t("steps.edit.picker.none")}</li>}
          </ul>
          <div className="picker-detail">
            {shown ? (
              <>
                <h3>{shown.name}</h3>
                <p>{shown.text}</p>
                <p className="caption">{t("steps.edit.picker.params")}</p>
                <ul className="plain-list">{(OPERATOR_PARAMS[shown.op] ?? []).map((p) => <li key={p}>{p}</li>)}</ul>
              </>
            ) : <p className="muted">{t("steps.edit.picker.choose")}</p>}
          </div>
        </div>
      </div>
      <div className="actions">
        <span></span>
        <button className="plain" onClick={onClose}>{t("steps.edit.cancel")}</button>
        <button className="primary" disabled={!shown} onClick={() => onPick(shown.op)}>{t("steps.edit.picker.add", { name: shown ? shown.name : "" })}</button>
      </div>
    </dialog>
  );
}

function OperatorReport({ report }) {
  if (!report) return null;
  const failed = report.failed ?? [];
  return (
    <div className="op-report">
      {report.text && <p className="muted small">{report.text}</p>}
      {failed.length > 0 && <ul className="plain-list small warn">{failed.slice(0, 10).map((f) => <li key={f.row}>{t("steps.edit.report.row", { row: f.row, value: f.value })}</li>)}{failed.length > 10 && <li>{t("steps.edit.report.more", { count: failed.length - 10 })}</li>}</ul>}
      {report.error_rows?.length > 0 && <p className="warn small">{t("steps.edit.report.errorRows", { rows: report.error_rows.slice(0, 10).join(", "), more: report.error_rows.length > 10 ? t("steps.edit.report.etc") : "" })}</p>}
      {(report.notices ?? []).map((n, i) => <p key={i} className="warn small">{n.text}</p>)}
      {doubledGroupLines(report).map((l, i) => <p key={i} className="warn small">{l}</p>)}
    </div>
  );
}

function TransformEditor({ step, draft, setDraft, nodes, name, catalog, onPreviewTo }) {
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const reports = nodes[step.id]?.operators ?? [];
  const apply = (spec) => setDraft(spec);
  return (
    <div className="op-form">
      <div className="field">
        <span className="caption">{t("steps.edit.tf.reads")}</span>
        <Select label={t("steps.edit.tf.reads")} value={step.from ?? ""} onChange={(from) => { setEditing(null); setDraft(updateStep(draft, step.id, { from })); }}>{readOptions(draft, step)}</Select>
      </div>
      <ol className="op-stack">
        {step.operators.map((op, i) => (
          <li key={i} className="op-card">
            <div className="op-head">
              <span className="op-no">{i + 1}</span>
              <strong>{operatorName(op)}</strong>
              {reports[i]?.affected != null && <span className="op-affect">{t("steps.edit.tf.affects", { count: reports[i].affected.toLocaleString("en-US") })}</span>}
            </div>
            <p className="muted">{operatorTitle(op)}</p>
            <div className="op-buttons">
              <button className="plain" aria-expanded={editing === i} onClick={() => setEditing(editing === i ? null : i)}>{editing === i ? t("steps.edit.tf.collapse") : t("steps.edit.tf.edit")}</button>
              <button className="plain" onClick={() => onPreviewTo(i)}>{t("steps.edit.tf.preview")}</button>
              <button className="plain" onClick={() => apply(copyOperator(draft, step.id, i))}>{t("steps.edit.tf.copy")}</button>
              <button className="plain" onClick={() => { setEditing(null); apply(removeOperator(draft, step.id, i)); }}>{t("steps.edit.delete")}</button>
              <button className="plain" disabled={i === 0} onClick={() => { setEditing(null); apply(moveOperator(draft, step.id, i, -1)); }}>{t("steps.edit.tf.up")}</button>
              <button className="plain" disabled={i === step.operators.length - 1} onClick={() => { setEditing(null); apply(moveOperator(draft, step.id, i, 1)); }}>{t("steps.edit.tf.down")}</button>
            </div>
            {editing === i && <OperatorEditor name={name} draft={draft} step={step} index={i} onChange={(next) => apply(setOperator(draft, step.id, i, next))} />}
            <OperatorReport report={reports[i]} />
          </li>
        ))}
      </ol>
      {!step.operators.length && <p className="muted">{t("steps.edit.tf.empty")}</p>}
      <button className="secondary" onClick={() => setAdding(true)}>{t("steps.edit.tf.add")}</button>
      {adding && <OperatorPicker catalog={catalog} onClose={() => setAdding(false)} onPick={(kind) => { setAdding(false); apply(addOperator(draft, step.id, newOperator(kind))); setEditing(step.operators.length); }} />}
    </div>
  );
}

/** 合并: the steps whose rows are stacked, matched by column name; what to do with a column some of them lack; an optional column that says where each row came from. */
function UnionEditor({ step, draft, setDraft, nodes }) {
  const set = (patch) => setDraft(updateStep(draft, step.id, patch));
  const inputs = step.inputs ?? [];
  const readable = readableSteps(earlier(draft, step));
  const options = [...readable, ...inputs.filter((i) => !readable.some((r) => r.id === i)).map((i) => ({ id: i, label: t("steps.edit.un.cantRead", { id: i }) }))];
  const toggle = (id, on) => set({ inputs: on ? [...inputs, id] : inputs.filter((i) => i !== id) });
  const lines = unionLines(nodes[step.id]?.union);
  return (
    <div className="op-form">
      <fieldset className="keys">
        <legend>{t("steps.edit.un.legend")}</legend>
        {options.map((r) => <label key={r.id}><input type="checkbox" checked={inputs.includes(r.id)} onChange={(e) => toggle(r.id, e.target.checked)} />{r.label}</label>)}
      </fieldset>
      <div className="ways">
        <label><input type="radio" name={`missing-${step.id}`} checked={(step.missing ?? "error") === "error"} onChange={() => set({ missing: "error" })} />{t("steps.edit.un.missingError")}</label>
        <label><input type="radio" name={`missing-${step.id}`} checked={step.missing === "empty"} onChange={() => set({ missing: "empty" })} />{t("steps.edit.un.missingEmpty")}</label>
      </div>
      <label className="field"><span className="caption">{t("steps.edit.un.source")}</span>
        <input type="text" value={step.source_column ?? ""} placeholder={t("steps.edit.un.sourcePh")} onChange={(e) => set({ source_column: e.target.value || undefined })} />
      </label>
      <p className="hint">{t("steps.edit.un.hint")}</p>
      {lines.length > 0 && (
        <div className="verdict">
          <p className="caption">{t("steps.edit.whatItDid")}</p>
          <ul className="plain-list">{lines.map((l) => <li key={l} className={new RegExp(t("steps.edit.un.warnRe"), "i").test(l) ? "warn" : ""}>{l}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

/** The columns a split's conditions read: what its source step leaves, with the meanings of its code columns (asked the way a transform's first operator asks). */
function useSourceColumns(name, draft, step) {
  const probe = `__cols_${step.id}`;
  const spec = { ...draft, steps: [...earlier(draft, step), { id: probe, type: "transform", from: step.from, operators: [] }] };
  const key = JSON.stringify(spec);
  const [state, setState] = useState({ cols: null, error: "" });
  useEffect(() => {
    let live = true;
    if (!step.from) return undefined;
    operatorColumns(name, spec, probe, null).then((b) => live && setState({ cols: b.columns, error: "" }), (e) => live && setState({ cols: null, error: e.message }));
    return () => { live = false; };
  }, [key]);
  return state;
}

/** A branch's name, renamed when the person leaves the box or presses Enter: an empty name or one already taken goes back to what it was. */
function BranchName({ label, id, onRename }) {
  const [text, setText] = useState(id);
  useEffect(() => setText(id), [id]);
  const done = () => {
    if (text.trim() && text !== id) onRename(text.trim());
    setText(id);   // a refused name goes back; an accepted one comes back as the new id
  };
  return <input type="text" aria-label={label} value={text} onChange={(e) => setText(e.target.value)} onBlur={done} onKeyDown={(e) => e.key === "Enter" && done()} />;
}

/** 拆分: each row goes to the first branch whose condition holds; a last 其余 branch takes the rest. Each branch has a name later steps read. */
function SplitEditor({ step, draft, setDraft, nodes, name }) {
  const set = (patch) => setDraft(updateStep(draft, step.id, patch));
  const branches = step.branches ?? [];
  const setBranch = (i, patch) => set({ branches: branches.map((b, k) => (k === i ? { ...b, ...patch } : b)) });
  const ruled = branches.filter((b) => !b.rest);
  const rest = branches.find((b) => b.rest);
  const source = useSourceColumns(name, draft, step);
  const readBy = (id) => branchReaders(draft.steps, id);
  const lines = splitLines(nodes[step.id]?.split);
  const withRest = (list) => [...list, ...(rest ? [rest] : [])];
  return (
    <div className="op-form">
      <div className="field"><span className="caption">{t("steps.edit.sp.source")}</span>
        <Select label={t("steps.edit.tf.reads")} value={step.from ?? ""} onChange={(from) => set({ from })}>{readOptions(draft, step)}</Select>
      </div>
      {source.error && <p className="error">{t("steps.edit.sp.error", { error: friendlyError(source.error, draft.steps) })}</p>}
      {ruled.map((b, i) => (
        <fieldset className="component" key={i}>
          <span className="caption">{t("steps.edit.sp.branchName", { n: i + 1 })}</span>
          <div className="inline wide">
            <BranchName label={t("steps.edit.sp.branchLabel", { n: i + 1 })} id={b.id} onRename={(to) => setDraft(renameBranch(draft, step.id, b.id, to))} />
            <button className="plain" disabled={ruled.length === 1 || readBy(b.id).length > 0} title={readBy(b.id).length ? t("steps.edit.sp.readBy", { names: readBy(b.id).join(", ") }) : ""} onClick={() => set({ branches: branches.filter((x) => x !== b) })}>{t("steps.edit.sp.dropBranch")}</button>
          </div>
          {source.cols && <FilterForm op={{ where: b.where ?? { all: [] } }} cols={source.cols} onChange={(op) => setBranch(branches.indexOf(b), { where: op.where })} lead={t("steps.edit.sp.lead")} tail={t("steps.edit.sp.tail")} />}
        </fieldset>
      ))}
      <div className="inline">
        <button className="plain" disabled={branches.length >= 10} onClick={() => set({ branches: withRest([...ruled, { id: newBranchId(step, draft.steps), where: { all: [{ column: "", cmp: "eq", value: "" }] } }]) })}>{t("steps.edit.sp.addBranch")}</button>
        <label className="check" title={rest && readBy(rest.id).length ? t("steps.edit.sp.readRest", { names: readBy(rest.id).join(", ") }) : ""}><input type="checkbox" checked={Boolean(rest)} disabled={Boolean(rest) && readBy(rest.id).length > 0} onChange={(e) => set({ branches: e.target.checked ? [...ruled, { id: `${step.id}_${t("steps.edit.sp.restSuffix")}`, rest: true }] : ruled })} />{t("steps.edit.sp.restCheck")}</label>
      </div>
      {rest && (
        <label className="field"><span className="caption">{t("steps.edit.sp.restName")}</span>
          <BranchName label={t("steps.edit.sp.restName")} id={rest.id} onRename={(to) => setDraft(renameBranch(draft, step.id, rest.id, to))} />
        </label>
      )}
      <p className="hint">{t("steps.edit.sp.hint1")} {rest ? "" : `${t("steps.edit.sp.hint2")} `}{t("steps.edit.sp.hint3")}</p>
      {lines.length > 0 && (
        <div className="verdict">
          <p className="caption">{t("steps.edit.whatItDid")}</p>
          <ul className="plain-list">{lines.map((l) => <li key={l} className={new RegExp(t("steps.edit.sp.warnRe"), "i").test(l) ? "warn" : ""}>{l}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function OutputEditor({ step, draft, setDraft, nodes }) {
  const node = nodes[step.id];
  const source = nodes[step.from]?.column_types ?? [];
  const names = source.map((c) => c.name);
  const set = (patch) => setDraft(updateStep(draft, step.id, patch));
  const kept = step.columns ?? names;
  const toggle = (n, on) => {
    const next = on ? [...kept, n] : kept.filter((k) => k !== n);
    set({ columns: names.every((x) => next.includes(x)) ? undefined : names.filter((x) => next.includes(x)) });
  };
  const key = step.key?.columns ?? [];
  const setKey = (columns) => set({ key: columns.length ? { ...step.key, columns } : undefined });
  const out = node?.output;
  const status = out?.status;
  return (
    <div className="op-form">
      <div className="field"><span className="caption">{t("steps.edit.tf.reads")}</span>
        <Select label={t("steps.edit.tf.reads")} value={step.from ?? ""} onChange={(from) => set({ from, columns: undefined, key: undefined })}>{readOptions(draft, step)}</Select>
      </div>
      <label className="field"><span className="caption">{t("steps.edit.out.name")}</span>
        <input type="text" value={step.name ?? ""} onChange={(e) => set({ name: e.target.value })} />
      </label>
      {status && <p className={`output-status status-${status.state}`}>{status.text}</p>}
      <fieldset className="keys">
        <legend>{t("steps.edit.out.keep")}</legend>
        {names.map((n) => <label key={n}><input type="checkbox" checked={kept.includes(n)} onChange={(e) => toggle(n, e.target.checked)} />{n}</label>)}
      </fieldset>
      <fieldset className="keys">
        <legend>{t("steps.edit.out.key")}</legend>
        {names.map((n) => <label key={n}><input type="checkbox" checked={key.includes(n)} onChange={(e) => setKey(e.target.checked ? [...key, n] : key.filter((k) => k !== n))} />{n}</label>)}
      </fieldset>
      {key.length > 1 && (
        <div className="inline wide">
          <label className="field"><span className="caption">{t("steps.edit.out.sep")}</span><input type="text" value={step.key.separator ?? "|"} maxLength={10} onChange={(e) => set({ key: { ...step.key, separator: e.target.value } })} /></label>
          <label className="field"><span className="caption">{t("steps.edit.out.as")}</span><input type="text" value={step.key.as ?? ""} placeholder={t("steps.edit.out.asPh")} onChange={(e) => set({ key: { ...step.key, as: e.target.value || undefined } })} /></label>
        </div>
      )}
      {out?.duplicate_keys && (
        <div className="verdict">
          <p className="bad">{t("steps.edit.out.dupKeys", { count: out.duplicate_keys.count, extra: out.duplicate_keys.extra_rows })}</p>
          <ul className="plain-list small">{out.duplicate_keys.examples.map((e, i) => <li key={i}>{t("steps.edit.out.dupExample", { key: e.key.join(" + "), rows: e.rows })}</li>)}</ul>
        </div>
      )}
      {out?.empty_keys > 0 && <p className="bad">{t("steps.edit.out.emptyKeys", { count: out.empty_keys })}</p>}
      {out?.dropped.length > 0 && <p className="muted small">{t("steps.edit.out.dropped", { names: out.dropped.join(", ") })}</p>}
    </div>
  );
}

/** The editor on the right: by the kind of the selected step. `onPreviewTo(i)` shows the node's rows up to operator i in the bottom panel. */
export function StepEditor({ step, draft, setDraft, nodes, datasets, name, catalog, options, dirty, onPreviewTo }) {
  if (!step) return <p className="muted pl-empty">{t("steps.edit.none")}</p>;
  const failures = failureLines(nodes[step.id]);
  return (
    <div>
      {step.type === "input" && <InputEditor step={step} draft={draft} setDraft={setDraft} datasets={datasets} />}
      {step.type === "join" && <JoinEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} />}
      {step.type === "transform" && <TransformEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} name={name} catalog={catalog} onPreviewTo={onPreviewTo} />}
      {step.type === "llm" && <LlmEditor key={step.id} step={step} draft={draft} setDraft={setDraft} nodes={nodes} name={name} options={options} dirty={dirty} />}
      {step.type === "union" && <UnionEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} />}
      {step.type === "split" && <SplitEditor key={step.id} step={step} draft={draft} setDraft={setDraft} nodes={nodes} name={name} />}
      {step.type === "output" && <OutputEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} />}
      {(step.type === "transform" || step.type === "llm") && failures.length > 0 && <p className="warn small">{t("steps.edit.failTotal", { lines: failures.join("; ") })}</p>}
    </div>
  );
}
