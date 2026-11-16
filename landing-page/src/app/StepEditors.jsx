import React, { useEffect, useRef, useState } from "react";
import { operatorColumns } from "./api.js";
import { LlmEditor } from "./LlmEditor.jsx";
import { FilterForm, OperatorForm } from "./OperatorForms.jsx";
import {
  HOW_LABEL, KIND_LABEL, NULL_KEYS_LABEL, OPERATOR_PARAMS, addOperator, catalogView, copyOperator, doubledGroupLines, failureLines, friendlyError, joinVerdictLines, moveOperator, newOperator,
  branchReaders, newBranchId, operatorName, operatorTitle, readableSteps, removeOperator, removeStep, renameBranch, setOperator, splitLines, stepTitle, unionLines, updateStep,
} from "./pipelineModel.js";
import { Select } from "./Select.jsx";

const earlier = (draft, step) => draft.steps.slice(0, draft.steps.findIndex((s) => s.id === step.id));
/** The options of a "读哪一步" picker: the steps before this one, a split by its branches. */
const readOptions = (draft, step, skip = []) => readableSteps(earlier(draft, step)).filter((r) => !skip.includes(r.id)).map((r) => <option key={r.id} value={r.id}>{r.label}</option>);

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
        <Select label="左边" value={step.left ?? ""} onChange={(v) => set({ left: v, on: step.on.map(() => ({ left: "", right: "" })) })}>{readOptions(draft, step)}</Select>
        <Select label="关联方式" value={step.how} onChange={(how) => set({ how })}>
          {Object.entries(HOW_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select label="右边" value={step.right ?? ""} onChange={(v) => set({ right: v, on: step.on.map((p) => ({ ...p, right: "" })), right_columns: undefined })}>{readOptions(draft, step, [step.left])}</Select>
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
        <Select label="读哪一步" value={step.from ?? ""} onChange={(from) => { setEditing(null); setDraft(updateStep(draft, step.id, { from })); }}>{readOptions(draft, step)}</Select>
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

/** 合并: the steps whose rows are stacked, matched by column name; what to do with a column some of them lack; an optional column that says where each row came from. */
function UnionEditor({ step, draft, setDraft, nodes }) {
  const set = (patch) => setDraft(updateStep(draft, step.id, patch));
  const inputs = step.inputs ?? [];
  const readable = readableSteps(earlier(draft, step));
  const options = [...readable, ...inputs.filter((i) => !readable.some((r) => r.id === i)).map((i) => ({ id: i, label: `${i}（这里不能读，取消勾选它）` }))];
  const toggle = (id, on) => set({ inputs: on ? [...inputs, id] : inputs.filter((i) => i !== id) });
  const lines = unionLines(nodes[step.id]?.union);
  return (
    <div className="op-form">
      <fieldset className="keys">
        <legend>把哪几步的行接在一起（按列名对上）</legend>
        {options.map((r) => <label key={r.id}><input type="checkbox" checked={inputs.includes(r.id)} onChange={(e) => toggle(r.id, e.target.checked)} />{r.label}</label>)}
      </fieldset>
      <div className="ways">
        <label><input type="radio" name={`missing-${step.id}`} checked={(step.missing ?? "error") === "error"} onChange={() => set({ missing: "error" })} />有一步缺列就不合并</label>
        <label><input type="radio" name={`missing-${step.id}`} checked={step.missing === "empty"} onChange={() => set({ missing: "empty" })} />缺的列留空（会数出留空的行）</label>
      </div>
      <label className="field"><span className="caption">加一列标出每行来自哪一步（不填就不加）</span>
        <input type="text" value={step.source_column ?? ""} placeholder="例如 来源" onChange={(e) => set({ source_column: e.target.value || undefined })} />
      </label>
      <p className="hint">同一列在各步里类型要一样；代码列要各步确认过的含义一样，不一样先用“打标签”换成含义。</p>
      {lines.length > 0 && (
        <div className="verdict">
          <p className="caption">这一步做了什么</p>
          <ul className="plain-list">{lines.map((l) => <li key={l} className={/算两次/.test(l) ? "warn" : ""}>{l}</li>)}</ul>
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
      <div className="field"><span className="caption">拆哪一步的行</span>
        <Select label="读哪一步" value={step.from ?? ""} onChange={(from) => set({ from })}>{readOptions(draft, step)}</Select>
      </div>
      {source.error && <p className="error">读不出这一步的列：{friendlyError(source.error, draft.steps)}</p>}
      {ruled.map((b, i) => (
        <fieldset className="component" key={i}>
          <span className="caption">分支 {i + 1} 的名字（后面的步骤按它读）</span>
          <div className="inline wide">
            <BranchName label={`分支 ${i + 1} 的名字`} id={b.id} onRename={(to) => setDraft(renameBranch(draft, step.id, b.id, to))} />
            <button className="plain" disabled={ruled.length === 1 || readBy(b.id).length > 0} title={readBy(b.id).length ? `${readBy(b.id).join("、")} 在读这个分支，先改它们` : ""} onClick={() => set({ branches: branches.filter((x) => x !== b) })}>去掉这个分支</button>
          </div>
          {source.cols && <FilterForm op={{ where: b.where ?? { all: [] } }} cols={source.cols} onChange={(op) => setBranch(branches.indexOf(b), { where: op.where })} lead="满足" tail="条件的行进这个分支" />}
        </fieldset>
      ))}
      <div className="inline">
        <button className="plain" disabled={branches.length >= 10} onClick={() => set({ branches: withRest([...ruled, { id: newBranchId(step, draft.steps), where: { all: [{ column: "", cmp: "eq", value: "" }] } }]) })}>加一个分支</button>
        <label className="check" title={rest && readBy(rest.id).length ? `${readBy(rest.id).join("、")} 在读“其余”分支，先改它们` : ""}><input type="checkbox" checked={Boolean(rest)} disabled={Boolean(rest) && readBy(rest.id).length > 0} onChange={(e) => set({ branches: e.target.checked ? [...ruled, { id: `${step.id}_其余`, rest: true }] : ruled })} />其余的行进“其余”分支</label>
      </div>
      {rest && (
        <label className="field"><span className="caption">“其余”分支的名字</span>
          <BranchName label="“其余”分支的名字" id={rest.id} onRename={(to) => setDraft(renameBranch(draft, step.id, rest.id, to))} />
        </label>
      )}
      <p className="hint">一行只进第一个满足条件的分支。{rest ? "" : "没有“其余”分支时，哪个条件都不满足的行不会往下走。"}后面的步骤按分支的名字读。</p>
      {lines.length > 0 && (
        <div className="verdict">
          <p className="caption">这一步做了什么</p>
          <ul className="plain-list">{lines.map((l) => <li key={l} className={/没进任何分支|空的|前面的分支/.test(l) ? "warn" : ""}>{l}</li>)}</ul>
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
      <div className="field"><span className="caption">读哪一步</span>
        <Select label="读哪一步" value={step.from ?? ""} onChange={(from) => set({ from, columns: undefined, key: undefined })}>{readOptions(draft, step)}</Select>
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
export function StepEditor({ step, draft, setDraft, nodes, datasets, name, catalog, options, dirty, onPreviewTo, onRemoved }) {
  if (!step) return <p className="muted pl-empty">点左边的步骤或图里的卡片，在这里改它。</p>;
  const failures = failureLines(nodes[step.id]);
  return (
    <div>
      <StepHead step={step} draft={draft} setDraft={setDraft} onRemoved={onRemoved} />
      {step.type === "input" && <InputEditor step={step} draft={draft} setDraft={setDraft} datasets={datasets} />}
      {step.type === "join" && <JoinEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} />}
      {step.type === "transform" && <TransformEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} name={name} catalog={catalog} onPreviewTo={onPreviewTo} />}
      {step.type === "llm" && <LlmEditor key={step.id} step={step} draft={draft} setDraft={setDraft} nodes={nodes} name={name} options={options} dirty={dirty} />}
      {step.type === "union" && <UnionEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} />}
      {step.type === "split" && <SplitEditor key={step.id} step={step} draft={draft} setDraft={setDraft} nodes={nodes} name={name} />}
      {step.type === "output" && <OutputEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} />}
      {(step.type === "transform" || step.type === "llm") && failures.length > 0 && <p className="warn small">这一步共：{failures.join("；")}</p>}
    </div>
  );
}
