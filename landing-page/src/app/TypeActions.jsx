import React, { useState } from "react";
import { confirmAction, createAction, getAction, getActions, getRelations, getTypes, setActionNotify, submitAction, undoRecord, withdrawRecord } from "./api.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { State } from "./TypesPage.jsx";
import { confirmersText, logText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { actionProblem, emptyActionForm, actionPayload, notifyRecipient, recordStateText } from "./actionModel.js";

/** Who the action tells when a change is approved: named people (kept as they are: an admin names them), people by an attribute equal to a column of the row, or
 * people by an attribute equal to a column of the object the row points to through a relation. Saved at once; not part of what is confirmed. */
function Notify({ name, type, notify, mayBuild, onSaved }) {
  const [relations] = useLoad(getRelations, []);
  const [f, setF] = useState({ kind: "attr", column: "", relation: "", attr: "" });
  const [error, setError] = useState("");
  const mine = (relations.data ?? []).filter((r) => (r.from === type.id) !== (r.to === type.id));
  const save = async (recipients) => {
    setError("");
    try {
      await setActionNotify(name, recipients);
      setF({ kind: f.kind, column: "", relation: "", attr: "" });
      onSaved();
    } catch (e) {
      setError(e.message);
    }
  };
  const fresh = notifyRecipient(f);
  return (
    <div className="trace">
      <p className="small"><strong>批准后通知：</strong>{notify.lines.length ? notify.lines.join("；") : "不通知任何人"}</p>
      {mayBuild && notify.recipients.length > 0 && (
        <ul className="checks">
          {notify.recipients.map((r, i) => <li key={i} className="small">{notify.lines[i]} <button className="plain" onClick={() => save(notify.recipients.filter((_, j) => j !== i))}>去掉</button></li>)}
        </ul>
      )}
      {mayBuild && notify.recipients.length < 5 && (
        <div className="inline wide" style={{ flexWrap: "wrap" }}>
          <Select label={`${name}：通知谁`} value={f.kind} onChange={(kind) => setF({ ...f, kind })}>
            <option value="attr">这一行的某列 = 人的属性</option>
            <option value="via">经关系找到的对象的某列 = 人的属性</option>
          </Select>
          {f.kind === "via" && (
            <Select label={`${name}：经哪个关系`} value={f.relation} onChange={(relation) => setF({ ...f, relation })}>
              <option value="">选关系</option>
              {mine.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </Select>
          )}
          {f.kind === "attr" ? (
            <Select label={`${name}：哪一列`} value={f.column} onChange={(column) => setF({ ...f, column })}>
              <option value="">选列</option>
              {type.properties.map((p) => <option key={p.column} value={p.column}>{p.name}</option>)}
            </Select>
          ) : (
            <input type="text" aria-label={`${name}：另一端的列`} placeholder="另一端的列名" value={f.column} onChange={(e) => setF({ ...f, column: e.target.value })} />
          )}
          <span>= 人的</span>
          <input type="text" aria-label={`${name}：人的属性名`} placeholder="如 部门" maxLength={20} value={f.attr} onChange={(e) => setF({ ...f, attr: e.target.value })} />
          <button className="secondary" disabled={!fresh} onClick={() => save([...notify.recipients, fresh])}>加上</button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Records({ name, type, mayBuild }) {
  const [state, reload] = useLoad(() => getAction(name), [name]);
  const [error, setError] = useState("");
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">加载中</p>;
  const { records, log, notify } = state.data;
  const act = (call) => async (id) => {
    setError("");
    try {
      await call(id);
      reload();
    } catch (e) {
      setError(e.message);
    }
  };
  const withdraw = act(withdrawRecord);
  const undo = act(undoRecord);   // a new request that writes the before-values back; another builder approves it
  return (
    <>
      {notify && type && <Notify name={name} type={type} notify={notify} mayBuild={mayBuild} onSaved={reload} />}
      {records.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>提交</th><th>对象</th><th>改动</th><th>状态</th><th /></tr></thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td className="keep">{r.submitted_by}<span className="muted small block">{timeText(r.submitted_at)}</span></td>
                  <td>{r.object}</td>
                  <td>{r.before_text} → {r.after_text}{r.reason && <span className="muted small block">{r.reason}</span>}</td>
                  <td>{recordStateText(r)}{r.why && <span className="muted small block">{r.why}</span>}</td>
                  <td className="keep">
                    {r.can_withdraw && <button className="plain" onClick={() => withdraw(r.id)}>撤回</button>}
                    {r.can_undo && <button className="plain" title="提交一条把值改回去的请求，要另一位建设者批准" onClick={() => undo(r.id)}>撤销</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {log.length > 0 && (
        <details className="trace">
          <summary>这个行为的日志（{log.length} 条，包括被拒绝的）</summary>
          <div className="table-wrap">
            <table className="log">
              <tbody>
                {log.map((e, i) => {
                  const t = logText(e);
                  return <tr key={i}><td className="keep">{timeText(e.at)}</td><td className="keep">{t.who}</td><td>{t.text}</td></tr>;
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </>
  );
}

function ActionCard({ action, type, mayBuild, onChanged }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmAction(action.id, action.version);
      onChanged();
    } catch (e) {
      setError(e.message);
      if (e.code === 409) onChanged();
    }
    setBusy(false);
  };
  const line = stateLine(action, "这个行为");
  return (
    <section className="card">
      <div className="page-head">
        <h2 className="item-title">{action.name}</h2>
        <State item={action} />
      </div>
      <p>{action.says}</p>
      {action.description && <p className="muted">{action.description}</p>}
      {line && <p className="muted small">{line}</p>}
      {action.waiting_on?.length > 0 && <p className="warn">要先确认{action.waiting_on.map((w) => `“${w.name}”`).join("、")}，才能确认这个行为</p>}
      {confirmersText(action) && <p className="muted small">{confirmersText(action)}</p>}
      {action.state === "needs_look" && action.reason && <div className="reason"><strong>为什么需要再看</strong><p>{action.reason}</p></div>}
      {mayBuild && action.can_confirm && <div className="inline"><button className="primary" onClick={confirm} disabled={busy}>确认这个行为</button></div>}
      {error && <p className="error">{error}</p>}
      <Records name={action.id} type={type} mayBuild={mayBuild} />
    </section>
  );
}

function NewAction({ type, form: options, onSaved }) {
  const [form, setForm] = useState(emptyActionForm());
  const [types] = useLoad(getTypes, []);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const problem = actionProblem(form);
  const column = options.properties.find((p) => p.column === form.condition.column);
  const toggle = (name, on) => setForm({ ...form, properties: on ? [...form.properties, name] : form.properties.filter((p) => p !== name) });
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await createAction(actionPayload(type, form));
      setForm(emptyActionForm());
      onSaved();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  return (
    <section>
      <h2 className="section">新建行为</h2>
      <label className="field">
        <span className="caption">名字（动词加名词）</span>
        <input type="text" value={form.name} maxLength={40} placeholder="例如 改订单状态" onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </label>
      <div className="field">
        <span className="caption">要改的属性（主键不能改）</span>
        <div className="inline wide" style={{ flexWrap: "wrap" }}>
          {options.properties.map((p) => (
            <label key={p.column} className="check">
              <input type="checkbox" checked={form.properties.includes(p.column)} onChange={(e) => toggle(p.column, e.target.checked)} aria-label={`改 ${p.name}`} />
              {p.name}
            </label>
          ))}
        </div>
      </div>
      {options.properties.filter((p) => form.properties.includes(p.column) && !p.values).length > 0 && (
        <div className="field">
          <span className="caption">新值只能从某个对象类型的一列里选（可以不写）</span>
          {options.properties.filter((p) => form.properties.includes(p.column) && !p.values).map((p) => {
            const pick = form.choices?.[p.column] ?? { type: "", column: "" };
            const put = (next) => setForm({ ...form, choices: { ...form.choices, [p.column]: { ...pick, ...next } } });
            return (
              <div className="inline wide" key={p.column}>
                <span>{p.name} 从</span>
                <Select label={`${p.name}：可选值来自的类型`} value={pick.type} onChange={(t) => put({ type: t })}>
                  <option value="">不限</option>
                  {(types.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </Select>
                {pick.type && <input type="text" aria-label={`${p.name}：可选值来自的列`} placeholder="那个类型的列名" value={pick.column} onChange={(e) => put({ column: e.target.value })} />}
                {pick.type && <span>里选</span>}
              </div>
            );
          })}
        </div>
      )}
      <div className="field">
        <span className="caption">只在对象满足这个条件时可以提交（可以不写）</span>
        <div className="inline wide">
          <Select label="条件的属性" value={form.condition.column} onChange={(c) => setForm({ ...form, condition: { column: c, value: "" } })}>
            <option value="">不设条件</option>
            {options.properties.map((p) => <option key={p.column} value={p.column}>{p.name}</option>)}
          </Select>
          {column && <span>等于</span>}
          {column?.values && (
            <Select label="条件的取值" value={form.condition.value} onChange={(value) => setForm({ ...form, condition: { ...form.condition, value } })}>
              <option value="">选含义</option>
              {column.values.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
            </Select>
          )}
          {column && !column.values && <input type="text" aria-label="条件的取值" value={form.condition.value} maxLength={100} onChange={(e) => setForm({ ...form, condition: { ...form.condition, value: e.target.value } })} />}
        </div>
      </div>
      <div className="inline">
        <button className="primary" onClick={save} disabled={busy || !!problem}>保存</button>
        {problem && <span className="muted small">{problem}</span>}
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

export function TypeActions({ type, mayBuild }) {
  const [state, reload] = useLoad(() => getActions(type.id), [type.id]);
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">加载中</p>;
  const { actions, form } = state.data;
  return (
    <>
      {!actions.length && <p className="muted">还没有行为。行为是改数据的唯一办法：一个人提交，另一位建设者批准，才会写成数据集的新版本。</p>}
      <div className="cards">
        {actions.map((a) => <ActionCard key={`${a.id}@${a.version}`} action={a} type={type} mayBuild={mayBuild} onChanged={reload} />)}
      </div>
      {mayBuild && form && <NewAction type={type.id} form={form} onSaved={reload} />}
    </>
  );
}

/** The form for running one action on one object: a value for each property it writes, a reason. It makes a record that waits for another builder. */
export function RunAction({ action, objectKey, objectText, onDone, onCancel }) {
  const [values, setValues] = useState(() => Object.fromEntries(action.parameters.map((p) => [p.column, ""])));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const send = async () => {
    setBusy(true);
    setError("");
    try {
      await submitAction(action.id, objectKey, values, reason);
      setDone(true);
      onDone?.();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  if (done) return <p>已提交，等另一位建设者在 <a href="#/confirm">待确认</a> 里批准。 <button className="plain" onClick={onCancel}>关闭</button></p>;
  return (
    <section className="card">
      <h2 className="item-title">{action.name}：{objectText}</h2>
      {action.parameters.map((p) => (
        <div className="field" key={p.column}>
          <span className="caption">{p.name} 改成</span>
          {p.options ? (
            <Select label={`${p.name} 改成`} value={values[p.column]} onChange={(v) => setValues({ ...values, [p.column]: v })}>
              <option value="">选一个</option>
              {p.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          ) : (
            <input type="text" aria-label={`${p.name} 改成`} value={values[p.column]} onChange={(e) => setValues({ ...values, [p.column]: e.target.value })} />
          )}
          {p.options_cut && <span className="muted small">只列出前 500 个可选值</span>}
          {!p.options && <span className="muted small">{p.type_name}</span>}
        </div>
      ))}
      <label className="field">
        <span className="caption">理由</span>
        <input type="text" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="inline">
        <button className="primary" onClick={send} disabled={busy || action.parameters.some((p) => !values[p.column].trim())}>提交，等人批准</button>
        <button className="plain" onClick={onCancel}>取消</button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
