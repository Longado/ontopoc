import React, { useEffect, useRef, useState } from "react";
import { operatorColumns } from "./api.js";
import { OperatorForm } from "./OperatorForms.jsx";
import {
  HOW_LABEL, KIND_LABEL, NULL_KEYS_LABEL, OPERATOR_PARAMS, addOperator, catalogView, copyOperator, doubledGroupLines, failureLines, friendlyError, joinVerdictLines, moveOperator, newOperator,
  operatorName, operatorTitle, removeOperator, removeStep, setOperator, stepTitle, updateStep,
} from "./pipelineModel.js";
import { Select } from "./Select.jsx";

const earlier = (draft, step) => draft.steps.slice(0, draft.steps.findIndex((s) => s.id === step.id));
const stepOption = (steps) => (s) => <option key={s.id} value={s.id}>{KIND_LABEL[s.type]}：{stepTitle(s, steps)}</option>;

/** The header every step editor has: what it is, and the way to remove it. */
function StepHead({ step, draft, setDraft, onRemoved }) {
  const readers = removeStep(draft, step.id).blocked;
  return (
    <div className="page-head step-head">
      <h2 className="section-title">{KIND_LABEL[step.type]}</h2>
      <button className="plain" disabled={readers.length > 0} title={readers.length ? `${readers.join("、")} 还在读它，先删它们` : ""} onClick={() => { setDraft(removeStep(draft, step.id).spec); onRemoved(); }}>删除这一步</button>
    </div>
  );
}

function InputEditor({ step, draft, setDraft, datasets }) {
  const known = datasets.find((d) => d.name === step.dataset);
  const set = (patch) => setDraft(updateStep(draft, step.id, patch));
  return (
    <div className="op-form">
      <div className="field">
        <span className="caption">读哪个数据集</span>
        <Select label="数据集" value={step.dataset ?? ""} onChange={(dataset) => set({ dataset, version: undefined })}>
          {!known && <option value={step.dataset ?? ""}>{step.dataset || "选一个数据集"}</option>}
          {datasets.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
        </Select>
      </div>
      <div className="field">
        <span className="caption">读哪一版</span>
        <Select label="版本" value={step.version ? String(step.version) : ""} onChange={(v) => set({ version: v ? Number(v) : undefined })}>
          <option value="">当前版本{known ? `（第 ${known.version} 版）` : ""}</option>
          {known && Array.from({ length: known.version }, (_, i) => known.version - i).map((v) => <option key={v} value={v}>第 {v} 版（固定）</option>)}
        </Select>
      </div>
      <p className="hint">选了固定的版本，数据集再有新版本，这一步也不动。</p>
    </div>
  );
}

function JoinEditor({ step, draft, setDraft, nodes }) {
  const before = earlier(draft, step);
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
  return (
    <div className="op-form">
      <div className="inline wide">
        <Select label="左边" value={step.left ?? ""} onChange={(v) => set({ left: v, on: step.on.map(() => ({ left: "", right: "" })) })}>{before.map(stepOption(draft.steps))}</Select>
        <Select label="关联方式" value={step.how} onChange={(how) => set({ how })}>
          {Object.entries(HOW_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select label="右边" value={step.right ?? ""} onChange={(v) => set({ right: v, on: step.on.map((p) => ({ ...p, right: "" })), right_columns: undefined })}>{before.filter((s) => s.id !== step.left).map(stepOption(draft.steps))}</Select>
      </div>
      {step.how === "semi" && <p className="hint">只留左边对得上的行，不带右边的列。</p>}
      {step.how === "anti" && <p className="hint">只留左边在右边找不到的行，不带右边的列。</p>}
      <fieldset className="keys">
        <legend>按哪几列对上</legend>
        {step.on.map((pair, i) => (
          <div className="inline wide op-row" key={i}>
            <Select label="左边的列" value={pair.left} onChange={(v) => setPair(i, { ...pair, left: v })}><option value="">左边的列</option>{left.map((n) => <option key={n} value={n}>{n}</option>)}</Select>
            <span>=</span>
            <Select label="右边的列" value={pair.right} onChange={(v) => setPair(i, { ...pair, right: v })}><option value="">右边的列</option>{right.map((n) => <option key={n} value={n}>{n}</option>)}</Select>
            <button className="plain" disabled={step.on.length === 1} onClick={() => set({ on: step.on.filter((_, k) => k !== i) })}>删除</button>
          </div>
        ))}
        <button className="plain" onClick={() => set({ on: [...step.on, { left: "", right: "" }] })}>加一对</button>
      </fieldset>
      <div className="ways">
        {Object.entries(NULL_KEYS_LABEL).map(([k, v]) => (
          <label key={k}><input type="radio" name={`null-${step.id}`} checked={(step.null_keys ?? "no_match") === k} onChange={() => set({ null_keys: k })} />{v}</label>
        ))}
      </div>
      {(step.how === "inner" || step.how === "left") && right.length > 0 && (
        <fieldset className="keys">
          <legend>带过来右边的哪些列</legend>
          {right.map((n) => <label key={n}><input type="checkbox" checked={chosen.includes(n)} onChange={(e) => toggleRight(n, e.target.checked)} />{n}</label>)}
        </fieldset>
      )}
      {verdict.length > 0 && (
        <div className="verdict">
          <p className="caption">这一步做了什么</p>
          <ul className="plain-list">{verdict.map((l, i) => <li key={i} className={i > 0 && /多出|合计|重复/.test(l) ? "warn" : ""}>{l}</li>)}</ul>
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
  if (state.error) return <p className="error">读不出这一步看到的列：{friendlyError(state.error, draft.steps)}</p>;
  if (!state.cols) return <p className="muted">加载中</p>;
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
        <h2>添加一个操作</h2>
        <input type="text" aria-label="搜索操作" placeholder="搜索，例如 求和、日期、空值" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="picker">
          <div className="picker-cats" role="tablist" aria-label="分类">
            <button role="tab" aria-selected={category === null} className={`plain${category === null ? " on" : ""}`} onClick={() => setCategory(null)}>全部</button>
            {categories.map((c) => <button key={c} role="tab" aria-selected={category === c} className={`plain${category === c ? " on" : ""}`} onClick={() => setCategory(c)}>{c}</button>)}
          </div>
          <ul className="picker-list">
            {items.map((c) => <li key={c.op}><button className={`plain${shown?.op === c.op ? " on" : ""}`} onClick={() => setPicked(c.op)}>{c.name}</button></li>)}
            {!items.length && <li className="muted">没有符合的操作</li>}
          </ul>
          <div className="picker-detail">
            {shown ? (
              <>
                <h3>{shown.name}</h3>
                <p>{shown.text}</p>
                <p className="caption">要填的</p>
                <ul className="plain-list">{(OPERATOR_PARAMS[shown.op] ?? []).map((p) => <li key={p}>{p}</li>)}</ul>
              </>
            ) : <p className="muted">从左边选一个操作</p>}
          </div>
        </div>
      </div>
      <div className="actions">
        <span></span>
        <button className="plain" onClick={onClose}>取消</button>
        <button className="primary" disabled={!shown} onClick={() => onPick(shown.op)}>添加{shown ? shown.name : ""}</button>
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
      {failed.length > 0 && <ul className="plain-list small warn">{failed.slice(0, 10).map((f) => <li key={f.row}>第 {f.row} 行：{f.value}</li>)}{failed.length > 10 && <li>还有 {failed.length - 10} 行</li>}</ul>}
      {report.error_rows?.length > 0 && <p className="warn small">算不出结果的行：{report.error_rows.slice(0, 10).join("、")}{report.error_rows.length > 10 ? " 等" : ""}</p>}
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
        <span className="caption">读哪一步</span>
        <Select label="读哪一步" value={step.from ?? ""} onChange={(from) => { setEditing(null); setDraft(updateStep(draft, step.id, { from })); }}>{earlier(draft, step).map(stepOption(draft.steps))}</Select>
      </div>
      <ol className="op-stack">
        {step.operators.map((op, i) => (
          <li key={i} className="op-card">
            <div className="op-head">
              <span className="op-no">{i + 1}</span>
              <strong>{operatorName(op)}</strong>
              {reports[i]?.affected != null && <span className="op-affect">影响 {reports[i].affected.toLocaleString("en-US")} 行</span>}
            </div>
            <p className="muted">{operatorTitle(op)}</p>
            <div className="op-buttons">
              <button className="plain" aria-expanded={editing === i} onClick={() => setEditing(editing === i ? null : i)}>{editing === i ? "收起" : "编辑"}</button>
              <button className="plain" onClick={() => onPreviewTo(i)}>预览</button>
              <button className="plain" onClick={() => apply(copyOperator(draft, step.id, i))}>复制</button>
              <button className="plain" onClick={() => { setEditing(null); apply(removeOperator(draft, step.id, i)); }}>删除</button>
              <button className="plain" disabled={i === 0} onClick={() => { setEditing(null); apply(moveOperator(draft, step.id, i, -1)); }}>上移</button>
              <button className="plain" disabled={i === step.operators.length - 1} onClick={() => { setEditing(null); apply(moveOperator(draft, step.id, i, 1)); }}>下移</button>
            </div>
            {editing === i && <OperatorEditor name={name} draft={draft} step={step} index={i} onChange={(next) => apply(setOperator(draft, step.id, i, next))} />}
            <OperatorReport report={reports[i]} />
          </li>
        ))}
      </ol>
      {!step.operators.length && <p className="muted">还没有操作。点“添加操作”，从清单里选。</p>}
      <button className="secondary" onClick={() => setAdding(true)}>添加操作</button>
      {adding && <OperatorPicker catalog={catalog} onClose={() => setAdding(false)} onPick={(kind) => { setAdding(false); apply(addOperator(draft, step.id, newOperator(kind))); setEditing(step.operators.length); }} />}
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
      <div className="field"><span className="caption">读哪一步</span>
        <Select label="读哪一步" value={step.from ?? ""} onChange={(from) => set({ from, columns: undefined, key: undefined })}>{earlier(draft, step).map(stepOption(draft.steps))}</Select>
      </div>
      <label className="field"><span className="caption">写成哪个数据集（没有就新建，有就加一个新版本）</span>
        <input type="text" value={step.name ?? ""} onChange={(e) => set({ name: e.target.value })} />
      </label>
      {status && <p className={`output-status status-${status.state}`}>{status.text}</p>}
      <fieldset className="keys">
        <legend>留下哪些列（取消勾选就丢掉）</legend>
        {names.map((n) => <label key={n}><input type="checkbox" checked={kept.includes(n)} onChange={(e) => toggle(n, e.target.checked)} />{n}</label>)}
      </fieldset>
      <fieldset className="keys">
        <legend>主键：用哪几列认出一行</legend>
        {names.map((n) => <label key={n}><input type="checkbox" checked={key.includes(n)} onChange={(e) => setKey(e.target.checked ? [...key, n] : key.filter((k) => k !== n))} />{n}</label>)}
      </fieldset>
      {key.length > 1 && (
        <div className="inline wide">
          <label className="field"><span className="caption">连起来的分隔符</span><input type="text" value={step.key.separator ?? "|"} maxLength={10} onChange={(e) => set({ key: { ...step.key, separator: e.target.value } })} /></label>
          <label className="field"><span className="caption">新主键列叫</span><input type="text" value={step.key.as ?? ""} placeholder="键" onChange={(e) => set({ key: { ...step.key, as: e.target.value || undefined } })} /></label>
        </div>
      )}
      {out?.duplicate_keys && (
        <div className="verdict">
          <p className="bad">主键有 {out.duplicate_keys.count} 个重复，多出 {out.duplicate_keys.extra_rows} 行，运行会被拦下</p>
          <ul className="plain-list small">{out.duplicate_keys.examples.map((e, i) => <li key={i}>{e.key.join(" + ")}：{e.rows} 行</li>)}</ul>
        </div>
      )}
      {out?.empty_keys > 0 && <p className="bad">{out.empty_keys} 行的主键是空的，运行会被拦下</p>}
      {out?.dropped.length > 0 && <p className="muted small">丢掉的列：{out.dropped.join("、")}</p>}
    </div>
  );
}

/** The editor on the right: by the kind of the selected step. `onPreviewTo(i)` shows the node's rows up to operator i in the bottom panel. */
export function StepEditor({ step, draft, setDraft, nodes, datasets, name, catalog, onPreviewTo, onRemoved }) {
  if (!step) return <p className="muted pl-empty">点左边的步骤或图里的卡片，在这里改它。</p>;
  const failures = failureLines(nodes[step.id]);
  return (
    <div>
      <StepHead step={step} draft={draft} setDraft={setDraft} onRemoved={onRemoved} />
      {step.type === "input" && <InputEditor step={step} draft={draft} setDraft={setDraft} datasets={datasets} />}
      {step.type === "join" && <JoinEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} />}
      {step.type === "transform" && <TransformEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} name={name} catalog={catalog} onPreviewTo={onPreviewTo} />}
      {step.type === "output" && <OutputEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} />}
      {step.type === "transform" && failures.length > 0 && <p className="warn small">这一步共：{failures.join("；")}</p>}
    </div>
  );
}
