import React, { useEffect, useState } from "react";
import { confirmAction, createAction, getAction, getActions, getRelations, getTypes, setActionNotify, submitAction, undoRecord, withdrawRecord } from "./api.js";
import { timeText } from "./format.js";
import { t } from "./i18n/index.js";
import { Select } from "./Select.jsx";
import { State } from "./TypesPage.jsx";
import { confirmersText, joinList, logText, stateLine } from "./typeModel.js";
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
          {notify.recipients.map((r, i) => <li key={i} className="small">{notify.lines[i]} <button className="plain" onClick={() => save(notify.recipients.filter((_, j) => j !== i))}>{t("actions.notify.remove")}</button></li>)}
        </ul>
      )}
      {mayBuild && notify.recipients.length < 5 && (
        <div className="inline wide" style={{ flexWrap: "wrap" }}>
          <Select label={t("actions.notify.who", { name })} value={f.kind} onChange={(kind) => setF({ ...f, kind })}>
            <option value="attr">{t("actions.notify.attr")}</option>
            <option value="via">{t("actions.notify.via")}</option>
          </Select>
          {f.kind === "via" && (
            <Select label={t("actions.notify.relation", { name })} value={f.relation} onChange={(relation) => setF({ ...f, relation })}>
              <option value="">{t("actions.notify.pickRelation")}</option>
              {mine.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </Select>
          )}
          {f.kind === "attr" ? (
            <Select label={t("actions.notify.column", { name })} value={f.column} onChange={(column) => setF({ ...f, column })}>
              <option value="">{t("actions.notify.pickColumn")}</option>
              {type.properties.map((p) => <option key={p.column} value={p.column}>{p.name}</option>)}
            </Select>
          ) : (
            <input type="text" aria-label={t("actions.notify.otherColumn", { name })} placeholder={t("actions.notify.otherColumnPlaceholder")} value={f.column} onChange={(e) => setF({ ...f, column: e.target.value })} />
          )}
          <span>{t("actions.notify.equals")}</span>
          <input type="text" aria-label={t("actions.notify.attrName", { name })} placeholder={t("actions.notify.attrPlaceholder")} maxLength={20} value={f.attr} onChange={(e) => setF({ ...f, attr: e.target.value })} />
          <button className="secondary" disabled={!fresh} onClick={() => save([...notify.recipients, fresh])}>{t("actions.notify.add")}</button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** The records of one action, with Withdraw and Undo, the notification setting (folded: most never touch it) and the log (folded). */
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
      <h3 className="drawer-section">{t("actions.drawer.submissions")} {records.length}</h3>
      {!records.length && <p className="muted small">{t("actions.drawer.none")}</p>}
      {records.length > 0 && (
        <div className="table-wrap">
          <table className="wraps">
            <thead><tr><th>{t("actions.drawer.colSubmitted")}</th><th>{t("actions.drawer.colObject")}</th><th>{t("actions.drawer.colChange")}</th><th>{t("actions.drawer.colState")}</th><th /></tr></thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td className="keep">{r.submitted_by}<span className="muted small block">{timeText(r.submitted_at)}</span></td>
                  <td>{r.object}</td>
                  <td className="wrap-cell">{recordChangeText(r)}{r.reason && <span className="muted small block">{r.reason}</span>}</td>
                  <td className="keep">{recordStateText(r)}{r.why && <span className="muted small block">{r.why}</span>}</td>
                  <td className="keep">
                    {r.can_withdraw && <button className="plain" onClick={() => withdraw(r.id)}>{t("actions.drawer.withdraw")}</button>}
                    {r.can_undo && <button className="plain" title={t("actions.drawer.undoTitle")} onClick={() => undo(r.id)}>{t("actions.drawer.undo")}</button>}
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
          <summary>{t("actions.drawer.notify", { who: notify.lines.length ? notify.lines.join(t("types.semi")) : t("actions.drawer.notifyNobody") })}</summary>
          <Notify name={name} type={type} notify={notify} mayBuild={mayBuild} onSaved={onChanged} />
        </details>
      )}
      {log.length > 0 && (
        <details className="trace">
          <summary>{t("actions.drawer.log", { count: log.length })}</summary>
          <div className="table-wrap">
            <table className="log">
              <tbody>
                {log.map((e, i) => {
                  const entry = logText(e);
                  return <tr key={i}><td className="keep">{timeText(e.at)}</td><td className="keep">{entry.who}</td><td>{entry.text}</td></tr>;
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
  const line = stateLine(action, t("actions.drawer.noun"));
  const canRun = mayBuild && action.kind === "create" && action.state === "confirmed" && action.can_submit !== false;
  return (
    <Drawer open title={action.name} onClose={onClose} width={680}
      footer={(
        <>
          <button className="secondary" onClick={onClose}>{t("common.close")}</button>
          {canRun && <button className="secondary" onClick={() => onRun(action)}>{action.name}</button>}
          {mayBuild && action.can_confirm && <button className="primary" onClick={confirm} disabled={busy}>{t("actions.drawer.confirm")}</button>}
        </>
      )}>
      <div className="drawer-lead"><State item={action} /> <span className="muted small">{KIND_WORD[action.kind]}</span></div>
      <p>{action.says}</p>
      {action.description && <p className="muted">{action.description}</p>}
      {line && <p className="muted small">{line}</p>}
      {action.waiting_on?.length > 0 && <p className="warn">{t("actions.drawer.waiting", { names: joinList(action.waiting_on.map((w) => `“${w.name}”`)) })}</p>}
      {confirmersText(action) && <p className="muted small">{confirmersText(action)}</p>}
      {action.state === "rejected" && <div className="reason sent-back"><strong>{sentBackLine(action)}</strong></div>}
      {action.state === "needs_look" && action.reason && <div className="reason"><strong>{t("types.page.whyLook")}</strong><p>{action.reason}</p></div>}
      {action.submitters?.length > 0 && <p className="muted small">{t("actions.drawer.submitters", { names: joinList(action.submitters.map((p) => p.name)) })}</p>}
      {error && <p className="error">{error}</p>}
      {detail ? <Records name={action.id} type={type} mayBuild={mayBuild} detail={detail} onChanged={onChanged} /> : <p className="muted">{t("common.loading")}</p>}
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
    <Drawer open title={t("actions.new.title")} onClose={onClose} width={600}
      footer={(
        <>
          {block.reason && <span className="save-reason" role="status">{block.reason}</span>}
          <button className="secondary" onClick={onClose}>{t("common.cancel")}</button>
          <button className="primary" onClick={save} disabled={block.disabled}>{t("common.save")}</button>
        </>
      )}>
      <div className="field">
        <span className="caption">{t("actions.new.kind")}</span>
        <div className="inline wide">
          {Object.entries(KIND_WORD).map(([kind, word]) => (
            <label key={kind} className="check">
              <input type="radio" name="action-kind" checked={form.kind === kind} onChange={() => setForm({ ...form, kind, properties: kind === "delete" ? [] : form.properties, conditions: kind === "create" ? [] : form.conditions })} />
              {word}
            </label>
          ))}
        </div>
        {form.kind === "create" && <span className="muted small">{t("actions.new.createHint")}</span>}
        {form.kind === "delete" && <span className="muted small">{t("actions.new.deleteHint")}</span>}
      </div>
      <label className="field">
        <span className="caption">{t("actions.new.name")}</span>
        <input type="text" value={form.name} maxLength={40} placeholder={t("actions.new.namePlaceholder")} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </label>
      {form.kind !== "delete" && <div className="field">
        <span className="caption">{form.kind === "create" ? t("actions.new.propsCreate") : t("actions.new.propsEdit")}</span>
        <div className="inline wide" style={{ flexWrap: "wrap" }}>
          {options.properties.map((p) => (
            <label key={p.column} className="check">
              <input type="checkbox" checked={form.properties.includes(p.column)} onChange={(e) => toggle(p.column, e.target.checked)} aria-label={t("actions.new.propAria", { name: p.name })} />
              {p.name}
            </label>
          ))}
        </div>
      </div>}
      {form.kind !== "delete" && options.properties.filter((p) => form.properties.includes(p.column) && !p.values).length > 0 && (
        <div className="field">
          <span className="caption">{t("actions.new.choices")}</span>
          {options.properties.filter((p) => form.properties.includes(p.column) && !p.values).map((p) => {
            const pick = form.choices?.[p.column] ?? { type: "", column: "" };
            const put = (next) => setForm({ ...form, choices: { ...form.choices, [p.column]: { ...pick, ...next } } });
            return (
              <div className="inline wide" key={p.column}>
                <span>{t("actions.new.choiceFrom", { name: p.name })}</span>
                <Select label={t("actions.new.choiceType", { name: p.name })} value={pick.type} onChange={(v) => put({ type: v })}>
                  <option value="">{t("actions.new.anyType")}</option>
                  {(types.data ?? []).map((ty) => <option key={ty.id} value={ty.id}>{ty.name}</option>)}
                </Select>
                {pick.type && <input type="text" aria-label={t("actions.new.choiceColumn", { name: p.name })} placeholder={t("actions.new.choiceColumnPlaceholder")} value={pick.column} onChange={(e) => put({ column: e.target.value })} />}
                {pick.type && <span>{t("actions.new.choiceEnd")}</span>}
              </div>
            );
          })}
        </div>
      )}
      {form.kind !== "create" && (
        <div className="field">
          <span className="caption">{t("actions.new.conditions")}</span>
          {form.conditions.map((c, i) => {
            const prop = condProps.find((p) => p.column === c.column);
            const ops = opsFor(prop);
            return (
              <div className="inline wide" key={i}>
                <Select label={t("actions.new.condProp", { n: i + 1 })} value={c.column} onChange={(column) => setCondition(i, { column, op: "eq", value: "" })}>
                  <option value="">{t("actions.new.pickProp")}</option>
                  {condProps.map((p) => <option key={p.column} value={p.column}>{p.name}</option>)}
                </Select>
                <Select label={t("actions.new.condOp", { n: i + 1 })} value={c.op} onChange={(op) => setCondition(i, { op, value: "" })}>
                  {ops.map((op) => <option key={op} value={op}>{OP_WORD[op]}</option>)}
                </Select>
                {!["empty", "not_empty"].includes(c.op) && (prop?.values && ["eq", "ne"].includes(c.op) ? (
                  <Select label={t("actions.new.condValue", { n: i + 1 })} value={c.value} onChange={(value) => setCondition(i, { value })}>
                    <option value="">{t("actions.new.pickMeaning")}</option>
                    {prop.values.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
                  </Select>
                ) : (
                  <input type="text" aria-label={t("actions.new.condValue", { n: i + 1 })} value={c.value} maxLength={c.op === "in" ? 400 : 100}
                    placeholder={c.op === "in" ? (prop?.values ? t("actions.new.commasValues", { values: prop.values.map((v) => v.value).join(t("types.comma")) }) : t("actions.new.commas")) : ""}
                    onChange={(e) => setCondition(i, { value: e.target.value })} />
                ))}
                <button className="plain" onClick={() => setForm({ ...form, conditions: form.conditions.filter((_, j) => j !== i) })}>{t("actions.new.removeCondition")}</button>
              </div>
            );
          })}
          {form.conditions.length < 5 && <div><button className="plain" onClick={() => setForm({ ...form, conditions: [...form.conditions, emptyCondition()] })}>{t("actions.new.addCondition")}</button></div>}
        </div>
      )}
      {options.people?.length > 0 && (
        <div className="field">
          <span className="caption">{t("actions.new.submitters")}</span>
          <div className="inline wide" style={{ flexWrap: "wrap" }}>
            {options.people.map((p) => (
              <label key={p.id} className="check">
                <input type="checkbox" aria-label={t("actions.new.submitterAria", { name: p.name })} checked={form.submitters.includes(p.id)}
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

/** The Actions tab: one row for each action; a row opens its drawer; "New action" opens the form in a drawer. */
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
  if (!state.data) return <p className="muted">{t("common.loading")}</p>;
  const { actions, form, details } = state.data;
  const opened = actions.find((a) => a.id === open);
  return (
    <>
      <div className="tab-bar">
        <span className="muted">{actions.length ? t("actions.tab.count", { count: actions.length }) : ""}</span>
        {mayBuild && form && <button className="primary" onClick={() => setCreating(true)}><Icon name="plus" size={16} /> {t("actions.tab.new")}</button>}
      </div>
      {!actions.length && (
        <EmptyState icon="play" title={t("actions.tab.emptyTitle")} text={t("actions.tab.emptyText")}
          action={mayBuild && form ? { label: t("actions.tab.new"), onClick: () => setCreating(true) } : undefined} />
      )}
      {actions.length > 0 && (
        <div className="table-wrap">
          <table className="rows-table">
            <thead><tr><th>{t("actions.col.name")}</th><th>{t("actions.col.kind")}</th><th>{t("actions.col.content")}</th><th>{t("actions.col.state")}</th><th>{t("actions.col.last")}</th><th /></tr></thead>
            <tbody>
              {actions.map((a) => {
                const row = actionRow(a, details[a.id]?.records ?? null, mayBuild);
                return (
                  <tr key={`${a.id}@${a.version}`} className={`click${fresh === a.id ? " fresh" : ""}`} onClick={() => setOpen(a.id)}>
                    <td><button className="plain row-name" onClick={(e) => { e.stopPropagation(); setOpen(a.id); }}>{row.name}</button></td>
                    <td><span className="kind-word">{row.kind}</span></td>
                    <td className="wrap-cell says">{row.says}</td>
                    <td><State item={a} />{mayBuild && a.can_confirm && <span className="muted small block">{t("actions.tab.waitingYou")}</span>}{a.state === "rejected" && a.reason && <span className="muted small block sent-back-reason">{a.reason}</span>}</td>
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
        <Drawer open title={t("actions.tab.runTitle", { name: running.name, object: t("actions.tab.newObject", { type: running.type_name }) })} onClose={() => { setRunning(null); reload(); }} width={520}>
          <RunAction action={running} objectText={t("actions.tab.newObject", { type: running.type_name })} onDone={reload} onCancel={() => { setRunning(null); reload(); }} />
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
  if (done) return <p>{t("actions.run.doneBefore")}<a href="#/confirm">{t("actions.run.doneLink")}</a>{t("actions.run.doneAfter")} <button className="plain" onClick={onCancel}>{t("common.close")}</button></p>;
  const verb = (p) => (action.kind === "create" ? (p.key ? t("actions.run.paramKey", { name: p.name }) : p.name) : t("actions.run.paramChange", { name: p.name }));
  return (
    <section className="card">
      <h2 className="item-title">{t("actions.tab.runTitle", { name: action.name, object: objectText })}</h2>
      {action.kind === "delete" && <p className="warn">{t("actions.run.deleteWarn", { object: objectText })}</p>}
      {action.parameters.map((p) => (
        <div className="field" key={p.column}>
          <span className="caption">{verb(p)}</span>
          {p.options ? (
            <Select label={verb(p)} value={values[p.column]} onChange={(v) => setValues({ ...values, [p.column]: v })}>
              <option value="">{t("actions.run.pick")}</option>
              {p.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          ) : (
            <input type="text" aria-label={verb(p)} value={values[p.column]} onChange={(e) => setValues({ ...values, [p.column]: e.target.value })} />
          )}
          {p.options_cut && <span className="muted small">{t("actions.run.optionsCut")}</span>}
          {!p.options && <span className="muted small">{p.type_name}</span>}
        </div>
      ))}
      <label className="field">
        <span className="caption">{action.kind === "delete" ? t("actions.run.reasonRequired") : t("actions.run.reason")}</span>
        <input type="text" aria-label={t("actions.run.reason")} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="inline">
        <button className="primary" onClick={send} disabled={busy || !!problem}>{t("actions.run.send")}</button>
        <button className="plain" onClick={onCancel}>{t("common.cancel")}</button>
        {problem && <span className="muted small">{problem}</span>}
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
