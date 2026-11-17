import React, { useEffect, useState } from "react";
import { getPermissions, setColumnAccess, setPermission, setRowRules } from "./api.js";
import { FormDialog } from "./FormDialog.jsx";
import { t, useT } from "./i18n/index.js";
import { attrNames, cutOff, loseAccess, prefilledRule, ruleText } from "./permissionModel.js";
import { Select } from "./Select.jsx";
import { toggled } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { useLoad } from "./useLoad.js";

const nameList = (people) => people.map((p) => p.name).join(t("data.listSep"));

/** The rows of one type that named people see: each rule is a property, a value and the people. Changes are collected here and saved together, so the person who sets them sees who is cut off before it happens. */
function RowRules({ type, people, onChanged, onError, onSaved }) {
  useT();
  const [column, setColumn] = useState("");
  const [value, setValue] = useState("");
  const [ids, setIds] = useState([]);
  const [attr, setAttr] = useState("");   // set: the rule is everyone's, against their own attribute of this name
  const [byAttr, setByAttr] = useState(false);
  const [draft, setDraft] = useState(null);   // null: nothing changed yet, what is saved is shown
  const [busy, setBusy] = useState(false);
  const rules = draft ?? type.row_rules;
  const names = (list) => list.map((i) => people.find((p) => p.id === i)?.name ?? `#${i}`).join(t("data.listSep"));
  const cut = cutOff(type, people, rules);
  const plain = (list) => JSON.stringify(list.map(({ column: c, value: v, user_ids, user_attr }) => [c, v, user_ids, user_attr || null]));
  const changed = draft !== null && plain(draft) !== plain(type.row_rules);
  const known = attrNames(people);
  const add = () => {
    const rule = byAttr ? { column, value: "", user_ids: [], user_attr: attr.trim() } : { column, value: value.trim(), user_ids: ids };
    const lead = draft === null ? prefilledRule(type, people, rule) : null;   // the first rule of a type brings an all-rows entry for the people it does not name
    setDraft([...rules, ...(lead ? [lead] : []), rule]);
    setColumn("");
    setValue("");
    setIds([]);
    setAttr("");
  };
  const save = async () => {
    setBusy(true);
    onError("");
    try {
      await setRowRules(type.id, rules.map(({ column: c, value: v, user_ids, user_attr }) => (user_attr ? { column: c, user_attr } : { column: c, value: v, user_ids })));
      setDraft(null);
      onSaved();
    } catch (e) {
      onError(e.message);
    }
    setBusy(false);
    onChanged();
  };
  return (
    <section className="card">
      <h3 className="item-title">{type.name}</h3>
      {!rules.length && <p className="muted">{t("users.perm.noRules")}</p>}
      <ul className="checks">
        {rules.map((r, i) => (
          <li key={r.id ?? `new${i}`}>{ruleText(r, type.columns.find((c) => c.column === r.column)?.name ?? r.column, names(r.user_ids))}
            {r.user_attr && <span className="faint small"> {t("users.perm.noAttr", { attr: r.user_attr })}</span>}
            {r.prefilled && <span className="faint small"> {t("users.perm.prefilled")}</span>}{" "}
            <button className="plain" disabled={busy} onClick={() => setDraft(rules.filter((_, j) => j !== i))}>{t("users.perm.remove")}</button></li>
        ))}
      </ul>
      {cut.length > 0 && <p className="warn">{t(changed ? "users.perm.cutAfter" : "users.perm.cutNow", { names: nameList(cut) })}</p>}
      <div className="inline wide" style={{ flexWrap: "wrap" }}>
        <Select label={t("users.perm.whoAria", { type: type.name })} value={byAttr ? "attr" : "named"} onChange={(v) => { setByAttr(v === "attr"); setColumn(""); }}>
          <option value="named">{t("users.perm.named")}</option>
          <option value="attr">{t("users.perm.byAttr")}</option>
        </Select>
        <Select label={t("users.perm.columnAria", { type: type.name })} value={column} onChange={setColumn}>
          {!byAttr && <option value="">{t("users.perm.allRows")}</option>}
          {byAttr && <option value="">{t("users.perm.pickAttr")}</option>}
          {type.columns.map((c) => <option key={c.column} value={c.column}>{c.name}</option>)}
        </Select>
        {column && <span>=</span>}
        {column && !byAttr && <input type="text" aria-label={t("users.perm.valueAria", { type: type.name })} value={value} maxLength={100} style={{ width: 200 }} onChange={(e) => setValue(e.target.value)} />}
        {byAttr && <span>{t("users.perm.theirOwn")}</span>}
        {byAttr && (
          <input type="text" list={`attrs-${type.id}`} aria-label={t("users.perm.attrAria", { type: type.name })} placeholder={t("users.perm.attrPlaceholder")} value={attr} maxLength={20} style={{ width: 140 }} onChange={(e) => setAttr(e.target.value)} />
        )}
        {byAttr && <datalist id={`attrs-${type.id}`}>{known.map((n) => <option key={n} value={n} />)}</datalist>}
        {!byAttr && people.map((p) => (
          <label key={p.id} className="check">
            <input type="checkbox" checked={ids.includes(p.id)} onChange={(e) => setIds(toggled(ids, p.id, e.target.checked))} aria-label={t("users.perm.seesAria", { type: type.name, name: p.name })} />
            {p.name}
          </label>
        ))}
        <button className="secondary" disabled={busy || (byAttr ? !column || !attr.trim() : (column && !value.trim()) || !ids.length)} onClick={add}>{t("users.perm.addRule")}</button>
      </div>
      {changed && (
        <div className="inline">
          <button className="primary" disabled={busy} onClick={save}>{t("users.perm.saveRules")}</button>
          <button className="plain" disabled={busy} onClick={() => setDraft(null)}>{t("users.perm.discard")}</button>
        </div>
      )}
    </section>
  );
}

/** Who sees each property of one type: everyone, or the people ticked (admins always). The key names the objects and is not offered. Saved at once, one column at a time. */
function ColumnAccess({ type, people, onChanged, onError, onSaved }) {
  useT();
  const [busy, setBusy] = useState(false);
  const columns = type.columns.filter((c) => !c.key);
  const save = async (column, visibleTo) => {
    setBusy(true);
    onError("");
    try {
      await setColumnAccess(type.id, column, visibleTo);
      onSaved();
    } catch (e) {
      onError(e.message);
    }
    setBusy(false);
    onChanged();
  };
  if (!columns.length) return null;
  return (
    <section className="card">
      <h3 className="item-title">{type.name}</h3>
      <div className="table-wrap">
        <table className="people">
          <thead><tr><th>{t("users.perm.property")}</th><th>{t("users.perm.everyone")}</th>{people.map((p) => <th key={p.id}>{p.name}</th>)}</tr></thead>
          <tbody>
            {columns.map((c) => {
              const ids = type.column_access?.[c.column];
              return (
                <tr key={c.column}>
                  <td>{c.name}</td>
                  <td><input type="checkbox" disabled={busy} checked={!ids} aria-label={t("users.perm.colEveryoneAria", { type: type.name, column: c.name })} onChange={(e) => save(c.column, e.target.checked ? "everyone" : [])} /></td>
                  {people.map((p) => (
                    <td key={p.id}>
                      <input type="checkbox" disabled={busy || !ids} checked={!ids || ids.includes(p.id)} aria-label={t("users.perm.colPersonAria", { type: type.name, column: c.name, name: p.name })}
                        onChange={(e) => save(c.column, toggled(ids ?? [], p.id, e.target.checked))} />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Who sees which object type: everyone, or the people ticked. A change that takes the type from someone asks first, and says who. */
export function PermissionsPage() {
  useT();
  const [state, reload] = useLoad(getPermissions, []);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [asking, setAsking] = useState(null);   // {type, visibleTo, losing}
  const [shown, setShown] = useState({});   // what a person just ticked, shown at once while the service saves it
  const people = state.data?.people ?? [];
  const save = async (type, visibleTo) => {
    setShown((s) => ({ ...s, [type]: visibleTo }));
    try {
      await setPermission(type, visibleTo);
      setSaved(t("users.saved"));
    } finally {
      reload();
    }
  };
  const change = (type, visibleTo) => {
    setError("");
    setSaved("");
    const losing = loseAccess(type, visibleTo, people);
    if (losing.length) {
      setAsking({ type, visibleTo, losing });
      return;
    }
    save(type.id, visibleTo).catch((e) => setError(e.message));
  };
  useEffect(() => setShown({}), [state.data]);   // the saved list has arrived: it is what is shown
  const now = (ty) => (ty.id in shown ? { ...ty, everyone: shown[ty.id] === "everyone", user_ids: shown[ty.id] === "everyone" ? [] : shown[ty.id] } : ty);
  const types = (state.data?.types ?? []).map(now);
  const later = people.filter((p) => p.role !== "admin");
  return (
    <main className="page">
      <div className="page-head"><h1 tabIndex={-1}>{t("users.perm.title")}</h1></div>
      <p className="muted lead">{t("users.perm.sub")}</p>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">{t("common.loading")}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {saved && !error && <p className="ok" role="status">{saved}</p>}
      {state.data && !state.data.types.length && <p className="muted">{t("users.perm.noTypes")}</p>}
      {types.length > 0 && (
        <div className="table-wrap">
          <table className="people">
            <thead>
              <tr>
                <th>{t("users.perm.objectType")}</th><th>{t("users.col.status")}</th><th>{t("users.perm.everyone")}</th>
                {people.map((p) => <th key={p.id}>{p.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {types.map((ty) => (
                <tr key={ty.id}>
                  <td><a href={hrefFor({ page: "type", id: ty.id, tab: "props" })}>{ty.name}</a></td>
                  <td><State item={ty} /></td>
                  <td><input type="checkbox" aria-label={t("users.perm.visibleAll", { type: ty.name })} checked={ty.everyone} onChange={(e) => change(ty, e.target.checked ? "everyone" : [])} /></td>
                  {people.map((p) => (
                    <td key={p.id}>
                      <input type="checkbox" aria-label={t("users.perm.visibleTo", { type: ty.name, name: p.name })} checked={ty.everyone || p.role === "admin" || ty.user_ids.includes(p.id)} disabled={ty.everyone || p.role === "admin"}
                        onChange={(e) => change(ty, toggled(ty.user_ids, p.id, e.target.checked))} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint">{t("users.perm.hint")}</p>
      {types.length > 0 && (
        <>
          <h2 className="section">{t("users.perm.rowRules")}</h2>
          <p className="muted lead">{t("users.perm.rowRulesText")}</p>
          <p className="muted lead">{t("users.perm.rowRulesNote")}</p>
          {types.map((t) => <RowRules key={t.id} type={t} people={later} onChanged={reload} onError={setError} onSaved={() => setSaved(t("users.saved"))} />)}
          <h2 className="section">{t("users.perm.colVisibility")}</h2>
          <p className="muted lead">{t("users.perm.colVisibilityText")}</p>
          {types.map((t) => <ColumnAccess key={t.id} type={t} people={later} onChanged={reload} onError={setError} onSaved={() => setSaved(t("users.saved"))} />)}
        </>
      )}
      {asking && (
        <FormDialog title={t("users.perm.askTitle", { name: asking.type.name })} submitLabel={t("users.roleChange.confirm")} valid onClose={() => setAsking(null)}
          onSubmit={() => save(asking.type.id, asking.visibleTo)}>
          <p>{t("users.perm.askText", { name: asking.type.name, names: nameList(asking.losing) })}</p>
        </FormDialog>
      )}
    </main>
  );
}
