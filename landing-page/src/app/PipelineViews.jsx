import React, { useState } from "react";
import { getPipelineRun, getPipelineRuns, getPipelineVersions } from "./api.js";
import { timeText } from "./format.js";
import { PipelineGraph } from "./PipelineGraph.jsx";
import { CHANGE_LABEL, KIND_LABEL, STATUS_LABEL, cardFlags, countsText, durationText, failureLines, numberText, stepSummary, stepTitle, versionsText } from "./pipelineModel.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

const runHref = (name, id) => hrefFor({ page: "pipeline", name, view: "run", run: id });

export function PipelineRuns({ detail }) {
  const [state, reload] = useLoad(() => getPipelineRuns(detail.name), [detail.name]);
  const runs = state.data ?? [];
  return (
    <div className="pl-page">
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !runs.length && <p className="muted">还没有运行过。到“编辑”页保存后点“运行”。</p>}
      {runs.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>运行</th><th>状态</th><th>谁运行的</th><th>开始</th><th className="num">用时</th><th className="num">定义版本</th></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td><a href={runHref(detail.name, r.id)}>第 {r.id} 次</a></td>
                  <td className={r.status === "failed" ? "bad" : ""}>{STATUS_LABEL[r.status] ?? r.status}</td>
                  <td>{r.who ?? "未署名"}</td>
                  <td>{timeText(r.started_at)}</td>
                  <td className="num">{durationText(r.duration_ms)}</td>
                  <td className="num">{r.definition_version}</td>
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
      <p><a href={hrefFor({ page: "pipeline", name: detail.name, view: "runs" })}>全部运行记录</a></p>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !run && <p className="muted">加载中</p>}
      {run && (
        <>
          <h2 className="section-title">第 {run.id} 次运行：<span className={run.status === "failed" ? "bad" : ""}>{STATUS_LABEL[run.status] ?? run.status}</span></h2>
          <dl className="defs">
            <dt>谁运行的</dt><dd>{run.who ?? "未署名"}</dd>
            <dt>开始</dt><dd>{timeText(run.started_at)}{run.finished_at && `，用时 ${durationText(run.duration_ms)}`}</dd>
            <dt>定义版本</dt><dd>第 {run.definition_version} 版</dd>
            <dt>读了</dt><dd>{versionsText(run.input_versions) || "—"}</dd>
          </dl>
          {run.error && <p className="error run-error">{run.error}</p>}
          {run.outputs.length > 0 && (
            <>
              <h3 className="section-title">写出了</h3>
              <ul className="plain-list">
                {run.outputs.map((o) => (
                  <li key={o.dataset}><a href={hrefFor({ page: "dataset", name: o.dataset, tab: "versions" })}>{o.dataset}</a> 第 {o.version} 版，{numberText(o.rows)} 行{o.created_version ? "" : "，内容没有变化，没有新版本"}</li>
                ))}
              </ul>
            </>
          )}
          {run.nodes.length > 0 && (
            <>
              <h3 className="section-title">每一步</h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>步骤</th><th>行数</th><th>做了什么</th><th>没做成的</th></tr></thead>
                  <tbody>
                    {run.nodes.map((n) => {
                      const flags = cardFlags(n).filter((f) => f.level !== "note");
                      return (
                        <tr key={n.id} className="wrap-row">
                          <td>{KIND_LABEL[n.type]} <span className="muted">{n.id}</span></td>
                          <td className="keep">{countsText(n)}</td>
                          <td>{(n.operators ?? []).map((op, i) => <p key={i} className="small">{i + 1}. {op.text}</p>)}{n.join && <p className="small">{n.join.matched_left} / {n.join.left_rows} 行左边对上了{n.join.extra_rows > 0 ? `，多出 ${n.join.extra_rows} 行` : ""}</p>}</td>
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
        <div><p className="caption">之前</p>{change.before ? line(change.before) : <p className="faint small">没有</p>}</div>
        <div><p className="caption">现在</p>{change.after ? line(change.after) : <p className="faint small">没有</p>}</div>
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
      {list.status === "loading" && !list.data && <p className="muted">加载中</p>}
      {versions.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>定义版本</th><th>谁保存的</th><th>时间</th><th className="num">步骤</th><th></th></tr></thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.version}>
                  <td>第 {v.version} 版{v.version === detail.definition_version && <span className="muted">（现在这一版）</span>}</td>
                  <td>{v.saved_by ?? "未署名"}</td>
                  <td>{timeText(v.saved_at)}</td>
                  <td className="num">{v.steps}</td>
                  <td><button className="plain" onClick={() => setViewing(viewing === v.version ? null : v.version)}>{viewing === v.version ? "收起" : "只读查看"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {viewing && past.data?.spec && (
        <div className="past">
          <h3 className="section-title">第 {viewing} 版（只读）</h3>
          <PipelineGraph steps={past.data.spec.steps} nodes={{}} selected={null} onSelect={() => {}} />
          <ul className="plain-list">{past.data.spec.steps.flatMap((s) => stepSummary(s, past.data.spec.steps).map((l, i) => <li key={`${s.id}${i}`}><span className="muted">{KIND_LABEL[s.type]}</span> {l}</li>))}</ul>
        </div>
      )}
      {versions.length > 1 && (
        <>
          <h3 className="section-title">对比两个版本</h3>
          <div className="inline wide">
            <Select label="从哪一版" value={String(a)} onChange={(v) => setFrom(Number(v))}>{versions.map((v) => <option key={v.version} value={v.version}>第 {v.version} 版</option>)}</Select>
            <span>改成</span>
            <Select label="到哪一版" value={String(b)} onChange={(v) => setTo(Number(v))}>{versions.map((v) => <option key={v.version} value={v.version}>第 {v.version} 版</option>)}</Select>
          </div>
          {compared.status === "error" && <p className="error">{compared.error}</p>}
          {compared.data && !compared.data.changes.length && <p className="muted">这两版的步骤一样</p>}
          {compared.data?.changes.map((c) => <ChangeRow key={`${c.id}${c.change}`} change={c} steps={compared.data.spec.steps} titleOf={changeTitle} />)}
        </>
      )}
    </div>
  );
}

export { ChangeRow };
