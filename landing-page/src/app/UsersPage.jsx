import React, { useEffect, useRef, useState } from "react";
import { createUser, getTwoPerson, getUsers, resetUserPassword, setTwoPerson, setUserDisabled, updateUser } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { ROLES, roleLabel, statusText } from "./authModel.js";
import { CopyButton } from "./CopyButton.jsx";
import { FormDialog } from "./FormDialog.jsx";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { ROLE_CARDS, inviteText, newUserProblem, randomPassword, secureRandom, twoPersonBanner } from "./usersModel.js";
import { Icon } from "./ui/Icon.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

/** A password box that is masked until asked, with a button that fills it with a random one (and shows it, since it has to be sent to someone). */
function PasswordField({ value, onChange, caption }) {
  const [show, setShow] = useState(false);
  return (
    <div className="field">
      <span className="caption">{caption}</span>
      <span className="secret">
        <input type={show ? "text" : "password"} aria-label={caption} value={value} autoComplete="new-password" onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="plain" onClick={() => setShow(!show)} aria-pressed={show}>{show ? "隐藏" : "显示"}</button>
        <button type="button" className="secondary" onClick={() => { onChange(randomPassword(secureRandom)); setShow(true); }}>生成随机密码</button>
      </span>
    </div>
  );
}

/** Making a user, or (with `user`) setting a new temporary password. When it is saved the dialog turns into the invitation: the text to send, to copy. */
function UserDialog({ user, onClose, onDone }) {
  const ref = useRef(null);
  const [f, setF] = useState({ username: "", display_name: "", role: "builder", password: "" });
  const [made, setMade] = useState(null);   // the account and the password just set: what the invitation says
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  useEffect(() => ref.current.showModal(), []);
  const resetting = !!user;
  const problem = resetting ? (f.password.length < 12 ? "新密码至少 12 个字符" : "") : newUserProblem(f);
  const close = () => {
    ref.current.close();
    onClose();
  };
  const submit = async () => {
    setSending(true);
    setError("");
    try {
      if (resetting) {
        await resetUserPassword(user.id, f.password);
        setMade({ username: user.username, display_name: user.display_name, role: user.role, password: f.password });
      } else {
        const body = await createUser({ ...f, username: f.username.trim(), display_name: f.display_name.trim() || f.username.trim() });
        setMade({ username: body.user?.username ?? f.username.trim(), display_name: body.user?.display_name ?? f.display_name, role: f.role, password: f.password });
      }
      onDone();
    } catch (e) {
      setError(e.message);
    }
    setSending(false);
  };
  const text = made ? inviteText({ origin: window.location.origin, ...made }) : "";
  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); close(); }}>
      <div className="dialog-body">
        <h2>{made ? (resetting ? "密码已重置" : "账号已建好") : resetting ? `重置“${user.display_name}”的密码` : "新建用户"}</h2>
        {made ? (
          <>
            <p className="muted">把下面这段话发给 {made.display_name}。初始密码只在这里显示这一次，关掉后就看不到了。</p>
            <textarea className="invite-box" readOnly rows={6} value={text} aria-label="邀请文字" onFocus={(e) => e.target.select()} />
            <p className="hint">对方第一次登录时必须改掉这个初始密码。{resetting && "这个账号现在所有的登录都已退出。"}</p>
          </>
        ) : (
          <>
            {resetting && <p className="muted">这个账号现在所有的登录都会退出，对方用新密码登录后要先改掉它。</p>}
            {!resetting && (
              <>
                <label className="field"><span className="caption">账号（登录用）</span><input type="text" value={f.username} autoComplete="off" onChange={(e) => setF({ ...f, username: e.target.value })} /></label>
                <label className="field"><span className="caption">显示名（记在每次操作上，可以是中文名）</span><input type="text" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></label>
                <fieldset className="field role-field">
                  <legend className="caption">角色</legend>
                  <div className="radio-cards" role="radiogroup" aria-label="角色">
                    {ROLE_CARDS.map((r) => (
                      <label key={r.key} className={`radio-card${f.role === r.key ? " on" : ""}`}>
                        <input type="radio" name="role" checked={f.role === r.key} onChange={() => setF({ ...f, role: r.key })} />
                        <span className="radio-card-title">{r.label}</span>
                        <span className="radio-card-text">{r.rights}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              </>
            )}
            <PasswordField value={f.password} onChange={(password) => setF({ ...f, password })} caption={resetting ? "新的临时密码（至少 12 个字符）" : "初始密码（至少 12 个字符）"} />
            {problem && (f.username || resetting) && <p className="hint">{problem}</p>}
          </>
        )}
      </div>
      <div className="actions">
        {error ? <span className="error" role="alert">{error}</span> : <span></span>}
        {made ? (
          <>
            <CopyButton text={text} label="复制邀请文字" className="secondary" />
            <button className="primary" onClick={close}>完成</button>
          </>
        ) : (
          <>
            <button className="plain" onClick={close}>取消</button>
            <button className="primary" onClick={submit} disabled={!!problem || sending}>{sending ? "提交中" : resetting ? "重置" : "创建"}</button>
          </>
        )}
      </div>
    </dialog>
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

/** The two-person rule, in full, with what it means from now on. */
function TwoPersonBanner({ banner, enabled, onToggle }) {
  return (
    <section className={`banner banner-${banner.tone}`} aria-label="两人确认">
      <span className="banner-icon"><Icon name={banner.tone === "on" ? "shield" : "info"} size={18} /></span>
      <div className="banner-body">
        <p className="banner-text">{banner.text}</p>
        <p className="banner-from">{banner.from}</p>
      </div>
      <button className="secondary" onClick={onToggle}>{enabled ? "关闭两人确认" : "开启两人确认"}</button>
    </section>
  );
}

/** Admin only: the people, their roles, and the two-person switch. The service refuses anything else, so a person who is not an admin never gets here. */
export function UsersPage() {
  const me = useAuth().user;
  const [users, reload] = useLoad(getUsers, []);
  const [two, reloadTwo] = useLoad(getTwoPerson, []);
  const [dialog, setDialog] = useState(null);   // "new" | {reset: user} | {role: user, to} | {disable: user} | {attrs: user} | "two-off"
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
      <PageHeader crumbs={[{ label: "设置" }, { label: "用户" }]} title="用户" sub="谁能登录，能做什么。新同事的账号在这里开。"
        actions={<button className="primary" onClick={() => setDialog("new")}>新建用户</button>} />
      {two.data && <TwoPersonBanner banner={twoPersonBanner(two.data)} enabled={two.data.enabled} onToggle={() => (two.data.enabled ? setDialog("two-off") : act(() => setTwoPerson(true)))} />}
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
      {dialog === "new" && <UserDialog onClose={() => setDialog(null)} onDone={() => { reload(); reloadTwo(); }} />}
      {dialog?.attrs && <Attributes user={dialog.attrs} onClose={() => setDialog(null)} onDone={() => { setSaved(true); reload(); }} />}
      {dialog?.reset && <UserDialog user={dialog.reset} onClose={() => setDialog(null)} onDone={() => { setSaved(true); reload(); }} />}
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
