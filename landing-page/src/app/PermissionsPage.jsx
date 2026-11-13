import React, { useEffect, useState } from "react";
import { getPermissions, setPermission } from "./api.js";
import { toggled } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { useLoad } from "./useLoad.js";

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
    </main>
  );
}
