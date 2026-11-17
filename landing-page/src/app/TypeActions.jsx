import React, { useEffect, useState } from "react";
import { confirmAction, createAction, getAction, getActions, getRelations, getTypes, setActionNotify, submitAction, undoRecord, withdrawRecord } from "./api.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { State } from "./TypesPage.jsx";
import { confirmersText, logText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { Drawer } from "./ui/Drawer.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { Icon } from "./ui/Icon.jsx";
import { sentBackLine } from "./relationModel.js";
import { KIND_WORD, OP_WORD, actionPayload, actionRow, emptyActionForm, emptyCondition, notifyRecipient, opsFor, recordChangeText, recordStateText, runPayload, runProblem, saveBlock } from "./actionModel.js";

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

/** The records of one action, with 撤回 and 撤销, the notification setting (folded: most never touch it) and the log (folded). */
function Records({ name, type, mayBuild, detail, onChanged }) {
  const [error, setError] = useState("");
  const { records, log, notify } = detail;
  const act = (call) => async (id) => {
    setError("");
    try {
      await call(id);
      onChanged();
    } catch (e) {
      setError(e.message);
    }
  };
  const withdraw = act(withdrawRecord);
  const undo = act(undoRecord);   // a new request that writes the before-values back; another builder approves it
  return (
    <>
      <h3 className="drawer-section">提交记录 {records.length}</h3>
      {!records.length && <p className="muted small">还没有人提交过。</p>}
      {records.length > 0 && (
        <div className="table-wrap">
          <table className="wraps">
            <thead><tr><th>提交</th><th>对象</th><th>改动</th><th>状态</th><th /></tr></thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td className="keep">{r.submitted_by}<span className="muted small block">{timeText(r.submitted_at)}</span></td>
                  <td>{r.object}</td>
                  <td className="wrap-cell">{recordChangeText(r)}{r.reason && <span className="muted small block">{r.reason}</span>}</td>
                  <td className="keep">{recordStateText(r)}{r.why && <span className="muted small block">{r.why}</span>}</td>
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
      {notify && type && (
        <details className="trace">
          <summary>批准后通知：{notify.lines.length ? notify.lines.join("；") : "不通知任何人"}</summary>
          <Notify name={name} type={type} notify={notify} mayBuild={mayBuild} onSaved={onChanged} />
        </details>
      )}
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

/** What one action is, who stands behind it and what has been done with it: the drawer a row opens. */
function ActionDrawer({ action, detail, type, mayBuild, onChanged, onRun, onClose }) {
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
  const canRun = mayBuild && action.kind === "create" && action.state === "confirmed" && action.can_submit !== false;
  return (
    <Drawer open title={action.name} onClose={onClose} width={680}
      footer={(
        <>
          <button className="secondary" onClick={onClose}>关闭</button>
          {canRun && <button className="secondary" onClick={() => onRun(action)}>{action.name}</button>}
          {mayBuild && action.can_confirm && <button className="primary" onClick={confirm} disabled={busy}>确认这个行为</button>}
        </>
      )}>
      <div className="drawer-lead"><State item={action} /> <span className="muted small">{KIND_WORD[action.kind]}</span></div>
      <p>{action.says}</p>
      {action.description && <p className="muted">{action.description}</p>}
      {line && <p className="muted small">{line}</p>}
      {action.waiting_on?.length > 0 && <p className="warn">要先确认{action.waiting_on.map((w) => `“${w.name}”`).join("、")}，才能确认这个行为</p>}
      {confirmersText(action) && <p className="muted small">{confirmersText(action)}</p>}
      {action.state === "rejected" && <div className="reason sent-back"><strong>{sentBackLine(action)}</strong></div>}
      {action.state === "needs_look" && action.reason && <div className="reason"><strong>为什么需要再看</strong><p>{action.reason}</p></div>}
      {action.submitters?.length > 0 && <p className="muted small">只有 {action.submitters.map((p) => p.name).join("、")} 可以提交</p>}
      {error && <p className="error">{error}</p>}
      {detail ? <Records name={action.id} type={type} mayBuild={mayBuild} detail={detail} onChanged={onChanged} /> : <p className="muted">加载中</p>}
    </Drawer>
  );
}

function NewAction({ type, form: options, onSaved, onClose }) {
  const [form, setForm] = useState(emptyActionForm());
  const [types] = useLoad(getTypes, []);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const block = saveBlock(form, busy);
  const condProps = options.condition_properties ?? options.properties;
  const setCondition = (i, next) => setForm({ ...form, conditions: form.conditions.map((c, j) => (j === i ? { ...c, ...next } : c)) });
  const toggle = (name, on) => setForm({ ...form, properties: on ? [...form.properties, name] : form.properties.filter((p) => p !== name) });
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await createAction(actionPayload(type, form));
      onSaved(form.name.trim());
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };
  return (
    <Drawer open title="新建行为" onClose={onClose} width={600}
      footer={(
        <>
          {block.reason && <span className="save-reason" role="status">{block.reason}</span>}
          <button className="secondary" onClick={onClose}>取消</button>
          <button className="primary" onClick={save} disabled={block.disabled}>保存</button>
        </>
      )}>
      <div className="field">
        <span className="caption">做什么</span>
        <div className="inline wide">
          {Object.entries(KIND_WORD).map(([kind, word]) => (
            <label key={kind} className="check">
              <input type="radio" name="action-kind" checked={form.kind === kind} onChange={() => setForm({ ...form, kind, properties: kind === "delete" ? [] : form.properties, conditions: kind === "create" ? [] : form.conditions })} />
              {word}
            </label>
          ))}
        </div>
        {form.kind === "create" && <span className="muted small">新建一个对象：主键总要填，再选要一起填的属性。主键已经有了就拒绝，不会改写已有的对象。</span>}
        {form.kind === "delete" && <span className="muted small">删除一个对象：提交要写理由，另一位建设者批准后才删；整行会留在记录里，可以撤销。</span>}
      </div>
      <label className="field">
        <span className="caption">名字（动词加名词）</span>
        <input type="text" value={form.name} maxLength={40} placeholder="例如 改订单状态" onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </label>
      {form.kind !== "delete" && <div className="field">
        <span className="caption">{form.kind === "create" ? "新建时要一起填的属性（主键总要填）" : "要改的属性（主键不能改）"}</span>
        <div className="inline wide" style={{ flexWrap: "wrap" }}>
          {options.properties.map((p) => (
            <label key={p.column} className="check">
              <input type="checkbox" checked={form.properties.includes(p.column)} onChange={(e) => toggle(p.column, e.target.checked)} aria-label={`改 ${p.name}`} />
              {p.name}
            </label>
          ))}
        </div>
      </div>}
      {form.kind !== "delete" && options.properties.filter((p) => form.properties.includes(p.column) && !p.values).length > 0 && (
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
      {form.kind !== "create" && (
        <div className="field">
          <span className="caption">只在对象满足这些条件时可以提交（都要满足，最多 5 条，可以不写）</span>
          {form.conditions.map((c, i) => {
            const prop = condProps.find((p) => p.column === c.column);
            const ops = opsFor(prop);
            return (
              <div className="inline wide" key={i}>
                <Select label={`条件 ${i + 1} 的属性`} value={c.column} onChange={(column) => setCondition(i, { column, op: "eq", value: "" })}>
                  <option value="">选属性</option>
                  {condProps.map((p) => <option key={p.column} value={p.column}>{p.name}</option>)}
                </Select>
                <Select label={`条件 ${i + 1} 的比较`} value={c.op} onChange={(op) => setCondition(i, { op, value: "" })}>
                  {ops.map((op) => <option key={op} value={op}>{OP_WORD[op]}</option>)}
                </Select>
                {!["empty", "not_empty"].includes(c.op) && (prop?.values && ["eq", "ne"].includes(c.op) ? (
                  <Select label={`条件 ${i + 1} 的取值`} value={c.value} onChange={(value) => setCondition(i, { value })}>
                    <option value="">选含义</option>
                    {prop.values.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
                  </Select>
                ) : (
                  <input type="text" aria-label={`条件 ${i + 1} 的取值`} value={c.value} maxLength={c.op === "in" ? 400 : 100}
                    placeholder={c.op === "in" ? (prop?.values ? `用逗号隔开：${prop.values.map((v) => v.value).join("，")}` : "用逗号隔开") : ""}
                    onChange={(e) => setCondition(i, { value: e.target.value })} />
                ))}
                <button className="plain" onClick={() => setForm({ ...form, conditions: form.conditions.filter((_, j) => j !== i) })}>去掉</button>
              </div>
            );
          })}
          {form.conditions.length < 5 && <div><button className="plain" onClick={() => setForm({ ...form, conditions: [...form.conditions, emptyCondition()] })}>加一个条件</button></div>}
        </div>
      )}
      {options.people?.length > 0 && (
        <div className="field">
          <span className="caption">谁能提交（不选就是能看到它的建设者都能提交）</span>
          <div className="inline wide" style={{ flexWrap: "wrap" }}>
            {options.people.map((p) => (
              <label key={p.id} className="check">
                <input type="checkbox" aria-label={`能提交：${p.name}`} checked={form.submitters.includes(p.id)}
                  onChange={(e) => setForm({ ...form, submitters: e.target.checked ? [...form.submitters, p.id] : form.submitters.filter((x) => x !== p.id) })} />
                {p.name}
              </label>
            ))}
          </div>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </Drawer>
  );
}

/** The 行为 tab: one row for each action; a row opens its drawer; 新建行为 opens the form in a drawer. */
export function TypeActions({ type, mayBuild, onCount }) {
  const [state, reload] = useLoad(async () => {
    const list = await getActions(type.id);
    const details = await Promise.all(list.actions.map((a) => getAction(a.id).catch(() => null)));
    return { ...list, details: Object.fromEntries(list.actions.map((a, i) => [a.id, details[i]])) };
  }, [type.id]);
  const [open, setOpen] = useState(null);       // the name of the action whose drawer is open
  const [creating, setCreating] = useState(false);
  const [running, setRunning] = useState(null);   // the create being run
  const [fresh, setFresh] = useState("");        // the action just saved, lit for a moment
  const count = state.data?.actions.length;
  useEffect(() => { if (count != null) onCount?.(count); }, [count]);   // the tab's number is this list's own
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">加载中</p>;
  const { actions, form, details } = state.data;
  const opened = actions.find((a) => a.id === open);
  return (
    <>
      <div className="tab-bar">
        <span className="muted">{actions.length ? `${actions.length} 个行为。点一行看详情和提交记录。` : ""}</span>
        {mayBuild && form && <button className="primary" onClick={() => setCreating(true)}><Icon name="plus" size={16} /> 新建行为</button>}
      </div>
      {!actions.length && (
        <EmptyState icon="play" title="还没有行为" text="行为是改数据的唯一办法：一个人提交，另一位建设者批准，才会写成数据集的新版本。"
          action={mayBuild && form ? { label: "新建行为", onClick: () => setCreating(true) } : undefined} />
      )}
      {actions.length > 0 && (
        <div className="table-wrap">
          <table className="rows-table">
            <thead><tr><th>名称</th><th>做什么</th><th>内容</th><th>状态</th><th>最近提交</th><th /></tr></thead>
            <tbody>
              {actions.map((a) => {
                const row = actionRow(a, details[a.id]?.records ?? null, mayBuild);
                return (
                  <tr key={`${a.id}@${a.version}`} className={`click${fresh === a.id ? " fresh" : ""}`} onClick={() => setOpen(a.id)}>
                    <td><button className="plain row-name" onClick={(e) => { e.stopPropagation(); setOpen(a.id); }}>{row.name}</button></td>
                    <td><span className="kind-word">{row.kind}</span></td>
                    <td className="wrap-cell says">{row.says}</td>
                    <td><State item={a} />{mayBuild && a.can_confirm && <span className="muted small block">等你确认</span>}{a.state === "rejected" && a.reason && <span className="muted small block sent-back-reason">{a.reason}</span>}</td>
                    <td className="muted small">{row.last}</td>
                    <td className="keep" onClick={(e) => e.stopPropagation()}>
                      {row.canRun && <button className="secondary" onClick={() => setRunning(a)}>{row.name}</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {opened && <ActionDrawer key={opened.id} action={opened} detail={details[opened.id]} type={type} mayBuild={mayBuild} onChanged={reload} onRun={(a) => { setOpen(null); setRunning(a); }} onClose={() => setOpen(null)} />}
      {running && (
        <Drawer open title={`${running.name}：新的${running.type_name}`} onClose={() => { setRunning(null); reload(); }} width={520}>
          <RunAction action={running} objectText={`新的${running.type_name}`} onDone={reload} onCancel={() => { setRunning(null); reload(); }} />
        </Drawer>
      )}
      {creating && mayBuild && form && (
        <NewAction type={type.id} form={form} onClose={() => setCreating(false)}
          onSaved={(name) => {
            setCreating(false);
            setFresh(name);
            setTimeout(() => setFresh(""), 4000);
            reload();
          }} />
      )}
    </>
  );
}

/** The form for running one action: a value for each property it writes (a create's key first), a reason (a delete must give one). It makes a record that waits
 * for another builder. A create has no object yet: `objectKey` is null and the key comes from the form. */
export function RunAction({ action, objectKey, objectText, onDone, onCancel }) {
  const [values, setValues] = useState(() => Object.fromEntries(action.parameters.map((p) => [p.column, ""])));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const problem = runProblem(action, values, reason);
  const send = async () => {
    setBusy(true);
    setError("");
    try {
      const run = runPayload(action, values);
      await submitAction(action.id, run.key ?? objectKey, run.params, reason);
      setDone(true);
      onDone?.();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  if (done) return <p>已提交，等另一位建设者在 <a href="#/confirm">待确认</a> 里批准。 <button className="plain" onClick={onCancel}>关闭</button></p>;
  const verb = (p) => (action.kind === "create" ? (p.key ? `${p.name}（主键）` : p.name) : `${p.name} 改成`);
  return (
    <section className="card">
      <h2 className="item-title">{action.name}：{objectText}</h2>
      {action.kind === "delete" && <p className="warn">批准后会删除 {objectText}。整行会留在记录里，可以撤销。</p>}
      {action.parameters.map((p) => (
        <div className="field" key={p.column}>
          <span className="caption">{verb(p)}</span>
          {p.options ? (
            <Select label={verb(p)} value={values[p.column]} onChange={(v) => setValues({ ...values, [p.column]: v })}>
              <option value="">选一个</option>
              {p.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          ) : (
            <input type="text" aria-label={verb(p)} value={values[p.column]} onChange={(e) => setValues({ ...values, [p.column]: e.target.value })} />
          )}
          {p.options_cut && <span className="muted small">只列出前 500 个可选值</span>}
          {!p.options && <span className="muted small">{p.type_name}</span>}
        </div>
      ))}
      <label className="field">
        <span className="caption">{action.kind === "delete" ? "理由（必填）" : "理由"}</span>
        <input type="text" aria-label="理由" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="inline">
        <button className="primary" onClick={send} disabled={busy || !!problem}>提交，等人批准</button>
        <button className="plain" onClick={onCancel}>取消</button>
        {problem && <span className="muted small">{problem}</span>}
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
