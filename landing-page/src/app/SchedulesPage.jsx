import React, { useEffect, useState } from "react";
import { createSchedule, deleteSchedule, getPipelines, getScheduleRuns, getSchedules, getSources, updateSchedule } from "./api.js";
import { timeText } from "./format.js";
import { t, useT } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { CADENCES, weekdayNames, reasonText, runStatusText, runSummary, runnablePipeline, scheduleBody, scheduleProblem } from "./sourceModel.js";
import { browserZone, hourOptions, minuteOptions, timeFromParts, timeParts, zoneChoices, zoneLabel } from "./scheduleTime.js";
import { useLoad } from "./useLoad.js";
import { FormDialog } from "./FormDialog.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { MoreMenu } from "./ui/MoreMenu.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";

/** A fresh schedule form's values: a daily 08:00 run in the browser's own time zone. */
export const newScheduleForm = (extra = {}) => ({ name: "", kind: "source", target: "", cadence: "daily", minute: "0", time: "08:00", weekday: "0", tz: browserZone(), scope: [], ...extra });

/** A 24-hour time of day: two selects, so a computer set to 12 hours does not show AM/PM. */
export function TimeOfDay({ value, onChange }) {
  const { h, m } = timeParts(value);
  const minutes = minuteOptions.includes(m) ? minuteOptions : [...minuteOptions, m].sort();
  return (
    <span className="time-of-day">
      <Select label={t("sources.sched.hourAria")} value={h} onChange={(v) => onChange(timeFromParts(v, m))}>{hourOptions.map((x) => <option key={x} value={x}>{t("sources.sched.hour", { n: x })}</option>)}</Select>
      <Select label={t("sources.sched.minuteAria")} value={m} onChange={(v) => onChange(timeFromParts(h, v))}>{minutes.map((x) => <option key={x} value={x}>{t("sources.sched.minute", { n: x })}</option>)}</Select>
    </span>
  );
}

/** The "when" part of a schedule form, shared by the schedule dialog and the connection guide's last step. `f` is the form, `set(key)(value)` changes one value. */
export function WhenFields({ f, set, allowUpstream }) {
  const cadences = CADENCES.filter((c) => c.key !== "upstream" || allowUpstream);
  return (
    <>
      <div className="field">
        <span className="caption">{t("sources.sched.when")}</span>
        <Select label={t("sources.sched.trigger")} value={f.cadence} onChange={set("cadence")}>
          {cadences.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </Select>
      </div>
      {f.cadence === "hourly" && <label className="field"><span className="caption">{t("sources.sched.minuteOfHour")}</span><input type="text" inputMode="numeric" value={f.minute} onChange={(e) => set("minute")(e.target.value)} /></label>}
      {f.cadence === "weekly" && (
        <div className="field">
          <span className="caption">{t("sources.sched.weekday")}</span>
          <Select label={t("sources.sched.weekday")} value={f.weekday} onChange={set("weekday")}>{weekdayNames().map((d, i) => <option key={d} value={i}>{d}</option>)}</Select>
        </div>
      )}
      {(f.cadence === "daily" || f.cadence === "weekly") && <div className="field"><span className="caption">{t("sources.sched.time")}</span><TimeOfDay value={f.time} onChange={set("time")} /></div>}
      {f.cadence !== "upstream" && (
        <label className="field">
          <span className="caption">{t("sources.sched.tz")}</span>
          <Select label={t("sources.sched.tzAria")} value={f.tz} onChange={set("tz")}>
            {(zoneChoices(browserZone()).includes(f.tz) ? zoneChoices(browserZone()) : [f.tz, ...zoneChoices(browserZone())]).map((z) => <option key={z} value={z}>{zoneLabel(z)}{z === browserZone() ? t("sources.sched.thisComputer") : ""}</option>)}
          </Select>
          <span className="muted small">{t("sources.sched.runsIn", { zone: zoneLabel(f.tz) })}</span>
        </label>
      )}
      {f.cadence === "upstream" && <p className="hint">{t("sources.sched.upstreamHint")}</p>}
    </>
  );
}

function ScheduleForm({ sources, pipelines, onClose, onDone }) {
  useT();
  const [f, setF] = useState(() => newScheduleForm());
  const set = (k) => (v) => setF({ ...f, [k]: v });
  const source = sources.find((s) => s.name === f.target);
  const targets = f.kind === "source" ? sources.filter((s) => s.tables.length) : pipelines.filter(runnablePipeline);
  const problem = scheduleProblem(f, sources, pipelines);
  const toggle = (table) => set("scope")(f.scope.includes(table) ? f.scope.filter((x) => x !== table) : [...f.scope, table]);
  return (
    <FormDialog title={t("sources.sched.newTitle")} submitLabel={t("sources.form.create")} onClose={onClose} valid={!problem} onSubmit={async () => { await createSchedule(scheduleBody(f)); onDone(); }}>
      <label className="field"><span className="caption">{t("sources.sched.name")}</span><input type="text" value={f.name} maxLength={60} onChange={(e) => set("name")(e.target.value)} /></label>
      <div className="field">
        <span className="caption">{t("sources.sched.what")}</span>
        <Select label={t("sources.sched.what")} value={f.kind} onChange={(kind) => setF({ ...f, kind, target: "", scope: [], cadence: kind === "source" && f.cadence === "upstream" ? "daily" : f.cadence })}>
          <option value="source">{t("sources.sched.kindSource")}</option>
          <option value="pipeline">{t("sources.sched.kindPipeline")}</option>
        </Select>
      </div>
      <div className="field">
        <span className="caption">{f.kind === "source" ? t("sources.sched.sourceLabel") : t("sources.sched.pipelineLabel")}</span>
        <Select label={t("sources.sched.targetAria")} value={f.target} onChange={(target) => setF({ ...f, target, scope: [] })}>
          <option value="">{t("data.upl.choose")}</option>
          {targets.map((tg) => <option key={tg.name} value={tg.name}>{tg.name}</option>)}
        </Select>
      </div>
      {source && source.tables.length > 1 && (
        <fieldset className="field">
          <legend className="caption">{t("sources.sched.scope")}</legend>
          {source.tables.map((tb) => (
            <label key={tb.table}><input type="checkbox" checked={f.scope.includes(tb.table)} onChange={() => toggle(tb.table)} /> {tb.table} ({tb.dataset})</label>
          ))}
        </fieldset>
      )}
      <WhenFields f={f} set={set} allowUpstream={f.kind === "pipeline"} />
      {problem && f.name && <p className="hint">{problem}</p>}
    </FormDialog>
  );
}

function RunList({ id }) {
  const [state] = useLoad(() => getScheduleRuns(id), [id]);
  if (!state.data) return <p className="muted">{state.status === "error" ? state.error : t("common.loading")}</p>;
  if (!state.data.length) return <p className="muted">{t("sources.sched.noRuns")}</p>;
  return (
    <table>
      <thead><tr><th>{t("sources.runs.started")}</th><th>{t("sources.runs.ended")}</th><th>{t("sources.sched.target")}</th><th>{t("sources.sched.trigger")}</th><th>{t("sources.runs.result")}</th><th></th></tr></thead>
      <tbody>
        {state.data.map((r) => (
          <tr key={r.id}>
            <td>{timeText(r.started_at)}</td>
            <td>{r.finished_at ? timeText(r.finished_at) : <span className="faint">—</span>}</td>
            <td>{r.item || r.target}</td>
            <td>{reasonText(r)}</td>
            <td><StatusChip state={r.status} label={runStatusText(r)} /></td>
            <td className="keep">{runSummary(r)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SchedulesPage() {
  useT();
  const [state, reload] = useLoad(getSchedules, []);
  const [options, setOptions] = useState({ sources: [], pipelines: [], ready: false });
  const [making, setMaking] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [open, setOpen] = useState(null);   // the schedule whose runs are shown
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([getSources(), getPipelines()]).then(([sources, pipelines]) => setOptions({ sources, pipelines, ready: true }), (e) => setError(e.message));
  }, []);
  const act = async (call) => {
    setError("");
    try {
      await call();
    } catch (e) {
      setError(e.message);
    }
    reload();
  };
  const schedules = state.data ?? [];
  const nothingToSchedule = options.ready && !options.sources.some((s) => s.tables.length) && !options.pipelines.length;
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("data.crumb.data") }, { label: t("sources.sched.title") }]} title={t("sources.sched.title")} sub={t("sources.sched.sub")}
        actions={!nothingToSchedule && <button className="primary" onClick={() => setMaking(true)}>{t("sources.sched.newTitle")}</button>} />
      {(error || state.status === "error") && <p className="error" role="alert">{error || state.error}</p>}
      {state.status === "loading" && !state.data && <p className="muted">{t("common.loading")}</p>}
      {state.data && !schedules.length && (nothingToSchedule
        ? <EmptyState icon="database" title={t("sources.sched.emptyData.title")} text={t("sources.sched.emptyData.text")} action={{ label: t("sources.sched.emptyData.action"), href: hrefFor({ page: "sources" }) }} />
        : <EmptyState icon="clock" title={t("sources.sched.empty.title")} text={t("sources.sched.empty.text")} action={{ label: t("sources.sched.newTitle"), onClick: () => setMaking(true) }} />)}
      {schedules.length > 0 && (
        <div className="table-wrap menus">
          <table className="sched">
            <thead><tr><th>{t("sources.col.name")}</th><th>{t("sources.sched.target")}</th><th>{t("sources.sched.when")}</th><th>{t("sources.sched.next")}</th><th>{t("sources.sched.latest")}</th><th>{t("sources.sched.lastChange")}</th><th>{t("sources.sched.writes")}</th><th>{t("sources.sched.owner")}</th><th></th></tr></thead>
            <tbody>
              {schedules.flatMap((s) => [
                <tr key={s.id} className={s.enabled ? "" : "note"}>
                  <td>{s.name}{!s.enabled && <span className="faint"> {t("sources.sched.off")}</span>}</td>
                  <td>
                    <a href={s.kind === "source" ? hrefFor({ page: "source", name: s.target }) : hrefFor({ page: "pipeline", name: s.target, view: "edit" })}>{s.target}</a>
                    {s.scope && <span className="faint small"> {s.scope.join(t("data.listSep"))}</span>}
                  </td>
                  <td>{s.when}</td>
                  <td>{s.next_at ? timeText(s.next_at) : <span className="faint">—</span>}</td>
                  <td>
                    {s.latest_run ? <><StatusChip state={s.latest_run.status} label={runStatusText(s.latest_run)} /> <span className="faint small">{timeText(s.latest_run.started_at)}</span></> : <span className="faint">{t("sources.sched.neverRun")}</span>}
                  </td>
                  <td>{s.last_change ? <>{timeText(s.last_change.at)}{t("data.sep")}{s.last_change.by}</> : <span className="faint">{t("sources.noneYet")}</span>}</td>
                  <td>{s.targets.length ? s.targets.map((tg) => <span key={tg} className="output-chip"><a href={hrefFor({ page: "dataset", name: tg, tab: "fields" })}>{tg}</a> </span>) : <span className="faint">—</span>}</td>
                  <td>{s.mine ? t("sources.sched.me") : s.created_by}</td>
                  <td className="keep row-actions">
                    <button className="plain" onClick={() => setOpen(open === s.id ? null : s.id)}>{open === s.id ? t("sources.sched.hideRuns") : t("sources.sched.showRuns")}</button>
                    {s.can_change && (
                      <MoreMenu items={[
                        { label: s.enabled ? t("sources.sched.disable") : t("sources.sched.enable"), onClick: () => act(() => updateSchedule({ id: s.id, enabled: !s.enabled })) },
                        { label: t("sources.sched.delete"), danger: true, confirmText: t("sources.sched.deleteConfirm", { name: s.name, target: s.target }),
                          onClick: () => act(async () => { await deleteSchedule(s.id); setDeleted(true); }) },
                      ]} />
                    )}
                  </td>
                </tr>,
                ...(open === s.id ? [<tr key={`${s.id}-runs`}><td colSpan={9}><RunList id={s.id} /></td></tr>] : []),
              ])}
            </tbody>
          </table>
        </div>
      )}
      {deleted && <p className="ok" role="status">{t("sources.sched.deleted")}</p>}
      {making && <ScheduleForm sources={options.sources} pipelines={options.pipelines} onClose={() => setMaking(false)} onDone={reload} />}
    </main>
  );
}
