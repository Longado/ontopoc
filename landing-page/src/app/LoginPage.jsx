import React, { useState } from "react";
import { signIn } from "./api.js";

/** Account and password, one sentence when it fails. Before the first admin exists it says how to make one (on the machine, not here). */
export function LoginPage({ setup, ended, onSignedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSending(true);
    setError("");
    try {
      await signIn(username, password);
      onSignedIn();
    } catch (err) {
      setError(err.message);
      setPassword("");
      setSending(false);
    }
  };
  return (
    <main className="login login-page">
      <div className="login-intro">
        <span className="brand brand-lg"><span className="brand-mark" aria-hidden="true" />OntoPoc</span>
        <p className="login-line">把表格变成能问、能看的业务数据</p>
        <p className="muted">上传数据，定义“订单”“客户”这样的业务对象，同事就能直接用中文提问、看看板。</p>
      </div>
      <div className="card login-card">
      <h1 tabIndex={-1}>登录</h1>
      {setup ? (
        <p className="error">{setup}</p>
      ) : (
        <form onSubmit={submit}>
          {ended && !error && <p className="muted">登录已经过期，请再登录一次。</p>}
          <label className="field">
            <span className="caption">账号</span>
            <input type="text" value={username} autoComplete="username" autoFocus onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="field">
            <span className="caption">密码</span>
            <input type="password" value={password} autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="primary block" type="submit" disabled={sending || !username || !password}>{sending ? "登录中" : "登录"}</button>
        </form>
      )}
      <p className="muted small login-help">没有账号，或忘了密码？请联系你们的管理员。</p>
      </div>
    </main>
  );
}
