import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getMe, signOut, whenSignedOut } from "./api.js";
import { AccountPage } from "./AccountPage.jsx";
import { LoginPage } from "./LoginPage.jsx";

const AuthContext = createContext({ user: null, auth: false });
export const useAuth = () => useContext(AuthContext);

/**
 * Holds who is signed in. Signed out (or no account yet): the sign-in form, whatever address was asked for, which is still the address after
 * signing in. A person who must change the first password sees only that page. With the service run without sign-in, nobody is asked.
 */
export function AuthGate({ children }) {
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

  if (me.status === "loading") return <p className="muted center">加载中</p>;
  if (me.status === "failed") return <p className="error center">{me.error} <button className="plain" onClick={load}>重试</button></p>;
  if (me.status === "out") return <LoginPage setup={me.setup} ended={me.ended} onSignedIn={load} />;
  const exit = () => signOut().catch(() => {}).finally(() => setMe({ status: "out", setup: "" }));
  if (me.user.must_change) return <AccountPage forced user={me.user} onChanged={load} />;
  return <AuthContext.Provider value={{ user: me.user, auth: me.auth, signOut: exit, refresh: load }}>{children}</AuthContext.Provider>;
}
