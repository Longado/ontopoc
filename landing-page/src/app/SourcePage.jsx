import React, { useState } from "react";
import { deleteSource, getSource, getSourceTables, pullTable, refreshDataset, testSource } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { isAdmin } from "./authModel.js";
import { timeText } from "./format.js";
import { t, useT } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { SourceForm, SourceState } from "./SourcesPage.jsx";
import { ConnectFailure } from "./ConnectFailure.jsx";
import { errorReport } from "./connectModel.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { estimateText, keyColumnsFrom, reasonText, runStatusText, runSummary } from "./sourceModel.js";
import { useLoad } from "./useLoad.js";
import { FormDialog } from "./FormDialog.jsx";

const modeText = (mode) => (mode === "overwrite" || mode === "update_by_key" ? t(`sources.pull.mode.${mode}`) : mode);

function PullDialog({ source, table, onClose, onDone }) {
  useT();
  const [name, setName] = useState(table.split(".").pop());
  const [mode, setMode] = useState("overwrite");
  const [keys, setKeys] = useState("");
  const keyList = keyColumnsFrom(keys);
  const valid = name.trim() && (mode === "overwrite" || keyList.length);
  return (
    <FormDialog title={t("sources.pull.title", { table })} submitLabel={t("sources.pull.submit")} onClose={onClose} valid={valid}
      onSubmit={async () => {
        const run = await pullTable({ source, table, name: name.trim(), mode, ...(mode === "update_by_key" ? { key_columns: keyList } : {}) });
        if (run.status !== "success") throw new Error(run.error || t("sources.pull.failed"));
        onDone();
      }}>
      <label className="field"><span className="caption">{t("sources.pull.name")}</span><input type="text" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} /></label>
      <div className="field">
        <span className="caption">{t("sources.pull.refresh")}</span>
        <Select label={t("sources.pull.refreshAria")} value={mode} onChange={setMode}>
          <option value="overwrite">{t("sources.pull.overwrite")}</option>
          <option value="update_by_key">{t("sources.pull.update")}</option>
        </Select>
      </div>
      {mode === "update_by_key" && (
        <label className="field"><span className="caption">{t("sources.pull.keys")}</span><input type="text" value={keys} placeholder={t("sources.pull.keysHint")} onChange={(e) => setKeys(e.target.value)} /></label>
      )}
    </FormDialog>
  );
}

function Tables({ name, tables, reload }) {
  useT();
  const [pulling, setPulling] = useState(null);
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>{t("sources.tables.table")}</th><th>{t("sources.col.type")}</th><th>{t("sources.tables.rows")}</th><th>{t("sources.tables.dataset")}</th></tr></thead>
        <tbody>
          {tables.map((tb) => (
            <tr key={tb.name}>
              <td>{tb.name}</td>
              <td>{tb.kind}</td>
              <td title={t("sources.tables.estimateTip")}>{tb.rows == null ? <span className="faint">{estimateText(tb.rows)}</span> : estimateText(tb.rows)}</td>
              <td>
                {tb.hidden ? <span className="faint">{t("sources.tables.hidden")}</span>
                  : tb.dataset ? <a href={hrefFor({ page: "dataset", name: tb.dataset, tab: "fields" })}>{tb.dataset}</a>
                    : tb.supported === false ? <span className="faint small">{tb.note}</span>
                      : <button className="plain" onClick={() => setPulling(tb.name)}>{t("sources.tables.pull")}</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {pulling && <PullDialog source={name} table={pulling} onClose={() => setPulling(null)} onDone={reload} />}
    </div>
  );
}

function Runs({ runs }) {
  if (!runs.length) return <p className="muted">{t("sources.runs.none")}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>{t("sources.runs.started")}</th><th>{t("sources.runs.ended")}</th><th>{t("sources.tables.table")}</th><th>{t("sources.runs.how")}</th><th>{t("sources.runs.who")}</th><th>{t("sources.runs.result")}</th><th></th></tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>{timeText(r.started_at)}</td>
              <td>{r.finished_at ? timeText(r.finished_at) : <span className="faint">—</span>}</td>
              <td>{r.item}</td>
              <td>{reasonText(r)}</td>
              <td>{r.who}</td>
              <td><span className={`state ${r.status === "success" ? "state-confirmed" : r.status === "failed" ? "state-rejected" : r.status === "skipped" ? "state-needs_look" : ""}`}>{runStatusText(r)}</span></td>
              <td className="keep">{runSummary(r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SourcePage({ route }) {
  useT();
  const { name } = route;
  const admin = isAdmin(useAuth().user);
  const [state, reload] = useLoad(() => getSource(name), [name]);
  const [live, setLive] = useState(null);   // {status: "loading" | "ready" | "error", tables, error}: the tables in the database now
  const [dialog, setDialog] = useState(null);   // "edit" | "delete"
  const [refreshing, setRefreshing] = useState("");
  const [message, setMessage] = useState("");
  const source = state.data;

  const look = async () => {
    setLive({ status: "loading" });
    try {
      setLive({ status: "ready", tables: await getSourceTables(name) });
    } catch (e) {
      setLive({ status: "error", error: e.message });
    }
  };
  const test = async () => {
    setLive({ status: "loading" });
    setMessage("");
    try {
      const result = await testSource(name);
      setLive(result.status === "ok" ? { status: "ready", tables: result.tables } : { status: "error", error: result.note });
      setMessage(result.status === "ok" ? result.note ?? "" : "");
    } catch (e) {
      setLive({ status: "error", error: e.message });
    }
    reload();
  };
  const refresh = async (dataset) => {
    setRefreshing(dataset);
    setMessage("");
    try {
      const run = await refreshDataset(dataset);
      setMessage(run.status === "success" ? t("sources.page.refreshed", { dataset, summary: runSummary(run) }) : t("sources.page.refreshFailed", { dataset, error: run.error }));
    } catch (e) {
      setMessage(e.message);
    }
    setRefreshing("");
    reload();
  };
  const afterPull = () => { reload(); look(); };
  const removeSource = async () => {
    try {
      await deleteSource(name);
      window.location.hash = hrefFor({ page: "sources" });
    } catch (e) {
      setMessage(e.message);
    }
  };
  // a failed connection is explained once: after a test or a look, what that said; before either, what the last test left on the source
  const failure = live?.status === "error" ? live.error : !live && source?.status === "failed" ? source.status_note : null;
  const report = source && admin && failure ? errorReport({ source: name, kind: source.kind_label, host: source.host, port: source.port, database: source.database, username: source.username, tls: source.tls, message: failure, at: timeText(new Date().toISOString()) }) : "";

  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("data.crumb.data") }, { label: t("sources.title"), href: hrefFor({ page: "sources" }) }, { label: name }]} title={name} status={source && <SourceState source={source} />}
        actions={source && admin && (
          <>
            <button className="secondary" onClick={() => setDialog("edit")}>{t("sources.page.edit")}</button>
            <button className="primary" onClick={test}>{t("sources.page.test")}</button>
          </>
        )}
        more={source && admin ? [{ label: t("sources.page.delete"), danger: true, confirmText: t("sources.page.deleteConfirm", { name }), onClick: removeSource }] : undefined} />
      {state.status === "error" && <p className="error">{state.error} {!state.missing && <button className="plain" onClick={reload}>{t("common.retry")}</button>}</p>}
      {state.status === "loading" && !source && <p className="muted">{t("common.loading")}</p>}
      {source && (
        <>
          <p className="facts">
            <span>{source.kind_label}</span>
            {admin && <span>{source.host}:{source.port}/{source.database}{t("sources.page.account", { username: source.username })}</span>}
            {source.status_at && <span>{t("sources.page.lastTest", { time: timeText(source.status_at) })}</span>}
          </p>
          {admin && source.local && <p className="hint">{t("sources.page.local")}</p>}
          {failure && admin && (
            <ConnectFailure message={failure} report={report}>
              <button className="secondary" onClick={() => setDialog("edit")}>{t("sources.page.edit")}</button>
              <button className="primary" onClick={test}>{t("sources.page.retest")}</button>
            </ConnectFailure>
          )}
          {failure && !admin && <p className="error">{failure}</p>}
          {source.can_write && <p className="warn">{t("sources.page.writable", { note: source.write_note })}</p>}
          {message && <p className="muted">{message}</p>}

          <h2 className="section">{t("sources.page.dbTables")}</h2>
          {!live && <p><button className="secondary" onClick={look}>{t("sources.page.look")}</button></p>}
          {live?.status === "loading" && <p className="muted">{t("sources.page.connecting")}</p>}
          {live?.status === "error" && <p className="muted">{t("sources.page.cannotConnect")} <button className="plain" onClick={look}>{t("common.retry")}</button></p>}
          {live?.status === "ready" && (live.tables.length ? <Tables name={name} tables={live.tables} reload={afterPull} /> : <p className="muted">{t("sources.page.noTables")}</p>)}

          <h2 className="section">{t("sources.page.pulled")}</h2>
          {!source.tables.length ? <p className="muted">{t("sources.page.pulledNone")}</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>{t("sources.tables.dataset")}</th><th>{t("sources.page.fromTable")}</th><th>{t("sources.page.refreshMode")}</th><th></th></tr></thead>
                <tbody>
                  {source.tables.map((tb) => (
                    <tr key={tb.table}>
                      <td><a href={hrefFor({ page: "dataset", name: tb.dataset, tab: "fields" })}>{tb.dataset}</a></td>
                      <td>{tb.table}</td>
                      <td>{modeText(tb.mode)}{tb.key_columns && t("sources.page.keysIn", { keys: tb.key_columns.join(t("data.listSep")) })}</td>
                      <td className="keep"><button className="plain" disabled={refreshing === tb.dataset} onClick={() => refresh(tb.dataset)}>{refreshing === tb.dataset ? t("sources.page.refreshing") : t("sources.page.refreshNow")}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h2 className="section">{t("sources.page.schedules")}</h2>
          {source.schedules.length ? (
            <ul className="plain-list">
              {source.schedules.map((s) => <li key={s.id}><a href="#/schedules">{s.name}</a> {s.when}{!s.enabled && <span className="faint"> {t("sources.page.off")}</span>}</li>)}
            </ul>
          ) : <p className="muted">{t("sources.page.noSchedules")} <a href="#/schedules">{t("sources.page.setSchedule")}</a></p>}

          <h2 className="section">{t("sources.page.runs")}</h2>
          <Runs runs={source.runs} />
        </>
      )}
      {dialog === "edit" && <SourceForm source={source} onClose={() => setDialog(null)} onDone={reload} />}
    </main>
  );
}
