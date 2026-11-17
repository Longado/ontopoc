import React from "react";
import { getAsk, getHealth, getTwoPerson } from "./api.js";
import { t } from "./i18n/index.js";
import { BACKUP_FILES, workspaceRows } from "./settingsModel.js";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";

const CHIP = { ok: "confirmed", warn: "look", unknown: "draft" };   // the chip state each row state is drawn with

const BACKUP_COMMAND = 'sqlite3 workspace.sqlite ".backup /path/backup.sqlite"';

/** Reads what the workspace is set up with; a part this service will not tell comes back as null instead of failing the page. */
async function loadSettings() {
  const ok = (p) => p.then((v) => v, () => null);
  const [ask, two, health] = await Promise.all([ok(getAsk()), ok(getTwoPerson()), ok(getHealth())]);
  return { modelReady: typeof ask?.model_ready === "boolean" ? ask.model_ready : null, twoPerson: two, health };
}

/** Settings · Workspace (admin): whether questions can be answered, the two-person rule, the running build, and what to back up. Read only: each setting changes where it lives. */
export function SettingsPage() {
  const [state] = useLoad(loadSettings, []);
  const rows = state.data ? workspaceRows(state.data) : [];
  return (
    <main className="page settings">
      <PageHeader crumbs={[{ label: t("settings.crumb") }, { label: t("settings.crumb.workspace") }]} title={t("settings.title")} sub={t("settings.sub")} />
      <section className="card" aria-labelledby="ws-title">
        <h2 id="ws-title">{t("settings.status.title")}</h2>
        {!state.data ? <p className="muted">{t("settings.loading")}</p> : (
          <ul className="setting-rows">
            {rows.map((r) => (
              <li key={r.key} className="setting-row">
                <div className="setting-name"><strong>{r.title}</strong><StatusChip state={CHIP[r.state]} label={t(`settings.chip.${r.state}`)} /></div>
                <p className="muted">{r.text}{r.link && <> <a href={r.link.href}>{r.link.label}</a></>}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card" aria-labelledby="backup-title">
        <h2 id="backup-title">{t("settings.backup.title")}</h2>
        <p className="muted">{t("settings.backup.intro")}</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("settings.backup.file")}</th><th>{t("settings.backup.what")}</th></tr></thead>
            <tbody>{BACKUP_FILES.map((f) => <tr key={f.file}><td><code>{f.file}</code></td><td>{f.what}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="muted">{t("settings.backup.howto", { command: BACKUP_COMMAND })}</p>
      </section>
    </main>
  );
}
