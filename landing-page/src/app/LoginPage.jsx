import React, { useEffect, useState } from "react";
import { getHealth, signIn, startDemo } from "./api.js";
import { accessUrl } from "./authModel.js";
import { useT } from "./i18n/index.js";
import { LanguageSwitch } from "./ui/LanguageSwitch.jsx";
import { Icon } from "./ui/Icon.jsx";
import "./landing.css";

/** Account and password, one sentence when it fails. Before the first admin exists it says how to make one (on the machine, not here). */
export function LoginPage({ setup, ended, onSignedIn, feedbackUrl }) {
  const t = useT();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [demo, setDemo] = useState(false);
  const [ready, setReady] = useState(false);   // the health check has answered (or failed): until then neither page is drawn, so the sign-in form does not flash before the landing page
  const [askIsOff, setAskIsOff] = useState(false);
  const [demoError, setDemoError] = useState("");
  useEffect(() => {
    let live = true;
    getHealth().then((h) => { if (live) { setDemo(h?.demo === true); setAskIsOff(h?.demo_ask === false); setReady(true); } }, () => live && setReady(true));
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
  const toSignIn = () => {
    const el = document.getElementById("sign-in");
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "center" });
    el?.querySelector("input")?.focus({ preventScroll: true });
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
  const form = setup ? (
    <p className="error">{setup}</p>
  ) : (
    <form onSubmit={submit}>
      {ended && !error && <p className="muted">{t("auth.login.ended")}</p>}
      <label className="field">
        <span className="caption">{t("auth.login.username")}</span>
        <input type="text" value={username} autoComplete="username" autoFocus={!demo} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label className="field">
        <span className="caption">{t("auth.login.password")}</span>
        <input type="password" value={password} autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button className={demo ? "secondary block" : "primary block"} type="submit" disabled={sending || !username || !password}>{sending ? t("auth.login.sending") : t("auth.login.submit")}</button>
    </form>
  );
  if (!ready) return <main className="login login-page" aria-busy="true" />;
  if (!demo) {
    return (
      <main className="login login-page">
        <div className="login-intro">
          <span className="brand brand-lg"><span className="brand-mark" aria-hidden="true" />OntoPoc</span>
          <p className="login-line">{t("auth.login.tagline")}</p>
          <p className="muted">{t("auth.login.intro")}</p>
        </div>
        <div className="card login-card">
          <h1 tabIndex={-1}>{t("auth.login.title")}</h1>
          {form}
          <p className="muted small login-help">{t("auth.login.help")}</p>
          <LanguageSwitch variant="inline" />
        </div>
      </main>
    );
  }
  const tryLabel = sending ? t("auth.demo.trying") : t("auth.landing.try");
  const bars = [["paid", 10770], ["shipped", 36800], ["delivered", 72240]];
  const steps = [["edit", 1], ["check", 2], ["search", 3]];
  return (
    <div className="landing">
      <header className="ld-bar">
        <div className="ld-wrap ld-bar-in">
          <span className="brand"><span className="brand-mark" aria-hidden="true" />OntoPoc</span>
          <div className="ld-bar-r">
            <LanguageSwitch variant="inline" />
            <button type="button" className="ld-link" onClick={toSignIn}>{t("auth.landing.signIn")}</button>
            <button type="button" className="primary ld-btn-sm" onClick={tryDemo} disabled={sending}>{sending ? t("auth.demo.trying") : t("auth.demo.try")}</button>
          </div>
        </div>
      </header>
      <main>
        <section className="ld-wrap ld-hero">
          <div className="ld-copy">
            <h1 className="ld-h1" tabIndex={-1}>{t("auth.landing.headline")}</h1>
            <p className="ld-sub">{t("auth.landing.sub")}</p>
            <div className="ld-cta">
              <button className="primary ld-btn" type="button" onClick={tryDemo} disabled={sending}>{tryLabel}</button>
              <a className="ld-btn ld-ghost" href={accessUrl(feedbackUrl)} target="_blank" rel="noopener noreferrer">{t("auth.landing.request")}</a>
            </div>
            {askIsOff && <p className="ld-note">{t("auth.demo.askOff")}</p>}
            {demoError && <p className="error" role="alert">{demoError}</p>}
          </div>
          <figure className="ld-window" role="img" aria-label={t("auth.landing.preview.label")}>
            <div className="ld-titlebar" aria-hidden="true"><i /><i /><i /><span>{t("auth.landing.preview.title")}</span></div>
            <div className="ld-win-body" aria-hidden="true">
              <div className="ld-main">
                <span className="ld-k">{t("auth.landing.preview.valid")}</span>
                <span className="ld-big">119,810 <em>{t("auth.landing.preview.confirmed")}</em></span>
              </div>
              <div className="ld-pair">
                <div><span className="ld-k">{t("auth.landing.preview.orders")}</span><span className="ld-num">107</span></div>
                <div><span className="ld-k">{t("auth.landing.preview.all")}</span><span className="ld-num">162,960</span><span className="ld-mute">{t("auth.landing.preview.allNote")}</span></div>
              </div>
              <div className="ld-bars">
                {bars.map(([k, v]) => (
                  <div className="ld-bar-row" key={k}>
                    <span>{t(`auth.landing.preview.${k}`)}</span>
                    <span className="ld-track"><span style={{ width: `${Math.round((v / 72240) * 100)}%` }} /></span>
                    <b>{v.toLocaleString("en-US")}</b>
                  </div>
                ))}
              </div>
            </div>
          </figure>
        </section>
        <section className="ld-wrap ld-steps" aria-label={t("auth.landing.steps.label")}>
          <ol>
            {steps.map(([icon, n]) => (
              <li key={n}>
                <span className="ld-ico" aria-hidden="true"><Icon name={icon} size={18} /></span>
                <h2>{n}. {t(`auth.landing.step${n}.title`)}</h2>
                <p>{t(`auth.landing.step${n}.text`)}</p>
              </li>
            ))}
          </ol>
        </section>
        <section className="ld-wrap ld-signin" id="sign-in">
          <div className="card login-card">
            <h2>{t("auth.demo.haveAccount")}</h2>
            {form}
            <p className="muted small login-help">{t("auth.login.help")}</p>
          </div>
        </section>
      </main>
      <footer className="ld-foot">
        <div className="ld-wrap ld-foot-in">
          <span>{t("auth.landing.footer")}</span>
          <a href="https://github.com/Longado/ontopoc" target="_blank" rel="noopener noreferrer">{t("auth.landing.github")}</a>
        </div>
      </footer>
    </div>
  );
}
