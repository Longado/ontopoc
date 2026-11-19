import React, { useEffect, useState } from "react";
import { getHealth, signIn, startDemo } from "./api.js";
import { accessUrl } from "./authModel.js";
import { useT } from "./i18n/index.js";
import { LanguageSwitch } from "./ui/LanguageSwitch.jsx";

/** Account and password, one sentence when it fails. Before the first admin exists it says how to make one (on the machine, not here). */
export function LoginPage({ setup, ended, onSignedIn, feedbackUrl }) {
  const t = useT();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [demo, setDemo] = useState(false);
  const [demoError, setDemoError] = useState("");
  useEffect(() => {
    let live = true;
    getHealth().then((h) => live && setDemo(h?.demo === true), () => {});
    return () => {
      live = false;
    };
  }, []);
  const tryDemo = async () => {
    setSending(true);
    setDemoError("");
    try {
      await startDemo();
      onSignedIn();
    } catch (err) {
      setDemoError(err.message);
      setSending(false);
    }
  };
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
    <main className={`login login-page${demo ? " login-demo" : ""}`}>
      <div className="login-intro">
        <span className="brand brand-lg"><span className="brand-mark" aria-hidden="true" />OntoPoc</span>
        {demo ? (
          <>
            <p className="login-line">{t("auth.demo.pitch")}</p>
            <ul className="demo-points">
              <li>{t("auth.demo.point1")}</li>
              <li>{t("auth.demo.point2")}</li>
              <li>{t("auth.demo.point3")}</li>
            </ul>
            <div className="demo-actions">
              <button className="primary" type="button" onClick={tryDemo} disabled={sending}>{sending ? t("auth.demo.trying") : t("auth.demo.try")}</button>
              <a className="demo-request" href={accessUrl(feedbackUrl)} target="_blank" rel="noopener noreferrer">{t("auth.demo.request")}</a>
            </div>
            {demoError && <p className="error" role="alert">{demoError}</p>}
          </>
        ) : (
          <>
            <p className="login-line">{t("auth.login.tagline")}</p>
            <p className="muted">{t("auth.login.intro")}</p>
          </>
        )}
      </div>
      <div className="card login-card">
      <h1 tabIndex={-1}>{demo ? t("auth.demo.haveAccount") : t("auth.login.title")}</h1>
      {setup ? (
        <p className="error">{setup}</p>
      ) : (
        <form onSubmit={submit}>
          {ended && !error && <p className="muted">{t("auth.login.ended")}</p>}
          <label className="field">
            <span className="caption">{t("auth.login.username")}</span>
            <input type="text" value={username} autoComplete="username" autoFocus onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="field">
            <span className="caption">{t("auth.login.password")}</span>
            <input type="password" value={password} autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className={demo ? "secondary block" : "primary block"} type="submit" disabled={sending || !username || !password}>{sending ? t("auth.login.sending") : t("auth.login.submit")}</button>
        </form>
      )}
      <p className="muted small login-help">{t("auth.login.help")}</p>
      <LanguageSwitch variant="inline" />
      </div>
    </main>
  );
}
