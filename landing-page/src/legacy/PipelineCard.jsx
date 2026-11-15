import { useState } from "react";
import { HOW_CHOICES, fanOutLines, formProblem, joinRules, nodeLines, pipelineOf, setChoice, sourceLabel, startForm } from "./pipelineModel.js";
import { serviceError } from "./ontologyStudioModel.js";

/** Join two inputs (stored tables, or views) on a key and see the rows of every step; a join that makes more rows than its left input says why. */
export function PipelineCard({ runName, sources, rowCap }) {
  const [form, setForm] = useState(() => startForm(sources));
  const [shown, setShown] = useState(null);   // { form, sources, result } of the last run: the lines are written with the names it ran with
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = formProblem(form);
  const columns = (id) => sources.find((x) => x.id === id)?.columns || [];
  const choose = (part) => setForm(setChoice(form, sources, part));
  async function run() {
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/ontology/pipelines/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ saved_as: runName, pipeline: pipelineOf(form, sources) }) });
      const data = await response.json().catch(() => ({ error: `服务返回 ${response.status}` }));
      if (!response.ok) throw new Error(serviceError(response.status, data));
      setShown({ form, sources, result: data });
    } catch (e) {
      setError(e.message === "Failed to fetch" ? "连不上本机建模服务，确认它还在运行。" : e.message);
    } finally { setBusy(false); }
  }
  const join = shown?.result.nodes.find((n) => n.type === "join");
  const lines = shown ? nodeLines(shown.result, shown.form, shown.sources) : [];
  const warning = join ? fanOutLines(join, shown.form, shown.sources) : [];
  const select = (label, value, options, onChange) => <label className="os-pipe-field">{label}
    <select className="os-select" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">选一个</option>
      {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
    </select></label>;
  return <section className="pr-card os-pipeline">
    <div className="pr-card-head"><h2>连接两个输入</h2></div>
    <div className="os-pipe-form">
      {select("左边", form.left, sources.map((x) => [x.id, sourceLabel(sources, x.id)]), (left) => choose({ left }))}
      {select("左边的列", form.leftKey, columns(form.left).map((c) => [c, c]), (leftKey) => choose({ leftKey }))}
      {select("右边", form.right, sources.map((x) => [x.id, sourceLabel(sources, x.id)]), (right) => choose({ right }))}
      {select("右边的列", form.rightKey, columns(form.right).map((c) => [c, c]), (rightKey) => choose({ rightKey }))}
      <label className="os-pipe-field">怎么连
        <select className="os-select" value={form.how} onChange={(e) => choose({ how: e.target.value })}>
          {HOW_CHOICES.map(([how, label]) => <option key={how} value={how}>{label}</option>)}
        </select></label>
      <button type="button" className="pr-primary" disabled={busy || Boolean(problem)} title={problem || undefined} onClick={run}>{busy ? "运行中…" : "运行"}</button>
    </div>
    {rowCap && <p className="pr-muted">{joinRules(rowCap)}</p>}
    {error && <p role="alert" className="pr-error">{error}</p>}
    {shown && <>
      <ol className="os-pipe-steps">{lines.map((l) => <li key={l.id} className={l.flagged ? "os-pipe-flagged" : ""}>{l.text}</li>)}</ol>
      {warning.length > 0 && <div className="os-pipe-warning" role="note">{warning.map((l) => <p key={l}>{l}</p>)}</div>}
      <details className="os-how"><summary>管道和 SQL</summary>
        <pre className="os-pipe-code">{JSON.stringify(pipelineOf(shown.form, shown.sources), null, 1)}</pre>
        <pre className="os-pipe-code">{shown.result.nodes.filter((n) => n.sql).map((n) => `${n.sql};`).join("\n\n")}</pre>
      </details>
    </>}
  </section>;
}
