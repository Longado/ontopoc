import React, { useState } from "react";
import { createSource, getSources, updateSource } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { isAdmin } from "./authModel.js";
import { portAfterKind } from "./connectModel.js";
import { timeText } from "./format.js";
import { t, useT } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { ConnectWays, PassiveWay } from "./SourceWays.jsx";
import { SourceWizard } from "./SourceWizard.jsx";
import { KINDS, TLS_MODES, sourceBody, sourceProblem, statusText, tlsDefault, tlsWarning } from "./sourceModel.js";
import { useLoad } from "./useLoad.js";
import { FormDialog } from "./FormDialog.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";

const CHIP = { ok: "confirmed", failed: "failed", untested: "draft" };

export function SourceState({ source }) {
  return <StatusChip state={CHIP[source.status] ?? source.status} label={statusText(source)} />;
}

/** What a builder who is not an admin sees instead of the connect button: who connects databases, and the same "send this message" panel the admin's passive way uses (open, since it is their only way). */
function AskAdmin() {
  return (
    <section className="card ask-admin">
      <h2>{t("sources.ask.title")}</h2>
      <p className="muted">{t("sources.ask.text")}</p>
      <PassiveWay audience="admin" defaultOpen />
    </section>
  );
}

/** Make a source, or (with `source`) change its connection. The password is never filled in: a blank one keeps the saved one. */
export function SourceForm({ source, onClose, onDone }) {
  useT();
  const editing = !!source;
  const [f, setF] = useState({
    name: source?.name ?? "", kind: source?.kind ?? "postgresql", host: source?.host ?? "", port: String(source?.port ?? 5432),
    database: source?.database ?? "", username: source?.username ?? "", password: "", tls: source?.tls ?? null,   // null: the default for this host until one is chosen
    ca: "", dropCa: false,   // the CA is never sent back: a saved one shows as set, a pasted one replaces it
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const problem = sourceProblem(f, editing, source);
  const tls = f.tls ?? tlsDefault(f.host);
  const body = sourceBody(f, tls);
  return (
    <FormDialog title={editing ? t("sources.form.editTitle", { name: source.name }) : t("sources.form.newTitle")} submitLabel={editing ? t("common.save") : t("sources.form.create")} onClose={onClose} valid={!problem}
      onSubmit={async () => { await (editing ? updateSource(body) : createSource(body)); onDone(); }}>
      {!editing && <label className="field"><span className="caption">{t("sources.form.name")}</span><input type="text" value={f.name} maxLength={60} onChange={set("name")} /></label>}
      {!editing && (
        <div className="field">
          <span className="caption">{t("sources.form.kind")}</span>
          <Select label={t("sources.form.kind")} value={f.kind} onChange={(kind) => setF({ ...f, kind, port: portAfterKind(kind) })}>
            {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </Select>
        </div>
      )}
      <label className="field"><span className="caption">{t("sources.form.host")}</span><input type="text" value={f.host} placeholder="db.example.com" autoComplete="off" onChange={set("host")} /></label>
      <label className="field"><span className="caption">{t("sources.form.port")}</span><input type="text" inputMode="numeric" value={f.port} onChange={set("port")} /></label>
      <label className="field"><span className="caption">{t("sources.form.database")}</span><input type="text" value={f.database} autoComplete="off" onChange={set("database")} /></label>
      <label className="field"><span className="caption">{t("sources.form.username")}</span><input type="text" value={f.username} autoComplete="off" onChange={set("username")} /></label>
      <label className="field">
        <span className="caption">{editing ? t("sources.form.passwordEdit") : t("sources.form.password")}</span>
        <input type="password" value={f.password} autoComplete="new-password" onChange={set("password")} />
      </label>
      <div className="field">
        <span className="caption">{t("sources.form.tls")}</span>
        <Select label={t("sources.form.tls")} value={tls} onChange={(v) => setF({ ...f, tls: v })}>
          {TLS_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </Select>
      </div>
      <p className="hint">{t("sources.form.tlsHint")}</p>
      {tls === "none" && <p className="warn">{tlsWarning()}</p>}
      {tls === "required" && (
        <label className="field">
          <span className="caption">{source?.custom_ca ? t("sources.form.caSet") : t("sources.form.ca")}</span>
          <textarea rows={4} value={f.ca} placeholder="-----BEGIN CERTIFICATE-----" spellCheck={false} onChange={set("ca")} />
        </label>
      )}
      {tls === "required" && source?.custom_ca && !f.ca.trim() && (
        <label className="check"><input type="checkbox" checked={f.dropCa} onChange={(e) => setF({ ...f, dropCa: e.target.checked })} /> {t("sources.form.dropCa")}</label>
      )}
      <p className="hint">{t("sources.form.passwordNote")}</p>
      {problem && <p className="hint">{problem}</p>}
    </FormDialog>
  );
}

export function SourcesPage() {
  useT();
  const admin = isAdmin(useAuth().user);
  const [state, reload] = useLoad(getSources, []);
  const [making, setMaking] = useState(false);
  const sources = state.data ?? [];
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("data.crumb.data") }, { label: t("sources.title") }]} title={t("sources.title")} sub={t("sources.sub")}
        actions={admin && <button className="primary" onClick={() => setMaking(true)}>{t("sources.connect")}</button>} />
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">{t("common.loading")}</p>}
      {state.data && !admin && <AskAdmin />}
      {state.data && admin && <ConnectWays onConnect={() => setMaking(true)} />}
      {state.data && !sources.length && admin && <EmptyState icon="plug" title={t("sources.empty.title")} text={t("sources.empty.text")} />}
      {sources.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("sources.col.name")}</th><th>{t("sources.col.type")}</th>{admin && <th>{t("sources.col.address")}</th>}<th>{t("sources.col.status")}</th><th>{t("sources.col.datasets")}</th></tr></thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.name}>
                  <td><a href={hrefFor({ page: "source", name: s.name })}>{s.name}</a></td>
                  <td>{s.kind_label}</td>
                  {admin && <td>{s.host}:{s.port}/{s.database}{s.local && <span className="faint"> {t("sources.local")}</span>}</td>}
                  <td><SourceState source={s} />{s.status_at && <span className="faint small"> {timeText(s.status_at)}</span>}</td>
                  <td>
                    {s.tables.length ? s.tables.map((tb) => (
                      <span key={tb.table} className="output-chip"><a href={hrefFor({ page: "dataset", name: tb.dataset, tab: "fields" })}>{tb.dataset}</a> </span>
                    )) : <span className="faint">{t("sources.noneYet")}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {making && <SourceWizard onClose={() => setMaking(false)} onDone={reload} />}
    </main>
  );
}
