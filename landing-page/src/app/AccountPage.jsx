import React, { useState } from "react";
import { changePassword, createToken, getTokens, revokeToken } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { roleLabel } from "./authModel.js";
import { timeText } from "./format.js";
import { useLoad } from "./useLoad.js";

function PasswordForm({ forced, onChanged }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [state, setState] = useState({ kind: "idle" });
  const mismatch = again && next !== again;
  const submit = async (e) => {
    e.preventDefault();
    setState({ kind: "sending" });
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
      setAgain("");
      setState({ kind: "done" });
      onChanged();
    } catch (err) {
      setState({ kind: "error", message: err.message });
    }
  };
  return (
    <form onSubmit={submit} className="stack">
      <label className="field">
        <span className="caption">现在的密码</span>
        <input type="password" value={current} autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label className="field">
        <span className="caption">新密码（至少 12 个字符）</span>
        <input type="password" value={next} autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
      </label>
      <label className="field">
        <span className="caption">再输一次新密码</span>
        <input type="password" value={again} autoComplete="new-password" aria-invalid={!!mismatch} onChange={(e) => setAgain(e.target.value)} />
      </label>
      {mismatch && <p className="error">两次输入不一样</p>}
      {state.kind === "error" && <p className="error" role="alert">{state.message}</p>}
      {state.kind === "done" && !forced && <p className="muted">密码已改，其他地方的登录已经退出。</p>}
      <div><button className="primary" type="submit" disabled={!current || !next || !again || !!mismatch || state.kind === "sending"}>改密码</button></div>
    </form>
  );
}

function Tokens() {
  const [state, reload] = useLoad(getTokens, []);
  const [label, setLabel] = useState("");
  const [made, setMade] = useState(null);
  const [error, setError] = useState("");
  const create = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setMade(await createToken(label));
      setLabel("");
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  const revoke = async (id) => {
    try {
      await revokeToken(id);
      setMade(null);
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  const tokens = state.data ?? [];
  return (
    <>
      <p className="muted">给脚本和 MCP 用：令牌的权限和你的角色一样，用它做的事记在你的名下。只在创建时显示一次。</p>
      <form onSubmit={create} className="inline">
        <input type="text" value={label} placeholder="用来做什么，例如 MCP" aria-label="令牌用途" onChange={(e) => setLabel(e.target.value)} />
        <button className="secondary" type="submit" disabled={!label.trim()}>创建令牌</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {made && (
        <p className="token">
          <span className="caption">现在复制，之后看不到了：</span>
          <input type="text" readOnly value={made.token} aria-label="新令牌" onFocus={(e) => e.target.select()} />
        </p>
      )}
      {state.status === "error" && <p className="error">{state.error}</p>}
      {tokens.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>用途</th><th>创建</th><th>最近用过</th><th></th></tr></thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id}>
                  <td>{t.label}</td>
                  <td>{timeText(t.created_at)}</td>
                  <td>{t.last_used_at ? timeText(t.last_used_at) : <span className="faint">没用过</span>}</td>
                  <td>{t.revoked ? <span className="muted">已撤销</span> : <button className="plain" onClick={() => revoke(t.id)}>撤销</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/** Change the password, and the person's own API tokens. When `forced`, the first password is being replaced and nothing else is shown. */
export function AccountPage({ forced = false, user: given, onChanged }) {
  const auth = useAuth();
  const user = given ?? auth.user;
  if (!forced && !auth.auth) {
    return (
      <main className="page">
        <h1 tabIndex={-1}>我的账号</h1>
        <p className="muted">这个服务没有开登录（用了 --no-auth），没有账号可管理。</p>
      </main>
    );
  }
  const body = (
    <>
      <h1 tabIndex={-1}>{forced ? "先改掉初始密码" : "我的账号"}</h1>
      {forced && <p className="muted">这是管理员给你的临时密码，改成只有你知道的，才能继续。</p>}
      {user && <p className="facts"><span>{user.display_name}</span><span>账号 {user.username}</span><span>角色 {roleLabel(user.role)}</span></p>}
      <section>
        <h2 className="section">{forced ? "新密码" : "改密码"}</h2>
        <PasswordForm forced={forced} onChanged={onChanged ?? (() => {})} />
      </section>
      {!forced && (
        <section>
          <h2 className="section">令牌</h2>
          <Tokens />
        </section>
      )}
    </>
  );
  return forced ? <main className="login wide">{body}</main> : <main className="page">{body}</main>;
}
