import React from "react";
import { getPipelineLog } from "./api.js";
import { timeText, typeLabel } from "./format.js";
import { doubledGroupLines, failureLines, friendlyError, joinVerdictLines, numberText, operatorTitle, stepTitle } from "./pipelineModel.js";
import { logText } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

export const PANEL_TABS = [["rows", "预览"], ["columns", "列"], ["stats", "统计"], ["log", "日志"]];
const BADGE = { new: "新增", replaced: "替换" };

function Rows({ data }) {
  if (!data.columns.length) return <p className="muted">这一步没有列</p>;
  return (
    <div className="table-wrap panel-table">
      <table>
        <thead><tr>{data.columns.map((c) => <th key={c.name} className={["integer", "decimal"].includes(c.type) ? "num" : ""}>{c.name}</th>)}</tr></thead>
        <tbody>
          {data.rows.map((r, i) => <tr key={i}>{r.map((v, k) => <td key={k} className={`cell${["integer", "decimal"].includes(data.columns[k].type) ? " num" : ""}`}>{v == null ? <span className="faint">空</span> : String(v)}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

function Columns({ data }) {
  return (
    <div className="table-wrap panel-table">
      <table>
        <thead><tr><th>列</th><th>类型</th><th>标记</th><th>来自</th><th>可以做的统计</th></tr></thead>
        <tbody>
          {data.columns.map((c) => (
            <tr key={c.name}>
              <td>{c.name}</td>
              <td>{typeLabel(c.type)}</td>
              <td>{c.badge ? <span className={`badge badge-${c.badge}`}>{BADGE[c.badge]}</span> : ""}</td>
              <td className="muted">{c.origin ?? (c.aggregation ? `${c.aggregation.fn}（${c.aggregation.column ?? "整行"}）` : "")}{c.code && <span> 代码列</span>}</td>
              <td className="muted small">{c.aggregations.length ? c.aggregations.join("、") : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stats({ data }) {
  return (
    <div className="table-wrap panel-table">
      <table>
        <thead><tr><th>列</th><th className="num">空</th><th className="num">不同的值</th><th>最小</th><th>最大</th><th className="num">平均</th><th>最常见</th></tr></thead>
        <tbody>
          {data.stats.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td className="num">{numberText(s.nulls)}</td>
              <td className="num">{numberText(s.distinct)}</td>
              <td className="cell">{s.min ?? "—"}</td>
              <td className="cell">{s.max ?? "—"}</td>
              <td className="num">{s.mean ?? ""}</td>
              <td className="cell muted">{(s.top ?? []).slice(0, 3).map((t) => `${t.value}（${t.rows}）`).join("、")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Log({ name, step, steps, node }) {
  const [log] = useLoad(() => getPipelineLog(name), [name]);
  const lines = [
    ...(node?.join ? joinVerdictLines(node.join) : []),
    ...(node?.operators ?? []).flatMap((op, i) => [`${i + 1}. ${op.text ?? ""}`, ...(op.failed ?? []).slice(0, 5).map((f) => `　第 ${f.row} 行没转成功：${f.value}`), ...doubledGroupLines(op)]),
    ...failureLines(node),
  ].filter(Boolean);
  return (
    <div className="panel-log">
      <p className="caption">{step ? `这一步（${stepTitle(step, steps)}）` : "这一步"}</p>
      {lines.length ? <ul className="plain-list">{lines.map((l, i) => <li key={i}>{l}</li>)}</ul> : <p className="muted">这一步没有要记的</p>}
      <p className="caption">这条管道的记录</p>
      {log.status === "error" && <p className="error">{log.error}</p>}
      {log.data && !log.data.length && <p className="muted">还没有记录</p>}
      <ul className="plain-list">
        {(log.data ?? []).map((e, i) => <li key={i}><span className="muted">{timeText(e.at)}</span> {logText(e).who}：{logText(e).text}</li>)}
      </ul>
    </div>
  );
}

/** The bottom panel: the selected step's rows, columns, statistics and log. `preview` is {status, data, error}; `upto` the operator the preview stops at. */
export function PipelinePanel({ tab, setTab, preview, upto, onClearUpto, name, step, steps, node }) {
  return (
    <div className="panel">
      <div className="panel-tabs" role="tablist" aria-label="这一步的内容">
        {PANEL_TABS.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>)}
        {step && <span className="panel-title muted">{stepTitle(step, steps)}{upto != null && step.operators?.[upto] && `，到第 ${upto + 1} 个操作（${operatorTitle(step.operators[upto]).slice(0, 18)}）`}{upto != null && <button className="plain" onClick={onClearUpto}>看这一步的最终结果</button>}</span>}
      </div>
      <div className="panel-body">
        {!step && <p className="muted">选一个步骤，这里显示它的前 100 行。</p>}
        {step && tab === "log" && <Log name={name} step={step} steps={steps} node={node} />}
        {step && tab !== "log" && preview.status === "loading" && !preview.data && <p className="muted">加载中</p>}
        {step && tab !== "log" && preview.status === "error" && <p className="error">{friendlyError(preview.error, steps)}</p>}
        {step && tab !== "log" && preview.data && (
          <>
            {tab === "rows" && <p className="muted small">前 {preview.data.rows.length} 行，这一步共 {numberText(preview.data.node.rows_out)} 行</p>}
            {tab === "stats" && <p className="muted small">按这一步的全部 {numberText(preview.data.node.rows_out)} 行算</p>}
            {tab === "rows" && <Rows data={preview.data} />}
            {tab === "columns" && <Columns data={preview.data} />}
            {tab === "stats" && <Stats data={preview.data} />}
          </>
        )}
      </div>
    </div>
  );
}
