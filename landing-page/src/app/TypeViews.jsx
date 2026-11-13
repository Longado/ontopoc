import React, { useState } from "react";
import { confirmView, createView, getTypeViews } from "./api.js";
import { Select } from "./Select.jsx";
import { State } from "./TypesPage.jsx";
import { confirmersText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { OP_LABEL, emptyViewForm, rowsText, viewPayload, viewProblem, viewWaitingText } from "./viewModel.js";

function ViewCard({ view, mayBuild, onChanged }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmView(view.id, view.version, view.seen);
      onChanged();
    } catch (e) {
      setError(e.message);
      if (e.code === 409) onChanged();   // what was read has moved: show what is there now
    }
    setBusy(false);
  };
  const line = stateLine(view, "这个视图");
  return (
    <section className="card">
      <div className="page-head">
        <h2 className="item-title">{view.name}</h2>
        <State item={view} />
      </div>
      <p>{view.says}</p>
      <p className="facts">
        <span>{view.problems.length ? "读不出来" : `现在留下 ${rowsText(view)}`}</span>
        {view.anchored && view.state === "needs_look" && <span className="muted">确认时 {view.anchored.rows} / {view.anchored.of} 行</span>}
        {view.description && <span>{view.description}</span>}
      </p>
      {view.problems.map((p) => <p key={p} className="warn">{p}</p>)}
      {line && <p className="muted small">{line}</p>}
      {viewWaitingText(view) && <p className="warn">{viewWaitingText(view)}</p>}
      {confirmersText(view) && <p className="muted small">{confirmersText(view)}</p>}
      {view.state === "needs_look" && view.reason && (
        <div className="reason">
          <strong>为什么需要再看</strong>
          <p>{view.reason}</p>
        </div>
      )}
      {mayBuild && view.can_confirm && <div className="inline"><button className="primary" onClick={confirm} disabled={busy}>确认这个视图</button></div>}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

/** One row of conditions: a code column, 是 / 不是, and one of the meanings written for it. */
function Condition({ row, codes, onChange, onRemove, only }) {
  const labels = codes.find((c) => c.column === row.column)?.labels ?? [];
  return (
    <div className="inline wide">
      <Select label="条件的列" value={row.column} onChange={(column) => onChange({ ...row, column, label: "" })}>
        <option value="">选一列</option>
        {codes.map((c) => <option key={c.column} value={c.column}>{c.name}</option>)}
      </Select>
      <Select label="是或不是" value={row.op} onChange={(op) => onChange({ ...row, op })}>
        {Object.entries(OP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </Select>
      <Select label="含义" value={row.label} disabled={!row.column} onChange={(label) => onChange({ ...row, label })}>
        <option value="">选含义</option>
        {labels.map((l) => <option key={l} value={l}>{l}</option>)}
      </Select>
      {!only && <button className="plain" onClick={onRemove}>去掉</button>}
    </div>
  );
}

function NewView({ type, form: options, onSaved }) {
  const [form, setForm] = useState(emptyViewForm());
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
      setForm(emptyViewForm());
      onSaved();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  return (
    <section>
      <h2 className="section">新建视图</h2>
      <label className="field">
        <span className="caption">名字</span>
        <input type="text" value={form.name} maxLength={40} placeholder="例如 有效订单" onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </label>
      <div className="field">
        <span className="caption">只留符合这些条件的行</span>
        {form.filters.map((row, i) => (
          <Condition key={i} row={row} codes={options.codes} only={form.filters.length === 1}
            onChange={(next) => setForm({ ...form, filters: form.filters.map((r, j) => (j === i ? next : r)) })}
            onRemove={() => setForm({ ...form, filters: form.filters.filter((_, j) => j !== i) })} />
        ))}
        {form.filters.length < 5 && <button className="plain" style={{ alignSelf: "flex-start" }} onClick={() => setForm({ ...form, filters: [...form.filters, { column: "", op: "is_not", label: "" }] })}>再加一个条件</button>}
        {options.codes.every((c) => !c.labels.length) && <p className="muted small">这个类型还没有写好含义的代码列，条件要用含义，先到属性页写。</p>}
      </div>
      <div className="field">
        <label className="check">
          <input type="checkbox" checked={form.latest.on} onChange={(e) => setForm({ ...form, latest: { ...form.latest, on: e.target.checked } })} />
          每个编号只留最新的一行
        </label>
        {form.latest.on && (
          <>
            <span className="caption">编号（先取最新，再用上面的条件筛）</span>
            <div className="inline wide" style={{ flexWrap: "wrap" }}>
              {options.columns.map((c) => (
                <label key={c.name} className="check">
                  <input type="checkbox" checked={form.latest.key.includes(c.name)} onChange={(e) => toggleKey(c.name, e.target.checked)} aria-label={`编号列 ${c.name}`} />
                  {c.name}
                </label>
              ))}
            </div>
            <span className="caption">比先后的列（数字、年月、日期）</span>
            <Select label="比先后的列" value={form.latest.order} onChange={(order) => setForm({ ...form, latest: { ...form.latest, order } })}>
              <option value="">选一列</option>
              {orderable.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </Select>
          </>
        )}
      </div>
      <div className="inline">
        <button className="primary" onClick={save} disabled={busy || !!problem}>保存并数一下行数</button>
        {problem && <span className="muted small">{problem}</span>}
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

export function TypeViews({ type, mayBuild }) {
  const [state, reload] = useLoad(() => getTypeViews(type.id), [type.id]);
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">加载中</p>;
  const { views, form } = state.data;
  return (
    <>
      {!views.length && <p className="muted">还没有视图。视图是这个类型的一部分行，例如“有效订单”，问答用它回答“不算已取消”这样的问题。</p>}
      <div className="cards">
        {views.map((v) => <ViewCard key={`${v.id}@${v.version}`} view={v} mayBuild={mayBuild} onChanged={reload} />)}
      </div>
      {mayBuild && form && <NewView type={type.id} form={form} onSaved={reload} />}
    </>
  );
}
