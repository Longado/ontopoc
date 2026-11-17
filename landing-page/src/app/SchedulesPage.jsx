import React, { useEffect, useState } from "react";
import { createSchedule, deleteSchedule, getPipelines, getScheduleRuns, getSchedules, getSources, updateSchedule } from "./api.js";
import { timeText } from "./format.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { CADENCES, WEEKDAYS, reasonText, runStatusText, runSummary, runnablePipeline, scheduleBody, scheduleProblem } from "./sourceModel.js";
import { browserZone, hourOptions, minuteOptions, timeFromParts, timeParts } from "./scheduleTime.js";
import { useLoad } from "./useLoad.js";
import { FormDialog } from "./FormDialog.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { MoreMenu } from "./ui/MoreMenu.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";

const zones = () => {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return [];
  }
};

/** A fresh schedule form's values: a daily 08:00 run in the browser's own time zone. */
export const newScheduleForm = (extra = {}) => ({ name: "", kind: "source", target: "", cadence: "daily", minute: "0", time: "08:00", weekday: "0", tz: browserZone(), scope: [], ...extra });

/** A 24-hour time of day: two selects, so a computer set to 12 hours does not show 上午/下午. */
export function TimeOfDay({ value, onChange }) {
  const { h, m } = timeParts(value);
  const minutes = minuteOptions.includes(m) ? minuteOptions : [...minuteOptions, m].sort();
  return (
    <span className="time-of-day">
      <Select label="几点（24 小时制）" value={h} onChange={(v) => onChange(timeFromParts(v, m))}>{hourOptions.map((x) => <option key={x} value={x}>{x} 时</option>)}</Select>
      <Select label="几分" value={m} onChange={(v) => onChange(timeFromParts(h, v))}>{minutes.map((x) => <option key={x} value={x}>{x} 分</option>)}</Select>
    </span>
  );
}

/** The "when" part of a schedule form, shared by the schedule dialog and the connection guide's last step. `f` is the form, `set(key)(value)` changes one value. */
export function WhenFields({ f, set, allowUpstream }) {
  const cadences = CADENCES.filter((c) => c.key !== "upstream" || allowUpstream);
  return (
    <>
      <div className="field">
        <span className="caption">什么时候</span>
        <Select label="触发方式" value={f.cadence} onChange={set("cadence")}>
          {cadences.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </Select>
      </div>
      {f.cadence === "hourly" && <label className="field"><span className="caption">每小时的第几分（0 到 59）</span><input type="text" inputMode="numeric" value={f.minute} onChange={(e) => set("minute")(e.target.value)} /></label>}
      {f.cadence === "weekly" && (
        <div className="field">
          <span className="caption">星期几</span>
          <Select label="星期几" value={f.weekday} onChange={set("weekday")}>{WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</Select>
        </div>
      )}
      {(f.cadence === "daily" || f.cadence === "weekly") && <div className="field"><span className="caption">时间（24 小时制）</span><TimeOfDay value={f.time} onChange={set("time")} /></div>}
      {f.cadence !== "upstream" && (
        <label className="field">
          <span className="caption">时区（默认是这台电脑的时区）</span>
          <input type="text" list="zone-list" value={f.tz} onChange={(e) => set("tz")(e.target.value)} />
          <datalist id="zone-list">{zones().map((z) => <option key={z} value={z} />)}</datalist>
        </label>
      )}
      {f.cadence === "upstream" && <p className="hint">它读的数据集有新版本时运行一次；运行不会重叠。</p>}
    </>
  );
}

function ScheduleForm({ sources, pipelines, onClose, onDone }) {
  const [f, setF] = useState(() => newScheduleForm());
  const set = (k) => (v) => setF({ ...f, [k]: v });
  const source = sources.find((s) => s.name === f.target);
  const targets = f.kind === "source" ? sources.filter((s) => s.tables.length) : pipelines.filter(runnablePipeline);
  const problem = scheduleProblem(f, sources, pipelines);
  const toggle = (table) => set("scope")(f.scope.includes(table) ? f.scope.filter((t) => t !== table) : [...f.scope, table]);
  return (
    <FormDialog title="新建调度" submitLabel="创建" onClose={onClose} valid={!problem} onSubmit={async () => { await createSchedule(scheduleBody(f)); onDone(); }}>
      <label className="field"><span className="caption">名字</span><input type="text" value={f.name} maxLength={60} onChange={(e) => set("name")(e.target.value)} /></label>
      <div className="field">
        <span className="caption">刷新什么</span>
        <Select label="刷新什么" value={f.kind} onChange={(kind) => setF({ ...f, kind, target: "", scope: [], cadence: kind === "source" && f.cadence === "upstream" ? "daily" : f.cadence })}>
          <option value="source">数据源里读成数据集的表</option>
          <option value="pipeline">管道（重新运行）</option>
        </Select>
      </div>
      <div className="field">
        <span className="caption">{f.kind === "source" ? "数据源" : "管道（只有确认过定义的才能定时跑）"}</span>
        <Select label="对象" value={f.target} onChange={(target) => setF({ ...f, target, scope: [] })}>
          <option value="">请选择</option>
          {targets.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
        </Select>
      </div>
      {source && source.tables.length > 1 && (
        <fieldset className="field">
          <legend className="caption">刷新哪些表（都不选就是全部）</legend>
          {source.tables.map((t) => (
            <label key={t.table}><input type="checkbox" checked={f.scope.includes(t.table)} onChange={() => toggle(t.table)} /> {t.table}（{t.dataset}）</label>
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
  if (!state.data) return <p className="muted">{state.status === "error" ? state.error : "加载中"}</p>;
  if (!state.data.length) return <p className="muted">还没有跑过。</p>;
  return (
    <table>
      <thead><tr><th>开始</th><th>结束</th><th>对象</th><th>触发</th><th>结果</th><th></th></tr></thead>
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
      <PageHeader crumbs={[{ label: "数据" }, { label: "调度" }]} title="调度" sub="让数据源或管道按时间自动刷新。时间按 24 小时制，时区默认是这台电脑的。"
        actions={!nothingToSchedule && <button className="primary" onClick={() => setMaking(true)}>新建调度</button>} />
      {(error || state.status === "error") && <p className="error" role="alert">{error || state.error}</p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !schedules.length && (nothingToSchedule
        ? <EmptyState icon="database" title="先有数据，才能设定时刷新" text="调度刷新的是数据源里读成数据集的表，或一条已确认的管道。先接入一个数据源。" action={{ label: "去接入数据", href: hrefFor({ page: "sources" }) }} />
        : <EmptyState icon="clock" title="还没有调度" text="给数据源或管道设一个，让它按时刷新，不用再手动点。" action={{ label: "新建调度", onClick: () => setMaking(true) }} />)}
      {schedules.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>名称</th><th>对象</th><th>什么时候</th><th>下一次</th><th>最近一次</th><th>上次改了数据</th><th>写入</th><th>建的人</th><th></th></tr></thead>
            <tbody>
              {schedules.flatMap((s) => [
                <tr key={s.id} className={s.enabled ? "" : "note"}>
                  <td>{s.name}{!s.enabled && <span className="faint"> 已关</span>}</td>
                  <td>
                    <a href={s.kind === "source" ? hrefFor({ page: "source", name: s.target }) : hrefFor({ page: "pipeline", name: s.target, view: "edit" })}>{s.target}</a>
                    {s.scope && <span className="faint small"> {s.scope.join("、")}</span>}
                  </td>
                  <td>{s.when}</td>
                  <td>{s.next_at ? timeText(s.next_at) : <span className="faint">—</span>}</td>
                  <td>
                    {s.latest_run ? <><StatusChip state={s.latest_run.status} label={runStatusText(s.latest_run)} /> <span className="faint small">{timeText(s.latest_run.started_at)}</span></> : <span className="faint">还没跑过</span>}
                  </td>
                  <td>{s.last_change ? <>{timeText(s.last_change.at)}，{s.last_change.by}</> : <span className="faint">还没有</span>}</td>
                  <td>{s.targets.length ? s.targets.map((t) => <span key={t} className="output-chip"><a href={hrefFor({ page: "dataset", name: t, tab: "fields" })}>{t}</a> </span>) : <span className="faint">—</span>}</td>
                  <td>{s.mine ? "我" : s.created_by}</td>
                  <td className="keep row-actions">
                    <button className="plain" onClick={() => setOpen(open === s.id ? null : s.id)}>{open === s.id ? "收起记录" : "运行记录"}</button>
                    {s.can_change && <button className="plain" onClick={() => act(() => updateSchedule({ id: s.id, enabled: !s.enabled }))}>{s.enabled ? "关闭" : "开启"}</button>}
                    {s.can_change && (
                      <MoreMenu items={[{ label: "删除调度", danger: true, confirmText: `删除“${s.name}”？它不会再按时刷新 ${s.target}；数据集和已经读进来的数据不受影响。`,
                        onClick: () => act(async () => { await deleteSchedule(s.id); setDeleted(true); }) }]} />
                    )}
                  </td>
                </tr>,
                ...(open === s.id ? [<tr key={`${s.id}-runs`}><td colSpan={9}><RunList id={s.id} /></td></tr>] : []),
              ])}
            </tbody>
          </table>
        </div>
      )}
      {deleted && <p className="ok" role="status">已删除</p>}
      {making && <ScheduleForm sources={options.sources} pipelines={options.pipelines} onClose={() => setMaking(false)} onDone={reload} />}
    </main>
  );
}
