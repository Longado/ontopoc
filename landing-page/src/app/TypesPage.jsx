import React, { useEffect, useRef, useState } from "react";
import { getDatasets, getModelReady, getTypeList, suggestTypes } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { t } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { reconfirmText, stateText } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { DbtImportDialog } from "./DbtImportDialog.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";
import { DraftedChip } from "./ui/DraftedChip.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";

export function State({ item }) {
  if (!item.state && !item.model_draft) return <span className="state state-none">{stateText(item)}</span>;   // a column nobody gave meanings to has no state
  return <><StatusChip state={item.state} modelDraft={item.model_draft} /><DraftedChip item={item} /></>;
}

/** Asks the model for object types from some datasets. It runs as a task: what it proposed and what the checks dropped are listed, nothing is confirmed. */
function SuggestDialog({ onClose, onDone }) {
  const ref = useRef(null);
  const [datasets, setDatasets] = useState([]);
  const [chosen, setChosen] = useState([]);
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [sending, setSending] = useState(false);
  const [waited, setWaited] = useState(0);
  const [modelReady, setModelReady] = useState(true);
  useEffect(() => {
    ref.current.showModal();
    getDatasets().then((list) => {
      setDatasets(list);
      if (list.length === 1) setChosen([list[0].name]);   // the only dataset is the one to read
    }, (e) => setError(e.message));
    getModelReady().then(setModelReady);
  }, []);
  useEffect(() => {
    if (!sending) return undefined;
    setWaited(0);
    const timer = setInterval(() => setWaited((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [sending]);
  const close = () => {
    if (sending) return;   // the service keeps writing the drafts when the page goes: closing now would lose the list and invite a second run
    ref.current.close();
    onClose();
  };
  const send = async () => {
    setSending(true);
    setError("");
    try {
      setResult(await suggestTypes(chosen, purpose));
      onDone();
    } catch (e) {
      setError(e.message);
    }
    setSending(false);
  };
  const toggle = (name, on) => setChosen(on ? [...chosen, name] : chosen.filter((n) => n !== name));
  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); close(); }}>
      <div className="dialog-body">
        <h2>{t("types.suggest.title")}</h2>
        {!result && !modelReady && <p className="warn">{t("types.suggest.noModel")}</p>}
        {!result && (
          <>
            <fieldset className="keys">
              <legend>{t("types.suggest.datasets")}</legend>
              {datasets.map((d) => (
                <label key={d.name}>
                  <input type="checkbox" checked={chosen.includes(d.name)} onChange={(e) => toggle(d.name, e.target.checked)} />
                  {d.name}
                </label>
              ))}
            </fieldset>
            <label className="field">
              <span className="caption">{t("types.suggest.purpose")}</span>
              <input type="text" value={purpose} maxLength={400} placeholder={t("types.suggest.purposePlaceholder")} onChange={(e) => setPurpose(e.target.value)} />
            </label>
            <p className="hint">{t("types.suggest.hint")}</p>
          </>
        )}
        {result && (
          <>
            <p>{t("types.suggest.proposed", { count: result.proposed.length, colon: result.proposed.length > 0 ? t("types.colon") : "" })}</p>
            <ul className="results">
              {result.proposed.map((p) => <li key={p.id}><a href={hrefFor({ page: "type", id: p.id, tab: "props" })}>{p.name}</a></li>)}
            </ul>
            {result.rejected.length > 0 && (
              <>
                <p style={{ marginTop: 12 }}>{t("types.suggest.rejected", { count: result.rejected.length })}</p>
                <ul className="results">
                  {result.rejected.map((r, i) => <li key={i}>{r.name}{t("types.colon")} <span className="muted">{r.reason}</span></li>)}
                </ul>
              </>
            )}
          </>
        )}
      </div>
      <div className="actions">
        {error ? <span className="error">{error}</span> : <span></span>}
        {result ? (
          <button className="primary" onClick={close}>{t("common.close")}</button>
        ) : (
          <>
            {sending && <span className="muted">{t("types.suggest.waiting", { seconds: waited })}</span>}
            <button className="plain" onClick={close} disabled={sending}>{t("common.cancel")}</button>
            <button className="primary" onClick={send} disabled={sending || !chosen.length || !modelReady}>{sending ? t("types.suggest.working") : t("types.suggest.start")}</button>
          </>
        )}
      </div>
    </dialog>
  );
}

export function TypesPage() {
  const [state, reload] = useLoad(getTypeList, []);
  const [suggesting, setSuggesting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [filter, setFilter] = useState("");
  const mayBuild = canBuild(useAuth().user);
  const all = state.data?.types;
  const hidden = state.data?.hidden ?? 0;
  const types = (all ?? []).filter((ty) => `${ty.name} ${ty.id}`.toLowerCase().includes(filter.trim().toLowerCase()));
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("types.list.crumbGroup") }, { label: t("types.list.title") }]} title={t("types.list.title")} sub={t("types.list.sub")}
        actions={mayBuild && (
          <>
            <button className="secondary" onClick={() => setSuggesting(true)}>{t("types.list.suggest")}</button>
            <button className="secondary" onClick={() => setImporting(true)}>{t("types.dbt.open")}</button>
            <a className="button primary" href={hrefFor({ page: "typenew" })}>{t("types.list.new")}</a>
          </>
        )} />
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">{t("common.loading")}</p>}
      {all && !all.length && hidden > 0 && <p className="muted">{t("types.list.hidden", { count: hidden })}</p>}
      {all && !all.length && !hidden && (
        <EmptyState icon="cube" title={t("types.list.emptyTitle")} text={mayBuild ? t("types.list.emptyBuild") : t("types.list.emptyView")}
          action={mayBuild ? { label: t("types.list.new"), href: hrefFor({ page: "typenew" }) } : undefined} />
      )}
      {all?.length > 8 && (
        <div className="list-toolbar">
          <input type="search" className="list-search" aria-label={t("types.list.filter")} placeholder={t("types.list.filter")} value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
      )}
      {types.length > 0 && (
        <div className="table-wrap">
          <table className="resource-table">
            <thead>
              <tr><th>{t("types.list.col.name")}</th><th>{t("types.list.col.id")}</th><th>{t("types.list.col.source")}</th><th>{t("types.list.col.state")}</th><th className="num">{t("types.list.col.objects")}</th><th>{t("types.list.col.confirmedBy")}</th></tr>
            </thead>
            <tbody>
              {types.map((ty) => (
                <tr key={ty.id}>
                  <td><a className="row-name" href={hrefFor({ page: "type", id: ty.id, tab: "props" })}>{ty.name}</a></td>
                  <td className="id">{ty.id}</td>
                  <td>{ty.waiting ? <span className="faint">—</span> : <>{ty.dataset}{ty.dataset_version != null && <span className="muted">{t("types.list.version", { version: ty.dataset_version })}</span>}</>}</td>
                  <td><State item={ty} />{ty.waiting && <span className="muted small"> {reconfirmText(ty.waiting_for)}</span>}{ty.meanings_waiting > 0 && <span className="muted small"> {t("types.list.meaningsWaiting", { count: ty.meanings_waiting })}</span>}</td>
                  <td className="num">{ty.rows ?? "—"}</td>
                  <td>{ty.waiting ? <span className="faint">—</span> : ty.confirmed_by ?? <span className="faint">{t("types.none")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {all?.length > 0 && <p className="hint">{t("types.list.explorerHint")}</p>}
      {all?.length > 0 && hidden > 0 && <p className="hint">{t("types.list.hiddenMore", { count: hidden })}</p>}
      {suggesting && <SuggestDialog onClose={() => setSuggesting(false)} onDone={reload} />}
      {importing && <DbtImportDialog onClose={() => setImporting(false)} onDone={reload} />}
    </main>
  );
}
