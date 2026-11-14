import React, { useEffect, useRef, useState } from "react";
import { createUser, getTwoPerson, getUsers, resetUserPassword, setTwoPerson, setUserDisabled, updateUser } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { ROLES, roleLabel, statusText, twoPersonText } from "./authModel.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

/** A small modal with a form, closed by 取消 or Escape. */
function FormDialog({ title, onClose, children, submitLabel, onSubmit, valid }) {
  const ref = useRef(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  useEffect(() => ref.current.showModal(), []);
  const close = () => {
    ref.current.close();
    onClose();
  };
  const submit = async () => {
    setSending(true);
    setError("");
    try {
      await onSubmit();
      close();
    } catch (e) {
      setError(e.message);
      setSending(false);
    }
  };
  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); close(); }}>
      <div className="dialog-body">
        <h2>{title}</h2>
        {children}
      </div>
      <div className="actions">
        {error ? <span className="error" role="alert">{error}</span> : <span></span>}
        <button className="plain" onClick={close}>取消</button>
        <button className="primary" onClick={submit} disabled={!valid || sending}>{sending ? "提交中" : submitLabel}</button>
      </div>
    </dialog>
  );
}

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
      <p className="hint">查看：只能看和提问。建设：还能上传数据、改定义。管理员：还能管人。</p>
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

/** Admin only: the people, their roles, and the two-person switch. The service refuses anything else, so a person who is not an admin never gets here. */
export function UsersPage() {
  const me = useAuth().user;
  const [users, reload] = useLoad(getUsers, []);
  const [two, reloadTwo] = useLoad(getTwoPerson, []);
  const [dialog, setDialog] = useState(null);   // "new" | {reset: user}
  const [error, setError] = useState("");
  const act = async (call) => {
    setError("");
    try {
      await call();
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
          <button className="plain" onClick={() => act(() => setTwoPerson(!two.data.enabled))}>{two.data.enabled ? "关闭" : "开启"}</button>
        </p>
      )}
      {(error || users.status === "error") && <p className="error" role="alert">{error || users.error}</p>}
      {users.status === "loading" && !users.data && <p className="muted">加载中</p>}
      {list.length > 0 && (
        <div className="table-wrap">
          <table className="people">
            <thead><tr><th>账号</th><th>显示名</th><th>角色</th><th>状态</th><th>上次登录</th><th></th></tr></thead>
            <tbody>
              {list.map((u) => (
                <tr key={u.id} className={u.disabled ? "note" : ""}>
                  <td>{u.username}</td>
                  <td>{u.display_name}</td>
                  <td>
                    {u.id === me.id ? roleLabel(u.role) : (
                      <Select label={`${u.username} 的角色`} value={u.role} onChange={(role) => act(() => updateUser(u.id, { role }))}>
                        {ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
                      </Select>
                    )}
                  </td>
                  <td>{statusText(u)}</td>
                  <td>{u.last_login_at ? timeText(u.last_login_at) : <span className="faint">还没登录过</span>}</td>
                  <td>
                    {u.id === me.id ? <span className="faint">自己</span> : (
                      <>
                        <button className="plain" onClick={() => act(() => setUserDisabled(u.id, !u.disabled))}>{u.disabled ? "启用" : "停用"}</button>
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
      {dialog?.reset && <ResetPassword user={dialog.reset} onClose={() => setDialog(null)} onDone={reload} />}
    </main>
  );
}
