import React, { useEffect, useState } from "react";
import { getPermissions, setPermission, setRowRules } from "./api.js";
import { FormDialog } from "./FormDialog.jsx";
import { attrNames, cutOff, loseAccess, prefilledRule, ruleText } from "./permissionModel.js";
import { Select } from "./Select.jsx";
import { toggled } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { useLoad } from "./useLoad.js";

const nameList = (people) => people.map((p) => p.name).join("、");

/** The rows of one type that named people see: each rule is a property, a value and the people. Changes are collected here and saved together, so the person who sets them sees who is cut off before it happens. */
function RowRules({ type, people, onChanged, onError, onSaved }) {
  const [column, setColumn] = useState("");
  const [value, setValue] = useState("");
  const [ids, setIds] = useState([]);
  const [attr, setAttr] = useState("");   // set: the rule is everyone's, against their own attribute of this name
  const [byAttr, setByAttr] = useState(false);
  const [draft, setDraft] = useState(null);   // null: nothing changed yet, what is saved is shown
  const [busy, setBusy] = useState(false);
  const rules = draft ?? type.row_rules;
  const names = (list) => list.map((i) => people.find((p) => p.id === i)?.name ?? `#${i}`).join("、");
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
      {!rules.length && <p className="muted">没有行规则，所有看得到这个类型的人都看全部的行。</p>}
      <ul className="checks">
        {rules.map((r, i) => (
          <li key={r.id ?? `new${i}`}>{ruleText(r, type.columns.find((c) => c.column === r.column)?.name ?? r.column, names(r.user_ids))}
            {r.user_attr && <span className="faint small">（没填“{r.user_attr}”的人从这条规则看不到行）</span>}
            {r.prefilled && <span className="faint small">（自动加上：原来能看这个类型的人，照常看全部行）</span>}{" "}
            <button className="plain" disabled={busy} onClick={() => setDraft(rules.filter((_, j) => j !== i))}>去掉</button></li>
        ))}
      </ul>
      {cut.length > 0 && <p className="warn">{changed ? "保存后" : "现在"}这些人会一行也看不到：{nameList(cut)}。没被哪条规则点名的人，看不到这个类型的任何一行。</p>}
      <div className="inline wide" style={{ flexWrap: "wrap" }}>
        <Select label={`${type.name}：规则对谁`} value={byAttr ? "attr" : "named"} onChange={(v) => { setByAttr(v === "attr"); setColumn(""); }}>
          <option value="named">点名的人</option>
          <option value="attr">每个人，按自己的属性</option>
        </Select>
        <Select label={`${type.name}：规则的属性`} value={column} onChange={setColumn}>
          {!byAttr && <option value="">全部行（不设条件）</option>}
          {byAttr && <option value="">选属性</option>}
          {type.columns.map((c) => <option key={c.column} value={c.column}>{c.name}</option>)}
        </Select>
        {column && <span>=</span>}
        {column && !byAttr && <input type="text" aria-label={`${type.name}：规则的取值`} value={value} maxLength={100} style={{ width: 200 }} onChange={(e) => setValue(e.target.value)} />}
        {byAttr && <span>自己的</span>}
        {byAttr && (
          <input type="text" list={`attrs-${type.id}`} aria-label={`${type.name}：人的属性名`} placeholder="如 部门" value={attr} maxLength={20} style={{ width: 140 }} onChange={(e) => setAttr(e.target.value)} />
        )}
        {byAttr && <datalist id={`attrs-${type.id}`}>{known.map((n) => <option key={n} value={n} />)}</datalist>}
        {!byAttr && people.map((p) => (
          <label key={p.id} className="check">
            <input type="checkbox" checked={ids.includes(p.id)} onChange={(e) => setIds(toggled(ids, p.id, e.target.checked))} aria-label={`${type.name}：${p.name}按这条规则看`} />
            {p.name}
          </label>
        ))}
        <button className="secondary" disabled={busy || (byAttr ? !column || !attr.trim() : (column && !value.trim()) || !ids.length)} onClick={add}>加这条规则</button>
      </div>
      {changed && (
        <div className="inline">
          <button className="primary" disabled={busy} onClick={save}>保存行规则</button>
          <button className="plain" disabled={busy} onClick={() => setDraft(null)}>放弃修改</button>
        </div>
      )}
    </section>
  );
}

/** Who sees which object type: everyone, or the people ticked. A change that takes the type from someone asks first, and says who. */
export function PermissionsPage() {
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
      setSaved("已保存");
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
  const now = (t) => (t.id in shown ? { ...t, everyone: shown[t.id] === "everyone", user_ids: shown[t.id] === "everyone" ? [] : shown[t.id] } : t);
  const types = (state.data?.types ?? []).map(now);
  const later = people.filter((p) => p.role !== "admin");
  return (
    <main className="page">
      <div className="page-head"><h1 tabIndex={-1}>权限</h1></div>
      <p className="muted" style={{ marginBottom: 16 }}>每个对象类型可以让所有人看，或只让勾选的人看。管理员始终看得到全部；没确认的类型，查看者看不到，勾上也一样。</p>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {saved && !error && <p className="ok" role="status">{saved}</p>}
      {state.data && !state.data.types.length && <p className="muted">还没有对象类型。</p>}
      {types.length > 0 && (
        <div className="table-wrap">
          <table className="people">
            <thead>
              <tr>
                <th>对象类型</th><th>状态</th><th>所有人</th>
                {people.map((p) => <th key={p.id}>{p.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {types.map((t) => (
                <tr key={t.id}>
                  <td><a href={hrefFor({ page: "type", id: t.id, tab: "props" })}>{t.name}</a></td>
                  <td><State item={t} /></td>
                  <td><input type="checkbox" aria-label={`${t.name}：所有人可见`} checked={t.everyone} onChange={(e) => change(t, e.target.checked ? "everyone" : [])} /></td>
                  {people.map((p) => (
                    <td key={p.id}>
                      <input type="checkbox" aria-label={`${t.name}：${p.name}可见`} checked={t.everyone || p.role === "admin" || t.user_ids.includes(p.id)} disabled={t.everyone || p.role === "admin"}
                        onChange={(e) => change(t, toggled(t.user_ids, p.id, e.target.checked))} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint">不让所有人看之后，没勾的人（建设者也一样）在对象类型、对象、关系、待确认里都看不到这个类型。</p>
      {types.length > 0 && (
        <>
          <h2 className="section">行规则</h2>
          <p className="muted" style={{ marginBottom: 16 }}>类型一旦有行规则，每个人只看到点了他名字的规则放行的行；没被点名的人一行也看不到。“全部行”是不设条件的规则，点名的人看全部。管理员看全部。
            “每个人，按自己的属性”是一条管所有人的规则：比如 区域 = 自己的部门，每人看自己部门的行；人的属性在“用户”页填，新来的人填好属性就行，不用改规则。
            点名看“全部行”的人不受它限制：第一次加规则时自动给还没填属性的人加了“全部行”，之后给他们填了属性，要把这条“全部行”里的名字去掉才会按属性看。
            行为（类型页“行为”里定义的、会改某几个属性的值的操作）不能改写规则读的属性：改一次就能把一行移进或移出某个人看得到的范围。有行规则的类型，它的数据集只有管理员和被点名看全部行的人能看。</p>
          {types.map((t) => <RowRules key={t.id} type={t} people={later} onChanged={reload} onError={setError} onSaved={() => setSaved("已保存")} />)}
        </>
      )}
      {asking && (
        <FormDialog title={`改“${asking.type.name}”的可见范围`} submitLabel="确认改" valid onClose={() => setAsking(null)}
          onSubmit={() => save(asking.type.id, asking.visibleTo)}>
          <p>改了之后，这些人看不到“{asking.type.name}”了：{nameList(asking.losing)}。他们在对象类型、对象、关系、待确认里都不再出现它。</p>
        </FormDialog>
      )}
    </main>
  );
}
