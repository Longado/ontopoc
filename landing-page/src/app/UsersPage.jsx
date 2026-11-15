import React, { useState } from "react";
import { createUser, getTwoPerson, getUsers, resetUserPassword, setTwoPerson, setUserDisabled, updateUser } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { ROLES, roleLabel, statusText, twoPersonText } from "./authModel.js";
import { FormDialog } from "./FormDialog.jsx";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

function NewUser({ onClose, onDone }) {
  const [f, setF] = useState({ username: "", display_name: "", role: "builder", password: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <FormDialog title="新建用户" submitLabel="创建" onClose={onClose} valid={f.username.trim() && f.password} onSubmit={async () => { await createUser({ ...f, display_name: f.display_name.trim() || f.username.trim() }); onDone(); }}>
      <label className="field"><span className="caption">账号（登录用）</span><input type="text" value={f.username} autoComplete="off" onChange={set("username")} /></label>
      <label className="field"><span className="caption">显示名（记在每次操作上，可以是中文名）</span><input type="text" value={f.display_name} onChange={set("display_name")} /></label>
      <label className="field">
        <span className="caption">角色</span>
        <Select label="角色" value={f.role} onChange={(v) => setF({ ...f, role: v })}>{ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}</Select>
      </label>
      <label className="field"><span className="caption">第一个密码（至少 12 个字符，对方第一次登录时必须改掉）</span><input type="text" value={f.password} autoComplete="off" onChange={set("password")} /></label>
      <p className="hint">查看者：只能看和提问。建设者：还能上传数据、改定义。管理员：还能管人。</p>
    </FormDialog>
  );
}

function ResetPassword({ user, onClose, onDone }) {
  const [password, setPassword] = useState("");
  return (
    <FormDialog title={`重置“${user.display_name}”的密码`} submitLabel="重置" onClose={onClose} valid={!!password} onSubmit={async () => { await resetUserPassword(user.id, password); onDone(); }}>
      <p className="muted">这个账号现在所有的登录都会退出，对方用新密码登录后要先改掉它。</p>
      <label className="field"><span className="caption">新的临时密码（至少 12 个字符）</span><input type="text" value={password} autoComplete="off" onChange={(e) => setPassword(e.target.value)} /></label>
    </FormDialog>
  );
}

/** A person's attributes (部门、岗位…), which row rules may compare with: one name and value per line. */
function Attributes({ user, onClose, onDone }) {
  const [rows, setRows] = useState(() => [...Object.entries(user.attrs ?? {}), ["", ""]]);
  const put = (i, k, v) => setRows((list) => { const next = list.map((r, j) => (j === i ? (k === 0 ? [v, r[1]] : [r[0], v]) : r)); return next.at(-1)[0] || next.at(-1)[1] ? [...next, ["", ""]] : next; });
  const attrs = Object.fromEntries(rows.filter(([n]) => n.trim()).map(([n, v]) => [n.trim(), v.trim()]));
  const gone = Object.keys(user.attrs ?? {}).filter((n) => !attrs[n]);
  return (
    <FormDialog title={`“${user.display_name}”的属性`} submitLabel="保存" onClose={onClose} valid
      onSubmit={async () => { await updateUser(user.id, { attrs: { ...Object.fromEntries(gone.map((n) => [n, ""])), ...attrs } }); onDone(); }}>
      <p className="muted">行规则可以按“自己的属性”放行，比如 区域 = 自己的部门。改了属性，这个人看得到的行马上跟着变，改动记进日志。最多 5 个，值留空就去掉。</p>
      {rows.map(([n, v], i) => (
        <div className="inline" key={i}>
          <input type="text" aria-label={`属性名 ${i + 1}`} placeholder="属性名，如 部门" maxLength={20} value={n} onChange={(e) => put(i, 0, e.target.value)} />
          <input type="text" aria-label={`属性值 ${i + 1}`} placeholder="值" maxLength={100} value={v} onChange={(e) => put(i, 1, e.target.value)} />
        </div>
      ))}
    </FormDialog>
  );
}

/** Admin only: the people, their roles, and the two-person switch. The service refuses anything else, so a person who is not an admin never gets here. */
export function UsersPage() {
  const me = useAuth().user;
  const [users, reload] = useLoad(getUsers, []);
  const [two, reloadTwo] = useLoad(getTwoPerson, []);
  const [dialog, setDialog] = useState(null);   // "new" | {reset: user} | {role: user, to} | {disable: user} | {attrs: user}
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const act = async (call) => {
    setError("");
    setSaved(false);
    try {
      await call();
      setSaved(true);
      reload();
      reloadTwo();
    } catch (e) {
      setError(e.message);
      reload();   // what the person saw may be out of date
    }
  };
  const list = users.data ?? [];
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>用户</h1>
        <button className="primary" onClick={() => setDialog("new")}>新建用户</button>
      </div>
      {two.data && (
        <p className="facts">
          <span>{twoPersonText(two.data)}</span>
          <button className="plain" onClick={() => (two.data.enabled ? setDialog("two-off") : act(() => setTwoPerson(true)))}>{two.data.enabled ? "关闭" : "开启"}</button>
        </p>
      )}
      {(error || users.status === "error") && <p className="error" role="alert">{error || users.error}</p>}
      {saved && !error && <p className="ok" role="status">已保存</p>}
      {users.status === "loading" && !users.data && <p className="muted">加载中</p>}
      {list.length > 0 && (
        <div className="table-wrap">
          <table className="people">
            <thead><tr><th>账号</th><th>显示名</th><th>属性</th><th>角色</th><th>状态</th><th>上次登录</th><th></th></tr></thead>
            <tbody>
              {list.map((u) => (
                <tr key={u.id} className={u.disabled ? "note" : ""}>
                  <td>{u.username}</td>
                  <td>{u.display_name}</td>
                  <td>
                    {Object.entries(u.attrs ?? {}).map(([n, v]) => `${n}：${v}`).join("，") || <span className="faint">无</span>}{" "}
                    <button className="plain" onClick={() => setDialog({ attrs: u })}>改</button>
                  </td>
                  <td>
                    {u.id === me.id ? roleLabel(u.role) : (
                      <Select label={`${u.username} 的角色`} value={u.role} onChange={(role) => setDialog({ role: u, to: role })}>
                        {ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
                      </Select>
                    )}
                  </td>
                  <td>{statusText(u)}</td>
                  <td>{u.last_login_at ? timeText(u.last_login_at) : <span className="faint">还没登录过</span>}</td>
                  <td>
                    {u.id === me.id ? <span className="faint">自己</span> : (
                      <>
                        <button className="plain" onClick={() => (u.disabled ? act(() => setUserDisabled(u.id, false)) : setDialog({ disable: u }))}>{u.disabled ? "启用" : "停用"}</button>
                        <button className="plain" onClick={() => setDialog({ reset: u })}>重置密码</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {dialog === "new" && <NewUser onClose={() => setDialog(null)} onDone={() => { reload(); reloadTwo(); }} />}
      {dialog?.attrs && <Attributes user={dialog.attrs} onClose={() => setDialog(null)} onDone={() => { setSaved(true); reload(); }} />}
      {dialog?.reset && <ResetPassword user={dialog.reset} onClose={() => setDialog(null)} onDone={() => { setSaved(true); reload(); }} />}
      {dialog === "two-off" && (
        <FormDialog title="关闭两人确认" submitLabel="确认关闭" valid onClose={() => setDialog(null)}
          onSubmit={async () => { await setTwoPerson(false); setSaved(true); reload(); reloadTwo(); }}>
          <p>关闭后，一个人建的东西，自己确认就算数，不再需要另一个建设者看一遍。</p>
        </FormDialog>
      )}
      {dialog?.role && (
        <FormDialog title={`把“${dialog.role.display_name}”改成${roleLabel(dialog.to)}`} submitLabel="确认改" valid onClose={() => setDialog(null)}
          onSubmit={async () => { await updateUser(dialog.role.id, { role: dialog.to }); setSaved(true); reload(); }}>
          <p>对方会被登出，要重新登录；他名下的令牌也会作废，要重发。</p>
        </FormDialog>
      )}
      {dialog?.disable && (
        <FormDialog title={`停用“${dialog.disable.display_name}”`} submitLabel="确认停用" valid onClose={() => setDialog(null)}
          onSubmit={async () => { await setUserDisabled(dialog.disable.id, true); setSaved(true); reload(); reloadTwo(); }}>
          <p>对方会被登出，令牌永久作废，重新启用后要重发。对方登录时会看到“这个账号已停用”。</p>
        </FormDialog>
      )}
    </main>
  );
}
