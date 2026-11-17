import React, { useState } from "react";
import { getPipelineRun, getPipelineRuns, getPipelineVersions } from "./api.js";
import { formatDateTime, t } from "./i18n/index.js";
import { PipelineGraph } from "./PipelineGraph.jsx";
import { KindChip, PIcon } from "./PipelineIcons.jsx";
import { RunStatus } from "./PipelinesPage.jsx";
import { CHANGE_LABEL, KIND_LABEL, cardFlags, countsText, durationText, failureLines, friendlyError, llmRunText, numberText, offListLines, rowsText, stepSummary, stepTitle, versionsText } from "./pipelineModel.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

const runHref = (name, id) => hrefFor({ page: "pipeline", name, view: "run", run: id });

export function PipelineRuns({ detail }) {
  const [state, reload] = useLoad(() => getPipelineRuns(detail.name), [detail.name]);
  const runs = state.data ?? [];
  return (
    <div className="pl-page">
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("pipeline.retry")}</button></p>}
      {state.status === "loading" && !state.data && <div className="pl-skeleton table" aria-label={t("pipeline.loading")}><i /><i /><i /></div>}
      {state.data && !runs.length && (
        <div className="pl-empty-block"><span className="empty-icon"><PIcon name="play" size={20} /></span><p className="empty-title">{t("pipeline.runs.emptyTitle")}</p><p className="empty-text">{t("pipeline.runs.empty")}</p></div>
      )}
      {runs.length > 0 && (
        <div className="pl-resource">
          <table>
            <thead><tr><th>{t("pipeline.runs.status")}</th><th>{t("pipeline.runs.run")}</th><th>{t("pipeline.runs.who")}</th><th>{t("pipeline.runs.started")}</th><th className="num">{t("pipeline.runs.duration")}</th><th className="num">{t("pipeline.runs.version")}</th></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="clickable" onClick={(e) => { if (!e.target.closest("a")) window.location.hash = runHref(detail.name, r.id); }}>
                  <td><RunStatus status={r.status} /></td>
                  <td><a className="pl-res-name" href={runHref(detail.name, r.id)}>{t("pipeline.runs.nth", { id: r.id })}</a></td>
                  <td>{r.who ?? t("pipeline.unsigned")}</td>
                  <td title={r.started_at}>{formatDateTime(r.started_at)}</td>
                  <td className="num">{durationText(r.duration_ms)}</td>
                  <td className="num">v{r.definition_version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function PipelineRun({ detail, id }) {
  const [state, reload] = useLoad(() => getPipelineRun(detail.name, id), [detail.name, id]);
  const run = state.data;
  return (
    <div className="pl-page">
      <p className="pl-backline"><a href={hrefFor({ page: "pipeline", name: detail.name, view: "runs" })}>&larr; {t("pipeline.run.all")}</a></p>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("pipeline.retry")}</button></p>}
      {state.status === "loading" && !run && <div className="pl-skeleton table" aria-label={t("pipeline.loading")}><i /><i /><i /></div>}
      {run && (
        <>
          <div className="pl-run-head">
            <h2>{t("pipeline.run.title", { id: run.id })}</h2>
            <RunStatus status={run.status} />
          </div>
          <dl className="pl-facts">
            <div><dt>{t("pipeline.run.who")}</dt><dd>{run.who ?? t("pipeline.unsigned")}</dd></div>
            <div><dt>{t("pipeline.run.started")}</dt><dd>{formatDateTime(run.started_at)}{run.finished_at && <span className="muted"> · {t("pipeline.run.took", { time: durationText(run.duration_ms) })}</span>}</dd></div>
            <div><dt>{t("pipeline.run.version")}</dt><dd>{t("pipeline.run.versionN", { version: run.definition_version })}</dd></div>
            <div><dt>{t("pipeline.run.read")}</dt><dd>{versionsText(run.input_versions) || "—"}</dd></div>
          </dl>
          {run.error && <div className="pl-errcard" role="alert"><PIcon name="alert" size={16} /><div><strong>{t("pipeline.run.failedTitle")}</strong><p>{friendlyError(run.error, detail.spec.steps)}</p></div></div>}
          {run.outputs.length > 0 && (
            <>
              <h3 className="pl-section">{t("pipeline.run.wrote")}</h3>
              <ul className="pl-written">
                {run.outputs.map((o) => (
                  <li key={o.dataset}>
                    <PIcon name="output" size={16} />
                    <a href={hrefFor({ page: "dataset", name: o.dataset, tab: "versions" })}>{o.dataset}</a>
                    <span className="pl-badge neutral">v{o.version}</span>
                    <span>{rowsText(o.rows)}</span>
                    {!o.created_version && <span className="muted">{t("pipeline.run.unchanged")}</span>}
                  </li>
                ))}
              </ul>
            </>
          )}
          {run.nodes.length > 0 && (
            <>
              <h3 className="pl-section">{t("pipeline.run.steps")}</h3>
              <div className="pl-resource">
                <table>
                  <thead><tr><th>{t("pipeline.run.step")}</th><th>{t("pipeline.run.rows")}</th><th>{t("pipeline.run.did")}</th><th>{t("pipeline.run.problems")}</th></tr></thead>
                  <tbody>
                    {run.nodes.map((n) => {
                      const flags = cardFlags(n).filter((f) => f.level !== "note");
                      return (
                        <tr key={n.id} className="wrap-row">
                          <td><span className="pl-step-cell"><KindChip step={{ type: n.type }} />{KIND_LABEL[n.type]} <span className="muted">{n.id}</span></span></td>
                          <td className="keep">{countsText(n)}</td>
                          <td>{(n.operators ?? []).map((op, i) => <p key={i} className="small">{i + 1}. {op.text}</p>)}{n.llm && <p className="small">{llmRunText(n.llm)}{n.llm.called > 0 && `; ${t("pipeline.run.asked", { count: n.llm.called, n: numberText(n.llm.called) })}`}</p>}{n.llm && offListLines(n.llm).map((l) => <p key={l} className="warn small">{l}</p>)}{n.join && <p className="small">{t("pipeline.run.joined", { matched: n.join.matched_left, left: n.join.left_rows })}{n.join.extra_rows > 0 ? t("pipeline.run.extra", { count: n.join.extra_rows }) : ""}</p>}</td>
                          <td>{failureLines(n).map((l) => <p key={l} className="warn small">{l}</p>)}{flags.filter((f) => !failureLines(n).includes(f.text)).map((f) => <p key={f.text} className={`${f.level === "bad" ? "bad" : "warn"} small`}>{f.text}</p>)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function ChangeRow({ change, steps, titleOf }) {
  const line = (step) => stepSummary(step, steps).map((l, i) => <p key={i} className="small">{l}</p>);
  return (
    <div className={`change change-${change.change}`}>
      <div className="change-head"><span className="change-tag">{CHANGE_LABEL[change.change]}</span><strong>{titleOf(change, steps)}</strong></div>
      <div className="change-sides">
        <div><p className="caption">{t("pipeline.history.before")}</p>{change.before ? line(change.before) : <p className="faint small">{t("pipeline.history.none")}</p>}</div>
        <div><p className="caption">{t("pipeline.history.after")}</p>{change.after ? line(change.after) : <p className="faint small">{t("pipeline.history.none")}</p>}</div>
      </div>
    </div>
  );
}

export const changeTitle = (change, steps) => `${KIND_LABEL[(change.after ?? change.before).type]} ${stepTitle(change.after ?? change.before, steps)}`;

/** The versions kept, any one of them read-only (as the graph of its steps), and two of them compared step by step. */
export function PipelineHistory({ detail }) {
  const [list] = useLoad(() => getPipelineVersions(detail.name), [detail.name]);
  const [from, setFrom] = useState(null);
  const [to, setTo] = useState(null);
  const versions = list.data?.versions ?? [];
  const latest = versions[0]?.version;
  const a = from ?? (versions[1]?.version ?? latest);
  const b = to ?? latest;
  const [compared] = useLoad(() => (list.data ? getPipelineVersions(detail.name, a, b) : Promise.resolve(null)), [detail.name, a, b, !!list.data]);
  const [viewing, setViewing] = useState(null);
  const [past] = useLoad(() => (viewing ? getPipelineVersions(detail.name, viewing, viewing) : Promise.resolve(null)), [detail.name, viewing]);
  return (
    <div className="pl-page">
      {list.status === "error" && <p className="error">{list.error}</p>}
      {list.status === "loading" && !list.data && <div className="pl-skeleton table" aria-label={t("pipeline.loading")}><i /><i /><i /></div>}
      {versions.length > 0 && (
        <div className="pl-resource">
          <table>
            <thead><tr><th>{t("pipeline.history.version")}</th><th>{t("pipeline.history.savedBy")}</th><th>{t("pipeline.history.time")}</th><th className="num">{t("pipeline.history.steps")}</th><th /></tr></thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.version} className={viewing === v.version ? "selected" : ""}>
                  <td><strong>{t("pipeline.history.versionN", { version: v.version })}</strong>{v.version === detail.definition_version && <span className="pl-badge ok">{t("pipeline.history.current")}</span>}</td>
                  <td>{v.saved_by ?? t("pipeline.unsigned")}</td>
                  <td>{formatDateTime(v.saved_at)}</td>
                  <td className="num">{v.steps}</td>
                  <td className="actions"><button type="button" className="secondary pl-btn-sm" onClick={() => setViewing(viewing === v.version ? null : v.version)}>{viewing === v.version ? t("pipeline.history.hide") : t("pipeline.history.view")}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {viewing && past.data?.spec && (
        <div className="past">
          <h3 className="pl-section">{t("pipeline.history.readOnly", { version: viewing })}</h3>
          <div className="past-graph"><PipelineGraph steps={past.data.spec.steps} nodes={{}} selected={null} onSelect={() => {}} /></div>
          <ul className="pl-lines">{past.data.spec.steps.flatMap((s) => stepSummary(s, past.data.spec.steps).map((l, i) => <li key={`${s.id}${i}`}><span className="muted">{KIND_LABEL[s.type]}</span> {l}</li>))}</ul>
        </div>
      )}
      {versions.length > 1 && (
        <>
          <h3 className="pl-section">{t("pipeline.history.compare")}</h3>
          <div className="pl-compare">
            <Select label={t("pipeline.history.from")} value={String(a)} onChange={(v) => setFrom(Number(v))}>{versions.map((v) => <option key={v.version} value={v.version}>{t("pipeline.history.versionN", { version: v.version })}</option>)}</Select>
            <span className="muted">{t("pipeline.history.changedTo")}</span>
            <Select label={t("pipeline.history.to")} value={String(b)} onChange={(v) => setTo(Number(v))}>{versions.map((v) => <option key={v.version} value={v.version}>{t("pipeline.history.versionN", { version: v.version })}</option>)}</Select>
          </div>
          {compared.status === "error" && <p className="error">{compared.error}</p>}
          {compared.data && !compared.data.changes.length && <p className="muted">{t("pipeline.history.same")}</p>}
          {compared.data?.changes.map((c) => <ChangeRow key={`${c.id}${c.change}`} change={c} steps={compared.data.spec.steps} titleOf={changeTitle} />)}
        </>
      )}
    </div>
  );
}

export { ChangeRow };
