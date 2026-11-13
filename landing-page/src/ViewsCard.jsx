import { useState } from "react";
import { NewerLink } from "./CodeMeaningForm.jsx";
import { KIND_CHOICES, OP_CHOICES, blankView, codedColumns, setViewChoice, viewBody, viewLine, viewProblem } from "./viewsModel.js";

const FIELD_KEY = "views";

/** What the confirmed definitions of this run became in the workspace: one view each, with its rows, who confirmed it and the SQL;
 *  and a form to name a new one (a row filter from a confirmed meaning, or the latest row per key). */
export function ViewsCard({ views, tables, meanings, error, client }) {
  const [form, setForm] = useState(() => blankView(tables));
  const choose = (part) => setForm((was) => setViewChoice(was, part));
  const problem = viewProblem(form);
  const table = tables.find((t) => t.name === form.base);
  const coded = codedColumns(meanings, form.base);
  const labels = coded.find((c) => c.column === form.column)?.labels || [];
  const columns = (table?.columns || []).filter((c) => form.kind === "filter" || c.name !== form.key);
  const select = (label, value, options, onChange, placeholder = "选一个") => <label className="os-pipe-field">{label}
    <select className="os-select" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
    </select></label>;
  async function save() {
    if (await client.onSaveView(viewBody(form))) setForm(blankView(tables));
  }
  const lines = views.map(viewLine);
  return <section className="pr-card os-views">
    <div className="pr-card-head"><h2>视图</h2></div>
    {error && <p role="alert" className="pr-error">{error}</p>}
    {!lines.length && <p className="pr-muted">确认了代码的含义或重复编号的处理办法后，这里会出现对应的视图。</p>}
    <ul className="os-view-list">{lines.map((v) => <li key={v.name} className={v.usable ? "" : "os-view-off"}>
      <div className="os-view-head"><b>{v.name}</b><span>{v.rows}</span><span>{v.state}</span>
        {v.named && <button type="button" className="pr-link" disabled={client.busy || !client.can || Boolean(client.newer)} title={client.newer ? "有更新的版本，请在那一次运行里收回" : client.can ? undefined : client.why} onClick={() => client.onSaveView({ name: v.name, remove: true })}>收回</button>}</div>
      <p className="pr-muted">{v.from}</p>
      <details className="os-how"><summary>SQL</summary><pre className="os-pipe-code">{v.sql}</pre></details>
    </li>)}</ul>
    {tables.length > 0 && <details className="os-how os-view-new"><summary>新建视图</summary>
      <div className="os-pipe-form">
        <label className="os-pipe-field">名称<input value={form.name} maxLength={30} onChange={(e) => choose({ name: e.target.value })} /></label>
        {select("做什么", form.kind, KIND_CHOICES, (kind) => choose({ kind }), "选一种")}
        {select("表", form.base, tables.map((t) => [t.name, t.name]), (base) => choose({ base }))}
        {form.kind === "filter" ? <>
          {select("代码列", form.column, coded.map((c) => [c.column, c.column]), (column) => choose({ column }), coded.length ? "选一个" : "没有已确认含义的列")}
          {select("条件", form.op, OP_CHOICES, (op) => choose({ op }))}
          {select("含义", form.label, labels.map((l) => [l, l]), (label) => choose({ label }))}
        </> : <>
          {select("编号列", form.key, (table?.columns || []).map((c) => [c.name, c.name]), (key) => choose({ key }))}
          {select("按哪一列比先后", form.order, columns.filter((c) => c.orderable).map((c) => [c.name, c.name]), (order) => choose({ order }))}
        </>}
        {client.newer ? <NewerLink client={client} /> : <>
          <label className="os-pipe-field">确认人<input value={client.by} maxLength={40} onChange={(e) => client.setBy(e.target.value)} /></label>
          <button type="button" className="pr-primary" disabled={client.busy || !client.can || Boolean(problem)} title={problem || client.why || undefined} onClick={save}>{client.busy ? "保存中…" : "确认视图"}</button></>}
      </div>
      {client.error?.key === FIELD_KEY && <p role="alert" className="pr-error">{client.error.text}</p>}
    </details>}
  </section>;
}
