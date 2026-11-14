import React, { useEffect, useState } from "react";
import { getPermissions, setPermission, setRowRules } from "./api.js";
import { Select } from "./Select.jsx";
import { toggled } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { useLoad } from "./useLoad.js";

/** The rows of one type that named people see: each rule is a property, a value and the people. The whole list is saved when a rule is added or taken away. */
function RowRules({ type, people, onChanged, onError }) {
  const [column, setColumn] = useState("");
  const [value, setValue] = useState("");
  const [ids, setIds] = useState([]);
  const [busy, setBusy] = useState(false);
  const names = (list) => list.map((i) => people.find((p) => p.id === i)?.name ?? `#${i}`).join("、");
  const save = async (rules) => {
    setBusy(true);
    onError("");
    try {
      await setRowRules(type.id, rules.map(({ column: c, value: v, user_ids }) => ({ column: c, value: v, user_ids })));
      setColumn("");
      setValue("");
      setIds([]);
    } catch (e) {
      onError(e.message);
    }
    setBusy(false);
    onChanged();
  };
  return (
    <section className="card">
      <h3 className="item-title">{type.name}</h3>
      {!type.row_rules.length && <p className="muted">没有行规则，所有看得到这个类型的人都看全部的行。</p>}
      <ul className="checks">
        {type.row_rules.map((r) => (
          <li key={r.id}>{names(r.user_ids)} 看{r.column ? ` ${type.columns.find((c) => c.column === r.column)?.name ?? r.column} = ${r.value} 的行` : "全部行"}{" "}
            <button className="plain" disabled={busy} onClick={() => save(type.row_rules.filter((x) => x.id !== r.id))}>去掉</button></li>
        ))}
      </ul>
      <div className="inline wide" style={{ flexWrap: "wrap" }}>
        <Select label={`${type.name}：规则的属性`} value={column} onChange={setColumn}>
          <option value="">全部行（不设条件）</option>
          {type.columns.map((c) => <option key={c.column} value={c.column}>{c.name}</option>)}
        </Select>
        {column && <span>=</span>}
        {column && <input type="text" aria-label={`${type.name}：规则的取值`} value={value} maxLength={100} style={{ width: 200 }} onChange={(e) => setValue(e.target.value)} />}
        {people.map((p) => (
          <label key={p.id} className="check">
            <input type="checkbox" checked={ids.includes(p.id)} onChange={(e) => setIds(toggled(ids, p.id, e.target.checked))} aria-label={`${type.name}：${p.name}按这条规则看`} />
            {p.name}
          </label>
        ))}
        <button className="primary" disabled={busy || (column && !value.trim()) || !ids.length} onClick={() => save([...type.row_rules, { column, value: value.trim(), user_ids: ids }])}>加这条规则</button>
      </div>
    </section>
  );
}

/** Who sees which object type: everyone, or the people ticked. A change is saved when it is made. */
export function PermissionsPage() {
  const [state, reload] = useLoad(getPermissions, []);
  const [error, setError] = useState("");
  const [shown, setShown] = useState({});   // what a person just ticked, shown at once while the service saves it
  const change = async (type, visibleTo) => {
    setError("");
    setShown((s) => ({ ...s, [type]: visibleTo }));
    try {
      await setPermission(type, visibleTo);
    } catch (e) {
      setError(e.message);
    }
    reload();
  };
  useEffect(() => setShown({}), [state.data]);   // the saved list has arrived: it is what is shown
  const now = (t) => (t.id in shown ? { ...t, everyone: shown[t.id] === "everyone", user_ids: shown[t.id] === "everyone" ? [] : shown[t.id] } : t);
  const people = state.data?.people ?? [];
  return (
    <main className="page">
      <div className="page-head"><h1 tabIndex={-1}>权限</h1></div>
      <p className="muted" style={{ marginBottom: 16 }}>每个对象类型可以让所有人看，或只让勾选的人看。管理员始终看得到全部；没确认的类型，查看者看不到，勾上也一样。</p>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {error && <p className="error">{error}</p>}
      {state.data && !state.data.types.length && <p className="muted">还没有对象类型。</p>}
      {state.data?.types.length > 0 && (
        <div className="table-wrap">
          <table className="people">
            <thead>
              <tr>
                <th>对象类型</th><th>状态</th><th>所有人</th>
                {people.map((p) => <th key={p.id}>{p.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {state.data.types.map(now).map((t) => (
                <tr key={t.id}>
                  <td><a href={hrefFor({ page: "type", id: t.id, tab: "props" })}>{t.name}</a></td>
                  <td><State item={t} /></td>
                  <td><input type="checkbox" aria-label={`${t.name}：所有人可见`} checked={t.everyone} onChange={(e) => change(t.id, e.target.checked ? "everyone" : [])} /></td>
                  {people.map((p) => (
                    <td key={p.id}>
                      <input type="checkbox" aria-label={`${t.name}：${p.name}可见`} checked={t.everyone || p.role === "admin" || t.user_ids.includes(p.id)} disabled={t.everyone || p.role === "admin"}
                        onChange={(e) => change(t.id, toggled(t.user_ids, p.id, e.target.checked))} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint">不让所有人看之后，没勾的人（构建者也一样）在对象类型、对象、关系、待确认里都看不到这个类型。</p>
      {state.data?.types.length > 0 && (
        <>
          <h2 className="section">行规则</h2>
          <p className="muted" style={{ marginBottom: 16 }}>类型一旦有行规则（选“全部行”就是不设条件，点名的人看全部），每个人只看到点了名的规则放行的行，没有被点名的人一行也看不到；管理员看全部。规则读的属性不能被行为改写，有行规则的类型，它的数据集只有管理员能看。</p>
          {state.data.types.map((t) => <RowRules key={t.id} type={t} people={people.filter((p) => p.role !== "admin")} onChanged={reload} onError={setError} />)}
        </>
      )}
    </main>
  );
}
