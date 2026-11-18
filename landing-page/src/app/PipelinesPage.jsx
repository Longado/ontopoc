import React, { useEffect, useState } from "react";
import { createPipeline, getDatasets, getPipelines } from "./api.js";
import { moveDraft } from "./assistantModel.js";
import { formatDateTime, t } from "./i18n/index.js";
import { PIcon } from "./PipelineIcons.jsx";
import { STATUS_LABEL, pipelineStateText } from "./pipelineModel.js";
import { hrefFor, parseRoute } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { DraftedChip } from "./ui/DraftedChip.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";

export function PipelineState({ item }) {
  return <><StatusChip state={item.state} label={item.state === "needs_look" ? pipelineStateText(item) : undefined} /><DraftedChip item={item} /></>;
}

/** A run's status as an icon and a word (never colour alone). */
export function RunStatus({ status }) {
  const icon = status === "success" ? "success" : status === "failed" ? "cross" : status === "running" ? "clock" : "stop";
  return <span className={`run-status rs-${status}`}><PIcon name={icon} size={14} />{STATUS_LABEL[status] ?? status}</span>;
}

const initial = (who) => String(who ?? "?").trim().slice(0, 1).toUpperCase() || "?";
const open = (href) => (e) => {
  if (!e.target.closest("a, button")) window.location.hash = href;   // the whole row opens the pipeline; a link inside keeps its own target
};

export function PipelinesPage() {
  const [state, reload] = useLoad(getPipelines, []);
  const pipelines = state.data ?? [];
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("pipeline.bar.data") }, { label: t("pipeline.bar.pipelines") }]} title={t("pipeline.list.title")} sub={t("pipeline.list.sub")}
        actions={<a className="button primary pl-btn" href={hrefFor({ page: "pipelinenew" })}><PIcon name="plus" size={14} />{t("pipeline.list.new")}</a>} />
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("pipeline.retry")}</button></p>}
      {state.status === "loading" && !state.data && <div className="pl-skeleton table" aria-label={t("pipeline.loading")}><i /><i /><i /></div>}
      {state.data && !pipelines.length && <EmptyState icon="pipeline" title={t("pipeline.list.emptyTitle")} text={t("pipeline.list.emptyText")} action={{ label: t("pipeline.list.new"), href: hrefFor({ page: "pipelinenew" }) }} />}
      {pipelines.length > 0 && (
        <div className="pl-resource">
          <div className="pl-resource-bar"><span>{t("pipeline.list.count", { count: pipelines.length })}</span></div>
          <table>
            <thead>
              <tr><th>{t("pipeline.list.name")}</th><th>{t("pipeline.list.status")}</th><th>{t("pipeline.list.lastRun")}</th><th>{t("pipeline.list.outputs")}</th><th>{t("pipeline.list.createdBy")}</th></tr>
            </thead>
            <tbody>
              {pipelines.map((p) => {
                const href = hrefFor({ page: "pipeline", name: p.id, view: "edit" });
                return (
                  <tr key={p.id} className="clickable" onClick={open(href)}>
                    <td>
                      <div className="pl-name-cell">
                        <span className="pl-res-icon"><PIcon name="pipeline" size={16} /></span>
                        <div><a className="pl-res-name" href={href}>{p.name}</a>{p.description && <p className="pl-res-desc">{p.description}</p>}</div>
                      </div>
                    </td>
                    <td><PipelineState item={p} /></td>
                    <td>
                      {p.last_run ? (
                        <a className="pl-lastrun" href={hrefFor({ page: "pipeline", name: p.id, view: "run", run: p.last_run.id })}>
                          <RunStatus status={p.last_run.status} />
                          <span className="muted">{formatDateTime(p.last_run.started_at)} · {p.last_run.who ?? t("pipeline.unsigned")}</span>
                        </a>
                      ) : <span className="faint">{t("pipeline.list.neverRun")}</span>}
                    </td>
                    <td>
                      {p.outputs.length ? p.outputs.map((o) => (
                        <span key={o.dataset} className="output-chip">
                          <a href={hrefFor({ page: "dataset", name: o.dataset, tab: "fields" })}>{o.dataset}</a>
                          {o.stale && <span className="pl-badge warn">{o.word}</span>}
                        </span>
                      )) : <span className="faint">{t("pipeline.list.noOutputs")}</span>}
                    </td>
                    <td>{p.created_by ? <span className="pl-owner"><i aria-hidden="true">{initial(p.created_by)}</i>{p.created_by}</span> : <span className="faint">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

/** A pipeline starts as one input step; everything else is added on its page. */
export function PipelineNew() {
  const [datasets, setDatasets] = useState([]);
  const start = parseRoute(window.location.hash).dataset ?? "";   // "Use it in a pipeline" arrives with the dataset
  const [name, setName] = useState(start ? t("pipeline.new.suggest", { dataset: start }) : "");
  const [description, setDescription] = useState("");
  const [dataset, setDataset] = useState(start);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    getDatasets().then(setDatasets, (e) => setError(e.message));
  }, []);
  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const made = await createPipeline(name.trim(), description.trim(), { steps: [{ id: "in1", type: "input", dataset }] });
      moveDraft(window.sessionStorage, `new:${dataset}`, made.id);   // steps the assistant drafted for this dataset go to the new pipeline's editor
      window.location.hash = hrefFor({ page: "pipeline", name: made.id, view: "edit" });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("pipeline.bar.data") }, { label: t("pipeline.bar.pipelines"), href: hrefFor({ page: "pipelines" }) }, { label: t("pipeline.new.crumb") }]} title={t("pipeline.new.title")} sub={t("pipeline.new.sub")} />
      <form className="pl-form" onSubmit={create}>
        <label className="field">
          <span className="caption">{t("pipeline.new.name")}</span>
          <input type="text" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder={t("pipeline.new.namePlaceholder")} />
        </label>
        <label className="field">
          <span className="caption">{t("pipeline.new.description")}</span>
          <input type="text" value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <div className="field">
          <span className="caption">{t("pipeline.new.dataset")}</span>
          <Select label={t("pipeline.new.dataset")} value={dataset} onChange={setDataset}>
            <option value="">{t("pipeline.new.pick")}</option>
            {datasets.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
          </Select>
        </div>
        <div className="pl-form-actions">
          <button className="primary" type="submit" disabled={busy || !name.trim() || !dataset}>{t("pipeline.new.create")}</button>
          <a className="button secondary" href={hrefFor({ page: "pipelines" })}>{t("pipeline.new.cancel")}</a>
          {error && <span className="error">{error}</span>}
        </div>
      </form>
    </main>
  );
}
