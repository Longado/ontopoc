import { useState } from "react";

import {
  CARD_PIPELINE_NOTE, CARD_VOCAB, blankLine, cardEmptyText, changedCells, itemChoices, itemForm, itemProblem, linkedHint, noiseLine, saveProblem, stampLine, uniqueLine,
} from "./cardModel.js";

const count = (n) => n.toLocaleString("zh-CN");

/** The form that records what the client answered to a thing to settle. `answer` is the old answer when changing one. */
export function AnswerForm({ item, answer = null, client, onDone }) {
  const [form, setForm] = useState(() => itemForm(answer));
  const choices = itemChoices(item);
  const problem = itemProblem(item, form, client.by);
  const hint = linkedHint(item, form, answer);
  const set = (part) => setForm({ ...form, ...part });
  return <div className="os-add os-answer-form">
    {choices.length > 0 && <fieldset className="os-answer-choices"><legend>客户怎么答的</legend>
      {choices.map(([value, label]) => <label key={value} className="os-answer-choice">
        <input type="radio" name={`choice-${item.id}`} checked={form.choice === value} onChange={() => set({ choice: value })} />{label}</label>)}
    </fieldset>}
    <label>{choices.length ? "补充说明（选填）" : "客户怎么答的"}
      <textarea rows={2} value={form.text} maxLength={300} onChange={(e) => set({ text: e.target.value })} /></label>
    <label>出处（选填，例如“10-27 会议”）<input value={form.basis} maxLength={200} onChange={(e) => set({ basis: e.target.value })} /></label>
    <label>答复人<input value={client.by} maxLength={40} onChange={(e) => client.setBy(e.target.value)} /></label>
    {hint && <p className="pr-muted">{hint}</p>}
    <div className="os-go">
      <button type="button" className="pr-primary" disabled={client.busy || Boolean(problem)} title={problem || undefined}
        onClick={async () => { if (await client.onSave(item, form)) onDone(); }}>{client.busy ? "保存中…" : "记下"}</button>
      <button type="button" className="pr-link" onClick={onDone}>取消</button>
    </div>
    {client.error?.key === item.id && <p role="alert" className="pr-error">{client.error.text}</p>}
  </div>;
}

/** A cell answered by choosing one of the contract's words; the saved answer shows under it as who, which day, basis. */
function Choose({ kind, cell, label, draft, changed, onSet }) {
  const value = cell.id in draft ? draft[cell.id] ?? "" : cell.answer?.value ?? "";
  return <div className="os-card-cell">
    <select aria-label={label} value={value} className={changed.has(cell.id) ? "is-changed" : undefined} onChange={(e) => onSet(cell.id, e.target.value || null)}>
      <option value="">还没说</option>
      {CARD_VOCAB[kind].map(([v, says]) => <option key={v} value={v}>{says}</option>)}
    </select>
    {cell.answer && !changed.has(cell.id) && <small className="os-card-stamp">{stampLine(cell.answer)}</small>}
  </div>;
}

/** The period a date column is declared to cover: both ends optional. */
function Declared({ date, draft, changed, onSet }) {
  const id = date.range_id;
  const now = id in draft ? draft[id] : date.declared?.value;
  const set = (part, text) => onSet(id, { from: now?.from || "", to: now?.to || "", [part]: text });
  const mark = changed.has(id) ? "is-changed" : undefined;
  return <div className="os-card-cell">
    <span className="os-card-range">
      <input type="date" aria-label={`${date.field} 声明覆盖从`} className={mark} value={now?.from || ""} onChange={(e) => set("from", e.target.value)} />
      <i aria-hidden="true">至</i>
      <input type="date" aria-label={`${date.field} 声明覆盖到`} className={mark} value={now?.to || ""} onChange={(e) => set("to", e.target.value)} />
    </span>
    {date.declared && !changed.has(id) && <small className="os-card-stamp">{date.declared.says} · {stampLine(date.declared)}</small>}
  </div>;
}

function TableCard({ table, draft, changed, onSet }) {
  const pick = { draft, changed, onSet };
  return <section className="pr-card os-card-table">
    <div className="pr-card-head"><h2>{table.source}</h2><span className="os-stats"><b>{count(table.rows)}</b> 行</span></div>
    <h3>一行是什么</h3>
    <p className="os-card-fact">{uniqueLine(table.grain.unique, table.rows)}</p>
    {table.objects.length > 0 && <p className="os-card-fact">这张表里的对象：{table.objects.map((o) => `${o.label}（${o.identity.join(" + ")}）`).join("、")}</p>}
    <Choose kind="grain" cell={table.grain} label={`${table.source} 一行是什么`} {...pick} />
    {table.dates.length > 0 && <>
      <h3>日期列是什么时间</h3>
      <div className="os-table-scroll"><table className="os-fields">
        <thead><tr><th scope="col">日期列</th><th scope="col">最早</th><th scope="col">最晚</th><th scope="col">空值</th><th scope="col">是什么时间</th><th scope="col">声明覆盖时段（选填）</th></tr></thead>
        <tbody>{table.dates.map((d) => <tr key={d.id}>
          <td>{d.field}</td><td>{d.min || "—"}</td><td>{d.max || "—"}</td><td>{count(d.empty)}</td>
          <td><Choose kind="date" cell={d} label={`${d.field} 是什么时间`} {...pick} /></td>
          <td><Declared date={d} {...pick} /></td>
        </tr>)}</tbody>
      </table></div>
    </>}
    {table.amounts.length > 0 && <>
      <h3>数值列能不能相加</h3>
      <div className="os-table-scroll"><table className="os-fields">
        <thead><tr><th scope="col">数值列</th><th scope="col">空值</th><th scope="col">能不能加</th></tr></thead>
        <tbody>{table.amounts.map((a) => <tr key={a.id}>
          <td>{a.field}{a.noise && <small className="os-card-noise">{noiseLine(a.noise)}</small>}</td><td>{count(a.empty)}</td>
          <td><Choose kind="amount" cell={a} label={`${a.field} 能不能加`} {...pick} /></td>
        </tr>)}</tbody>
      </table></div>
    </>}
  </section>;
}

/** 口径卡: what code worked out for each table, and the cells only the client can answer. One save sends only what changed.
 *  `edit` holds what was set and not saved yet (cell id -> value, and the basis) above this page, so leaving it loses nothing. */
export function CardSection({ run, state, client, blocked, edit }) {
  const { cells: draft, basis } = edit;   // draft: cell id -> the value set on this page and not saved yet
  const card = state?.card;
  const cells = card ? changedCells(card, draft, basis) : [];
  const changed = new Set(cells.map((c) => c.id));
  const problem = saveProblem(client.by, cells, []) || blocked;
  const onSet = edit.setCell;
  const save = async () => { if (await client.onSaveCells(cells)) edit.clear(); };
  return <>
    <section className="pr-card os-card">
      <div className="pr-card-head"><h2>口径卡</h2>{card?.cells > 0 && <span className="pr-muted">{blankLine(card)}</span>}</div>
      <p className="pr-muted">每张表一张。代码能算的已经算好；只有客户答得了的，会上问了，记在这里。问答会照这里的答复算，保存不需要模型 key。{CARD_PIPELINE_NOTE}。</p>
      {!run.saved_as && <p className="pr-muted">示例结果没有口径卡，上传自己的文件后由本机服务算。</p>}
      {run.saved_as && !state && <p className="pr-muted">正在读取…</p>}
      {state?.error && <p role="alert" className="pr-error">{state.error}</p>}
      {card && !card.tables.length && !card.objects.length && <p className="pr-muted">{cardEmptyText(run)}</p>}
      {card?.cells > 0 && <div className="os-card-who">
        <label>答复人<input value={client.by} maxLength={40} autoComplete="off" onChange={(e) => client.setBy(e.target.value)} /></label>
        <label>出处（选填，这次保存的改动共用）<input value={basis} maxLength={200} autoComplete="off" onChange={(e) => edit.setBasis(e.target.value)} /></label>
        <button type="button" className="pr-primary" disabled={client.busy || Boolean(problem)} title={problem || undefined} onClick={save}>{client.busy ? "保存中…" : "保存口径卡"}</button>
        {cells.length > 0 && <span className="pr-muted">改了 {cells.length} 格，还没保存</span>}
      </div>}
      {client.error?.key === "card" && <p role="alert" className="pr-error">{client.error.text}</p>}
    </section>
    {card?.tables.map((t) => <TableCard key={t.source} table={t} draft={draft} changed={changed} onSet={onSet} />)}
    {card?.objects.length > 0 && <section className="pr-card os-card-objects">
      <div className="pr-card-head"><h2>对象全不全</h2></div>
      <p className="pr-muted">数据里的这些对象，是客户那边的全部，还是只导了一部分？</p>
      <div className="os-table-scroll"><table className="os-fields">
        <thead><tr><th scope="col">对象</th><th scope="col">数据里有</th><th scope="col">全不全</th></tr></thead>
        <tbody>{card.objects.map((o) => <tr key={o.id}>
          <td>{o.label}</td><td>{count(o.count)} 个</td>
          <td><Choose kind="complete" cell={o} label={`${o.label} 全不全`} draft={draft} changed={changed} onSet={onSet} /></td>
        </tr>)}</tbody>
      </table></div>
    </section>}
  </>;
}
