import React, { useState } from "react";
import { SKILL_HREF, STANDING_CSV_HREF, createAgentToken, getAgentInfo, getAgentTokens, getUsers, revokeAgentToken } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { FormDialog } from "./FormDialog.jsx";
import { isAdmin, roleLabel } from "./authModel.js";
import { EXPIRY_DAYS, connectConfig, endText, firstSentence, groupTools, scopeWord, scopes, skillText, toolInfo, tokenState } from "./agentModel.js";
import { useT } from "./i18n/index.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";

/** Tokens that act as a named person: the admin makes one here, it is shown once, and can be revoked. */
function Tokens({ onMade }) {
  const t = useT();
  const [tokens, reload] = useLoad(() => getAgentTokens(), []);
  const [users] = useLoad(() => getUsers(), []);
  const [who, setWho] = useState("");
  const [label, setLabel] = useState("");
  const [scope, setScope] = useState("read");
  const [days, setDays] = useState("90");
  const [made, setMade] = useState(null);
  const [error, setError] = useState("");
  const [revoking, setRevoking] = useState(null);   // the token the admin is about to revoke
  const [revoked, setRevoked] = useState(false);
  const active = (users.data ?? []).filter((u) => !u.disabled && u.role !== "admin");   // an admin's account gets no token: a leaked one would be the whole service
  const create = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const body = await createAgentToken(Number(who), label.trim(), scope, Number(days));
      setMade(body);
      onMade(body.token);
      setLabel("");
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  const revoke = async (id) => {
    await revokeAgentToken(id);
    setMade(null);
    onMade("");
    setRevoked(true);
    reload();
  };
  return (
    <>
      <h2 className="section">{t("agents.tokens.title")}</h2>
      <p className="muted">{t("agents.tokens.text")}</p>
      <form onSubmit={create} className="inline wide token-form">
        <Select label={t("agents.tokens.who")} value={who} onChange={setWho}>
          <option value="">{t("agents.tokens.pick")}</option>
          {active.map((u) => <option key={u.id} value={u.id}>{t("agents.tokens.person", { name: u.display_name, role: roleLabel(u.role) })}</option>)}
        </Select>
        <input type="text" aria-label={t("agents.tokens.purposeAria")} placeholder={t("agents.tokens.purposePlaceholder")} value={label} onChange={(e) => setLabel(e.target.value)} />
        <Select label={t("agents.tokens.permission")} value={scope} onChange={setScope}>
          {scopes().map(([k, text]) => <option key={k} value={k}>{text}</option>)}
        </Select>
        <Select label={t("agents.tokens.validFor")} value={days} onChange={setDays}>
          {EXPIRY_DAYS.map((d) => <option key={d} value={d}>{t("agents.tokens.days", { days: d })}</option>)}
        </Select>
        <button className="secondary" type="submit" disabled={!who || !label.trim()}>{t("agents.tokens.create")}</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {revoked && <p className="ok" role="status">{t("agents.tokens.revokedNote")}</p>}
      {made && (
        <p className="token">
          <span className="caption">{t("agents.tokens.made", { name: made.display_name })}</span>
          <input type="text" readOnly value={made.token} aria-label={t("agents.tokens.newAria")} onFocus={(e) => e.target.select()} />
        </p>
      )}
      {tokens.status === "error" && <p className="error">{tokens.error}</p>}
      {(tokens.data ?? []).length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("agents.tokens.col.who")}</th><th>{t("agents.tokens.col.purpose")}</th><th>{t("agents.tokens.col.permission")}</th><th>{t("agents.tokens.col.expires")}</th><th>{t("agents.tokens.col.lastUsed")}</th><th></th></tr></thead>
            <tbody>
              {tokens.data.map((tok) => (
                <tr key={tok.id}>
                  <td>{tok.display_name} <span className="muted small">{roleLabel(tok.role)}</span></td>
                  <td>{tok.label}</td>
                  <td>{scopeWord(tok)}</td>
                  <td>{endText(tok)}</td>
                  <td>{tok.last_used_at ? timeText(tok.last_used_at) : <span className="faint">{t("agents.tokens.never")}</span>}</td>
                  <td>{tok.revoked || tok.expired ? <span className="muted">{tokenState(tok)}</span> : <button className="plain" onClick={() => { setRevoked(false); setRevoking(tok); }}>{t("agents.tokens.revoke")}</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {revoking && (
        <FormDialog title={t("agents.tokens.revokeTitle")} submitLabel={t("agents.tokens.revokeConfirm")} valid onClose={() => setRevoking(null)} onSubmit={() => revoke(revoking.id)}>
          <p>{t("agents.tokens.revokeText", { label: revoking.label, name: revoking.display_name })}</p>
        </FormDialog>
      )}
    </>
  );
}

export function AgentsPage() {
  const t = useT();
  const { user } = useAuth();
  const [info] = useLoad(() => getAgentInfo(), []);
  const [token, setToken] = useState("");
  const i = info.data;
  const config = i ? connectConfig({ command: i.command, origin: window.location.origin, token }) : "";
  const localConfig = i?.command.local_src ? connectConfig({ command: i.command, origin: window.location.origin, token, local: true }) : "";
  const [copied, setCopied] = useState("");
  const copy = async (which, text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
    } catch {
      setCopied("");
    }
  };
  return (
    <main className="page">
      <PageHeader title={t("agents.title")} sub={t("agents.sub")} />
      {info.status === "error" && <p className="error">{info.error}</p>}
      {i && (
        <>
          <h2 className="section">{t("agents.tools.title")}</h2>
          <div className="table-wrap">
            <table className="wraps">
              <thead><tr><th>{t("agents.tools.tool")}</th><th>{t("agents.tools.what")}</th><th>{t("agents.tools.args")}</th></tr></thead>
              <tbody>
                {groupTools(i.tools).map((g) => (
                  <React.Fragment key={g.group}>
                    <tr className="group-row"><th colSpan="3">{t("agents.groupRow", { label: g.label, hint: g.hint })}</th></tr>
                    {g.tools.map((tool) => (
                      <tr key={tool.name}>
                        <td className="keep"><code>{tool.name}</code></td>
                        <td>{toolInfo(tool.name).line || firstSentence(tool.description)}</td>
                        <td>{tool.arguments.length ? tool.arguments.map((a) => (a.required ? a.name : t("agents.tools.optional", { name: a.name }))).join(t("ask.sep")) : <span className="faint">{t("agents.tools.none")}</span>}</td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">{t("agents.tools.noteRead")}</p>
          <p className="muted small">{t("agents.tools.noteAll", { count: i.more_with_all })}</p>
          <h2 className="section">{t("agents.connect.title")}</h2>
          <p className="muted">{t("agents.connect.text")}</p>
          <pre className="code-box">{config}</pre>
          <div className="inline"><button className="secondary" onClick={() => copy("generic", config)}>{copied === "generic" ? t("agents.connect.copied") : t("agents.connect.copy")}</button></div>
          {localConfig && (
            <>
              <h3 className="item-title">{t("agents.local.title")}</h3>
              <p className="muted small">{t("agents.local.text")}</p>
              <pre className="code-box">{localConfig}</pre>
              <div className="inline"><button className="secondary" onClick={() => copy("local", localConfig)}>{copied === "local" ? t("agents.connect.copied") : t("agents.connect.copy")}</button></div>
            </>
          )}
          {isAdmin(user) ? <Tokens onMade={setToken} /> : <p className="muted">{t("agents.tokens.adminOnly")}</p>}
          <h2 className="section">{t("agents.skill.title")}</h2>
          <p className="muted">{t("agents.skill.sentence", { text: skillText(i.skill) })}</p>
          <div className="inline"><a className="button secondary" href={SKILL_HREF} download={i.skill.file}>{t("agents.skill.download")}</a></div>
          <p className="muted small">{t("agents.standing.text")}</p>
          <div className="inline"><a className="button secondary" href={STANDING_CSV_HREF} download>{t("agents.standing.download")}</a></div>
        </>
      )}
      {!i && info.status === "loading" && <p className="muted">{t("agents.loading")}</p>}
    </main>
  );
}
