import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getMe, signOut, whenSignedOut } from "./api.js";
import { AccountPage } from "./AccountPage.jsx";
import { useT } from "./i18n/index.js";
import { LoginPage } from "./LoginPage.jsx";
import { afterSignIn } from "./routeModel.js";

const AuthContext = createContext({ user: null, auth: false });
export const useAuth = () => useContext(AuthContext);

/**
 * Holds who is signed in. Signed out (or no account yet): the sign-in form, whatever address was asked for, which is still the address after
 * signing in. A person who must change the first password sees only that page. With the service run without sign-in, nobody is asked.
 */
export function AuthGate({ children }) {
  const t = useT();   // a language switch re-renders the gate; the signed-in app below is remounted with the new language
  const [me, setMe] = useState({ status: "loading" });
  const load = useCallback(
    () => getMe().then(
      (b) => setMe({ status: "in", user: b.user, auth: b.auth }),
      (e) => setMe(e.code === 401 || e.setup ? { status: "out", setup: e.setup ? e.message : "" } : { status: "failed", error: e.message }),
    ),
    [],
  );
  useEffect(() => {
    whenSignedOut(() => setMe((m) => (m.status === "in" ? { status: "out", setup: "", ended: true } : m)));
    load();
  }, [load]);

  if (me.status === "loading") return <p className="muted center">{t("auth.loading")}</p>;
  if (me.status === "failed") return <p className="error center">{me.error} <button className="plain" onClick={load}>{t("auth.retry")}</button></p>;
  // a fresh sign-in (and the forced first-password change after it) opens the home page; only an expired session returns to where the person was
  const home = (ended) => {
    const to = afterSignIn(window.location.hash, ended);
    if (window.location.hash !== to) window.location.hash = to;
    load();
  };
  if (me.status === "out") return <LoginPage setup={me.setup} ended={me.ended} onSignedIn={() => home(me.ended)} />;
  const exit = () => signOut().catch(() => {}).finally(() => setMe({ status: "out", setup: "" }));
  if (me.user.must_change) return <AccountPage forced user={me.user} onChanged={() => home(false)} />;
  return <AuthContext.Provider value={{ user: me.user, auth: me.auth, signOut: exit, refresh: load }}><React.Fragment key={t.locale}>{children}</React.Fragment></AuthContext.Provider>;
}
