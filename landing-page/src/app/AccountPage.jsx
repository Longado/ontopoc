import React, { useState } from "react";
import { changePassword, createToken, getTokens, revokeToken } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { isGuest, roleLabel } from "./authModel.js";
import { formatDateTime, t } from "./i18n/index.js";
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
        <span className="caption">{t("account.password.current")}</span>
        <input type="password" value={current} autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label className="field">
        <span className="caption">{t("account.password.new")}</span>
        <input type="password" value={next} autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
      </label>
      <label className="field">
        <span className="caption">{t("account.password.again")}</span>
        <input type="password" value={again} autoComplete="new-password" aria-invalid={!!mismatch} onChange={(e) => setAgain(e.target.value)} />
      </label>
      {mismatch && <p className="error">{t("account.password.mismatch")}</p>}
      {state.kind === "error" && <p className="error" role="alert">{state.message}</p>}
      {state.kind === "done" && !forced && <p className="muted">{t("account.password.done")}</p>}
      <div><button className="primary" type="submit" disabled={!current || !next || !again || !!mismatch || state.kind === "sending"}>{t("account.password.submit")}</button></div>
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
      <p className="muted">{t("account.tokens.intro")}</p>
      <form onSubmit={create} className="inline">
        <input type="text" value={label} placeholder={t("account.tokens.label")} aria-label={t("account.tokens.labelAria")} onChange={(e) => setLabel(e.target.value)} />
        <button className="secondary" type="submit" disabled={!label.trim()}>{t("account.tokens.create")}</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {made && (
        <p className="token">
          <span className="caption">{t("account.tokens.copyNow")}</span>
          <input type="text" readOnly value={made.token} aria-label={t("account.tokens.newAria")} onFocus={(e) => e.target.select()} />
        </p>
      )}
      {state.status === "error" && <p className="error">{state.error}</p>}
      {tokens.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("account.tokens.purpose")}</th><th>{t("account.tokens.created")}</th><th>{t("account.tokens.lastUsed")}</th><th></th></tr></thead>
            <tbody>
              {tokens.map((tok) => (
                <tr key={tok.id}>
                  <td>{tok.label}</td>
                  <td>{formatDateTime(tok.created_at)}</td>
                  <td>{tok.last_used_at ? formatDateTime(tok.last_used_at) : <span className="faint">{t("account.tokens.never")}</span>}</td>
                  <td>{tok.revoked ? <span className="muted">{t("account.tokens.revoked")}</span> : <button className="plain" onClick={() => revoke(tok.id)}>{t("account.tokens.revoke")}</button>}</td>
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
        <h1 tabIndex={-1}>{t("account.title")}</h1>
        <p className="muted">{t("account.noAuth")}</p>
      </main>
    );
  }
  if (!forced && isGuest(user)) {
    return (
      <main className="page">
        <h1 tabIndex={-1}>{t("account.title")}</h1>
        <p className="muted">{t("account.guest.note")}</p>
      </main>
    );
  }
  const body = (
    <>
      <h1 tabIndex={-1}>{forced ? t("account.forced.title") : t("account.title")}</h1>
      {forced && <p className="muted">{t("account.forced.text")}</p>}
      {user && <p className="facts"><span>{user.display_name}</span><span>{t("account.facts.username", { username: user.username })}</span><span>{t("account.facts.role", { role: roleLabel(user.role) })}</span></p>}
      <section>
        <h2 className="section">{forced ? t("account.password.headingForced") : t("account.password.heading")}</h2>
        <PasswordForm forced={forced} onChanged={onChanged ?? (() => {})} />
      </section>
      {!forced && (
        <section>
          <h2 className="section">{t("account.tokens.heading")}</h2>
          <Tokens />
        </section>
      )}
    </>
  );
  return forced ? <main className="login wide">{body}</main> : <main className="page">{body}</main>;
}
