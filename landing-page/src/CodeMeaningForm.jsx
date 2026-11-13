import { createContext, useState } from "react";
import { codeBody, codeGuess, codeProblem, codeStart, codeWhyWeak } from "./openItemsModel.js";

/** What each code column's values mean ({ "订单.状态码": { labels } }), for the answers and field lists that show codes. */
export const CodeMeanings = createContext(null);

/** A code column's open item: each value with its count and what the data says about it, the model's guess where there is
 *  one (marked when the data does not back it, and then not put in the box), and a place to write what it means. */
/** What stands where a definition would be saved when a newer run of the same file is waiting: definitions are changed there. */
export function NewerLink({ client }) {
  return <div className="os-code-save"><button type="button" className="os-graph-link" onClick={() => client.onOpenRun(client.newer)}>有更新的版本在等你看 →</button></div>;
}

export function CodeMeaningForm({ item, client }) {
  const [form, setForm] = useState(() => codeStart(item));
  const problem = codeProblem(item, form);
  const set = (value, part) => setForm({ ...form, [value]: { ...form[value], ...part } });
  const guessed = item.column.values.some((v) => v.recommendation);
  return <div className="os-codes">
    <ul className="os-code-list">{item.column.values.map((v) => {
      const guess = codeGuess(v);
      return <li key={v.value} className="os-code">
        <div className="os-code-head"><b className="os-code-value">{v.value}</b><span>{v.facts[0]}</span>
          {v.confirmed && <em className="os-chip-note" title="已确认过，可以改">已确认</em>}</div>
        {v.facts.length > 1 && <ul className="os-open-facts">{v.facts.slice(1).map((f) => <li key={f}>{f}</li>)}</ul>}
        {v.recommendation && <p className="os-code-guess">模型建议“{v.recommendation.label}”
          {v.recommendation.strong ? "，数据有支持，已填进去" : `，但数据没有支持它：${codeWhyWeak(v.recommendation, v.rows)}`}。依据：{v.recommendation.basis || "没写"}
          {guess && <button type="button" className="pr-link" onClick={() => set(v.value, { label: guess.label, description: guess.description })}>采用这个</button>}</p>}
        <div className="os-code-inputs">
          <input aria-label={`取值 ${v.value} 的含义`} placeholder="这个代码指什么" maxLength={40} value={form[v.value].label} onChange={(e) => set(v.value, { label: e.target.value })} />
          <input aria-label={`取值 ${v.value} 的说明`} placeholder="说明（选填）" maxLength={200} value={form[v.value].description} onChange={(e) => set(v.value, { description: e.target.value })} />
        </div>
      </li>;
    })}</ul>
    {client.newer ? <NewerLink client={client} /> : <div className="os-code-save">
      <label>确认人<input value={client.by} maxLength={40} onChange={(e) => client.setBy(e.target.value)} /></label>
      <button type="button" className="pr-primary" disabled={client.busy || !client.can || Boolean(problem)} title={problem || client.why || undefined}
        onClick={() => client.onSaveCodes(item, codeBody(item, form))}>{client.busy ? "保存中…" : "确认含义"}</button>
      {!guessed && <button type="button" className="pr-link" disabled={client.busy || !client.canDraft} title={client.canDraft ? "请字段释义员按上面的事实猜一遍，只是建议" : client.draftWhy}
        onClick={() => client.onDraftCodes()}>让模型给个建议</button>}
      <button type="button" className="pr-link" disabled={client.busy || !client.can} title={client.can ? "这一列不是代码（例如版本号、数量），以后不再列出" : client.why}
        onClick={() => client.onDismissCodes(item)}>不是代码</button>
    </div>}
    <p className="pr-muted">没写含义的取值，各处仍显示为“含义未确认”。</p>
    {client.error?.key === item.id && <p role="alert" className="pr-error">{client.error.text}</p>}
  </div>;
}
