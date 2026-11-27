import React from "react";
import { getPipelineLog } from "./api.js";
import { formatDateTime, t } from "./i18n/index.js";
import { KindChip, PIcon, TypeMark } from "./PipelineIcons.jsx";
import { columnFrom, doubledGroupLines, failureLines, friendlyError, joinVerdictLines, kindLine, numberText, operatorTitle, splitLines, stepTitle, unionLines } from "./pipelineModel.js";
import { logText } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

export const PANEL_TABS = ["rows", "columns", "stats", "log"];
const NUMERIC = ["integer", "decimal"];
const BADGE = { new: "new", replaced: "replaced" };
const typeWord = (type) => (["text", "integer", "decimal", "date", "month", "datetime", "boolean"].includes(type) ? t(`pipeline.panel.type.${type}`) : type);

function Rows({ data }) {
  if (!data.columns.length) return <p className="muted pl-pad">{t("pipeline.panel.noColumns")}</p>;
  const stats = Object.fromEntries((data.stats ?? []).map((s) => [s.name, s]));
  return (
    <div className="pl-grid-table">
      <table>
        <thead>
          <tr>
            <th className="gutter" aria-label={t("pipeline.panel.rowNumber")} />
            {data.columns.map((c) => (
              <th key={c.name} className={NUMERIC.includes(c.type) ? "num" : ""} title={c.name}>
                <span className="col-name"><TypeMark type={c.type} /><span className="col-text">{c.name}</span></span>
                <span className="col-meta">{typeWord(c.type)}{stats[c.name] && ` · ${t("pipeline.panel.distinct", { count: stats[c.name].distinct, n: numberText(stats[c.name].distinct) })}${stats[c.name].nulls ? ` · ${t("pipeline.panel.nulls", { n: numberText(stats[c.name].nulls) })}` : ""}`}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r, i) => (
            <tr key={i}>
              <td className="gutter">{i + 1}</td>
              {r.map((v, k) => <td key={k} className={`cell${NUMERIC.includes(data.columns[k].type) ? " num" : ""}`} title={v == null ? undefined : String(v)}>{v == null ? <span className="is-null">{t("pipeline.panel.null")}</span> : String(v)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Columns({ data }) {
  return (
    <div className="pl-grid-table">
      <table>
        <thead><tr><th>{t("pipeline.panel.col.name")}</th><th>{t("pipeline.panel.col.type")}</th><th>{t("pipeline.panel.col.mark")}</th><th>{t("pipeline.panel.col.from")}</th><th>{t("pipeline.panel.col.aggs")}</th></tr></thead>
        <tbody>
          {data.columns.map((c) => (
            <tr key={c.name}>
              <td><span className="col-name"><TypeMark type={c.type} /><span className="col-text">{c.name}</span></span></td>
              <td>{typeWord(c.type)}</td>
              <td>{c.badge ? <span className={`pl-badge ${c.badge === "new" ? "info" : "neutral"}`}>{t(`pipeline.panel.badge.${BADGE[c.badge] ?? "new"}`)}</span> : ""}</td>
              <td className="muted">{columnFrom(c)}{c.code && <span> {t("pipeline.panel.codeColumn")}</span>}</td>
              <td className="muted">{c.aggregations.length ? c.aggregations.join(", ") : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stats({ data }) {
  return (
    <div className="pl-grid-table">
      <table>
        <thead><tr><th>{t("pipeline.panel.stat.column")}</th><th className="num">{t("pipeline.panel.stat.empty")}</th><th className="num">{t("pipeline.panel.stat.distinct")}</th><th>{t("pipeline.panel.stat.min")}</th><th>{t("pipeline.panel.stat.max")}</th><th className="num">{t("pipeline.panel.stat.mean")}</th><th>{t("pipeline.panel.stat.top")}</th></tr></thead>
        <tbody>
          {data.stats.map((s) => (
            <tr key={s.name}>
              <td><span className="col-name"><TypeMark type={data.columns.find((c) => c.name === s.name)?.type} /><span className="col-text">{s.name}</span></span></td>
              <td className="num">{numberText(s.nulls)}</td>
              <td className="num">{numberText(s.distinct)}</td>
              <td className="cell">{s.min ?? "—"}</td>
              <td className="cell">{s.max ?? "—"}</td>
              <td className="num">{s.mean ?? ""}</td>
              <td className="cell muted">{(s.top ?? []).slice(0, 3).map((x) => `${x.value} (${x.rows})`).join(", ")}</td>
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
    ...unionLines(node?.union),
    ...splitLines(node?.split),
    ...(node?.operators ?? []).flatMap((op, i) => [`${i + 1}. ${op.text ?? ""}`, ...(op.failed ?? []).slice(0, 5).map((f) => `   ${t("pipeline.panel.log.failedRow", { row: f.row, value: f.value })}`),
      ...(op.without_examples ?? []).slice(0, 5).map((f) => `   ${t("pipeline.panel.log.withoutRow", { row: f.row, value: f.value ?? "" })}`), ...doubledGroupLines(op)]),
    ...failureLines(node),
  ].filter(Boolean);
  return (
    <div className="panel-log">
      <h3 className="pl-cap">{step ? t("pipeline.panel.log.thisStepNamed", { title: stepTitle(step, steps) }) : t("pipeline.panel.log.thisStep")}</h3>
      {lines.length ? <ul className="pl-lines">{lines.map((l, i) => <li key={i}>{l}</li>)}</ul> : <p className="muted">{t("pipeline.panel.log.none")}</p>}
      <h3 className="pl-cap">{t("pipeline.panel.log.pipeline")}</h3>
      {log.status === "error" && <p className="error">{log.error}</p>}
      {log.data && !log.data.length && <p className="muted">{t("pipeline.panel.log.empty")}</p>}
      <ul className="pl-log">
        {(log.data ?? []).map((e, i) => <li key={i}><time className="muted">{formatDateTime(e.at)}</time><span>{logText(e).who}: {logText(e).text}</span></li>)}
      </ul>
    </div>
  );
}

/** The bottom drawer: the selected step's rows, columns, statistics and log. `preview` is {status, data, error}; `upto` the operator the preview stops at; `todo` what the step still
 * needs (an error from a step that is not set up yet is shown neutral, as "Unconfigured"); `size` normal / tall / max, changed by `setSize`; `onClose` hides the drawer's content
 * by deselecting the step. */
export function PipelinePanel({ tab, setTab, preview, upto, onClearUpto, name, step, steps, node, todo = [], size = "normal", setSize }) {
  const rows = preview.data?.rows.length ?? 0;
  const total = preview.data?.node.rows_out;
  return (
    <div className="panel">
      <div className="panel-tabs" role="tablist" aria-label={t("pipeline.panel.aria")}>
        {PANEL_TABS.map((k) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t(`pipeline.panel.tab.${k}`)}</button>)}
        <span className="panel-spacer" />
        {step && (
          <span className="panel-title">
            <KindChip step={step} size={18} />
            <span className="panel-name">{stepTitle(step, steps)}</span>
            {upto != null && step.operators?.[upto] && <span className="pl-badge info">{t("pipeline.panel.upto", { n: upto + 1, title: operatorTitle(step.operators[upto]).slice(0, 18) })}</span>}
            {upto != null && <button type="button" className="plain" onClick={onClearUpto}>{t("pipeline.panel.finalResult")}</button>}
          </span>
        )}
        {setSize && (
          <span className="panel-size" role="group" aria-label={t("pipeline.panel.sizeAria")}>
            {size !== "normal" && <button type="button" className="icon-btn" onClick={() => setSize("normal")} title={t("pipeline.panel.restore")} aria-label={t("pipeline.panel.restore")}><PIcon name="restore" /></button>}
            {size === "normal" && <button type="button" className="icon-btn" onClick={() => setSize("tall")} title={t("pipeline.panel.taller")} aria-label={t("pipeline.panel.taller")}><PIcon name="tall" /></button>}
            {size !== "max" && <button type="button" className="icon-btn" onClick={() => setSize("max")} title={t("pipeline.panel.maximize")} aria-label={t("pipeline.panel.maximize")}><PIcon name="maximize" /></button>}
          </span>
        )}
      </div>
      {step && tab !== "log" && preview.data && !todo.length && (
        <div className="panel-note">
          {tab === "rows" && <span>{t("pipeline.panel.showing", { count: rows, n: numberText(rows), total: numberText(total) })}</span>}
          {tab === "columns" && <span>{t("pipeline.panel.columnsOf", { count: preview.data.columns.length })}</span>}
          {tab === "stats" && <span>{t("pipeline.panel.statsOf", { total: numberText(total) })}</span>}
          <span className="panel-note-kind">{kindLine(step)}</span>
        </div>
      )}
      <div className="panel-body">
        {!step && <p className="pl-pad muted">{t("pipeline.panel.pick")}</p>}
        {step && tab === "log" && <Log name={name} step={step} steps={steps} node={node} />}
        {step && tab !== "log" && preview.status === "loading" && !preview.data && <div className="pl-skeleton" aria-label={t("pipeline.loading")}><i /><i /><i /><i /></div>}
        {step && tab !== "log" && todo.length > 0 && <p className="pl-note neutral"><PIcon name="info" size={14} /><span><strong>{t("pipeline.graph.unconfigured")}.</strong> {todo.join("; ")}</span></p>}
        {step && tab !== "log" && !todo.length && preview.status === "error" && (
          <div className="pl-errcard" role="alert"><PIcon name="alert" size={16} /><div><strong>{t("pipeline.panel.errorTitle")}</strong><p>{friendlyError(preview.error, steps)}</p></div></div>
        )}
        {step && tab !== "log" && !todo.length && preview.data && (
          <>
            {tab === "rows" && <Rows data={preview.data} />}
            {tab === "columns" && <Columns data={preview.data} />}
            {tab === "stats" && <Stats data={preview.data} />}
          </>
        )}
      </div>
    </div>
  );
}
