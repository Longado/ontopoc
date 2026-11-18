import React, { useEffect, useRef, useState } from "react";
import { createUser, getTwoPerson, getUsers, resetUserPassword, setTwoPerson, setUserDisabled, updateUser } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { ROLES, roleLabel, statusText } from "./authModel.js";
import { CopyButton } from "./CopyButton.jsx";
import { FormDialog } from "./FormDialog.jsx";
import { t, useT } from "./i18n/index.js";
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
        <button type="button" className="plain" onClick={() => setShow(!show)} aria-pressed={show}>{show ? t("users.hide") : t("users.show")}</button>
        <button type="button" className="secondary" onClick={() => { onChange(randomPassword(secureRandom)); setShow(true); }}>{t("users.generate")}</button>
      </span>
    </div>
  );
}

/** Making a user, or (with `user`) setting a new temporary password. When it is saved the dialog turns into the invitation: the text to send, to copy. */
function UserDialog({ user, onClose, onDone }) {
  useT();
  const ref = useRef(null);
  const [f, setF] = useState({ username: "", display_name: "", role: "builder", password: "" });
  const [made, setMade] = useState(null);   // the account and the password just set: what the invitation says
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  useEffect(() => ref.current.showModal(), []);
  const resetting = !!user;
  const problem = resetting ? (f.password.length < 12 ? t("users.problem.newPassword") : "") : newUserProblem(f);
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
        <h2>{made ? (resetting ? t("users.dialog.resetDone") : t("users.dialog.madeDone")) : resetting ? t("users.dialog.resetTitle", { name: user.display_name }) : t("users.dialog.newTitle")}</h2>
        {made ? (
          <>
            <p className="muted">{t("users.dialog.sendTo", { name: made.display_name })}</p>
            <textarea className="invite-box" readOnly rows={6} value={text} aria-label={t("users.dialog.inviteAria")} onFocus={(e) => e.target.select()} />
            <p className="hint">{t("users.dialog.mustChange")}{resetting && ` ${t("users.dialog.signedOut")}`}</p>
          </>
        ) : (
          <>
            {resetting && <p className="muted">{t("users.dialog.resetNote")}</p>}
            {!resetting && (
              <>
                <label className="field"><span className="caption">{t("users.dialog.username")}</span><input type="text" value={f.username} autoComplete="off" onChange={(e) => setF({ ...f, username: e.target.value })} /></label>
                <label className="field"><span className="caption">{t("users.dialog.displayName")}</span><input type="text" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></label>
                <fieldset className="field role-field">
                  <legend className="caption">{t("users.col.role")}</legend>
                  <div className="radio-cards" role="radiogroup" aria-label={t("users.col.role")}>
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
            <PasswordField value={f.password} onChange={(password) => setF({ ...f, password })} caption={resetting ? t("users.dialog.newPassword") : t("users.dialog.initialPassword")} />
            {problem && (f.username || resetting) && <p className="hint">{problem}</p>}
          </>
        )}
      </div>
      <div className="actions">
        {error ? <span className="error" role="alert">{error}</span> : <span></span>}
        {made ? (
          <>
            <CopyButton text={text} label={t("users.dialog.copyInvite")} className="secondary" />
            <button className="primary" onClick={close}>{t("data.upl.done")}</button>
          </>
        ) : (
          <>
            <button className="plain" onClick={close}>{t("common.cancel")}</button>
            <button className="primary" onClick={submit} disabled={!!problem || sending}>{sending ? t("users.dialog.submitting") : resetting ? t("users.dialog.reset") : t("sources.form.create")}</button>
          </>
        )}
      </div>
    </dialog>
  );
}

/** A person's attributes (department, job…), which row rules may compare with: one name and value per line. */
function Attributes({ user, onClose, onDone }) {
  useT();
  const [rows, setRows] = useState(() => [...Object.entries(user.attrs ?? {}), ["", ""]]);
  const put = (i, k, v) => setRows((list) => { const next = list.map((r, j) => (j === i ? (k === 0 ? [v, r[1]] : [r[0], v]) : r)); return next.at(-1)[0] || next.at(-1)[1] ? [...next, ["", ""]] : next; });
  const attrs = Object.fromEntries(rows.filter(([n]) => n.trim()).map(([n, v]) => [n.trim(), v.trim()]));
  const gone = Object.keys(user.attrs ?? {}).filter((n) => !attrs[n]);
  return (
    <FormDialog title={t("users.attrs.title", { name: user.display_name })} submitLabel={t("common.save")} onClose={onClose} valid
      onSubmit={async () => { await updateUser(user.id, { attrs: { ...Object.fromEntries(gone.map((n) => [n, ""])), ...attrs } }); onDone(); }}>
      <p className="muted">{t("users.attrs.text")}</p>
      {rows.map(([n, v], i) => (
        <div className="inline" key={i}>
          <input type="text" aria-label={t("users.attrs.nameAria", { n: i + 1 })} placeholder={t("users.attrs.namePlaceholder")} maxLength={20} value={n} onChange={(e) => put(i, 0, e.target.value)} />
          <input type="text" aria-label={t("users.attrs.valueAria", { n: i + 1 })} placeholder={t("users.attrs.valuePlaceholder")} maxLength={100} value={v} onChange={(e) => put(i, 1, e.target.value)} />
        </div>
      ))}
    </FormDialog>
  );
}

/** The two-person rule, in full, with what it means from now on. */
function TwoPersonBanner({ banner, enabled, onToggle }) {
  return (
    <section className={`banner banner-${banner.tone}`} aria-label={t("users.two.aria")}>
      <span className="banner-icon"><Icon name={banner.tone === "on" ? "shield" : "info"} size={18} /></span>
      <div className="banner-body">
        <p className="banner-text">{banner.text}</p>
        <p className="banner-from">{banner.from}</p>
      </div>
      <button className="secondary" onClick={onToggle}>{enabled ? t("users.two.turnOff") : t("users.two.turnOn")}</button>
    </section>
  );
}

/** Admin only: the people, their roles, and the two-person switch. The service refuses anything else, so a person who is not an admin never gets here. */
export function UsersPage() {
  useT();
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
      <PageHeader crumbs={[{ label: t("users.crumb.settings") }, { label: t("users.title") }]} title={t("users.title")} sub={t("users.sub")}
        actions={<button className="primary" onClick={() => setDialog("new")}>{t("users.dialog.newTitle")}</button>} />
      {two.data && <TwoPersonBanner banner={twoPersonBanner(two.data)} enabled={two.data.enabled} onToggle={() => (two.data.enabled ? setDialog("two-off") : act(() => setTwoPerson(true)))} />}
      {(error || users.status === "error") && <p className="error" role="alert">{error || users.error}</p>}
      {saved && !error && <p className="ok" role="status">{t("users.saved")}</p>}
      {users.status === "loading" && !users.data && <p className="muted">{t("common.loading")}</p>}
      {list.length > 0 && (
        <div className="table-wrap">
          <table className="people">
            <thead><tr><th>{t("users.col.username")}</th><th>{t("users.col.displayName")}</th><th>{t("users.col.attrs")}</th><th>{t("users.col.role")}</th><th>{t("users.col.status")}</th><th>{t("users.col.lastLogin")}</th><th></th></tr></thead>
            <tbody>
              {list.map((u) => (
                <tr key={u.id} className={u.disabled ? "note" : ""}>
                  <td>{u.username}</td>
                  <td>{u.display_name}</td>
                  <td>
                    {Object.entries(u.attrs ?? {}).map(([n, v]) => t("users.attrs.pair", { name: n, value: v })).join(t("data.sep")) || <span className="faint">{t("users.attrs.none")}</span>}{" "}
                    <button className="plain" onClick={() => setDialog({ attrs: u })}>{t("users.attrs.edit")}</button>
                  </td>
                  <td>
                    {u.id === me.id ? roleLabel(u.role) : (
                      <Select label={t("users.roleAria", { name: u.username })} value={u.role} onChange={(role) => setDialog({ role: u, to: role })}>
                        {ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
                      </Select>
                    )}
                  </td>
                  <td>{statusText(u)}</td>
                  <td>{u.last_login_at ? timeText(u.last_login_at) : <span className="faint">{t("users.never")}</span>}</td>
                  <td>
                    {u.id === me.id ? <span className="faint">{t("users.you")}</span> : (
                      <>
                        <button className="plain" onClick={() => (u.disabled ? act(() => setUserDisabled(u.id, false)) : setDialog({ disable: u }))}>{u.disabled ? t("users.enable") : t("users.disable")}</button>
                        <button className="plain" onClick={() => setDialog({ reset: u })}>{t("users.resetPassword")}</button>
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
        <FormDialog title={t("users.two.turnOff")} submitLabel={t("users.two.confirmOff")} valid onClose={() => setDialog(null)}
          onSubmit={async () => { await setTwoPerson(false); setSaved(true); reload(); reloadTwo(); }}>
          <p>{t("users.two.offText")}</p>
        </FormDialog>
      )}
      {dialog?.role && (
        <FormDialog title={t("users.roleChange.title", { name: dialog.role.display_name, role: roleLabel(dialog.to) })} submitLabel={t("users.roleChange.confirm")} valid onClose={() => setDialog(null)}
          onSubmit={async () => { await updateUser(dialog.role.id, { role: dialog.to }); setSaved(true); reload(); }}>
          <p>{t("users.roleChange.text")}</p>
        </FormDialog>
      )}
      {dialog?.disable && (
        <FormDialog title={t("users.disableDialog.title", { name: dialog.disable.display_name })} submitLabel={t("users.disableDialog.confirm")} valid onClose={() => setDialog(null)}
          onSubmit={async () => { await setUserDisabled(dialog.disable.id, true); setSaved(true); reload(); reloadTwo(); }}>
          <p>{t("users.disableDialog.text")}</p>
        </FormDialog>
      )}
    </main>
  );
}
