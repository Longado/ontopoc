import { createContext } from "react";
import { codeGuess, codeWhyWeak } from "./openItemsModel.js";

/** What each code column's values mean ({ "订单.状态码": { labels } }), for the answers and field lists that show codes. */
export const CodeMeanings = createContext(null);

/** What stands where a definition would be saved when a newer run of the same file is waiting: definitions are changed there. */
export function NewerLink({ client }) {
  return <div className="os-code-save"><button type="button" className="os-graph-link" onClick={() => client.onOpenRun(client.newer)}>有更新的版本在等你看 →</button></div>;
}

/** A code column's values, one row each: its count and what the data says about it, the model's guess where there is one (marked when
 *  the data does not back it, and then not put in the box), and a place to write what it means, in `form` (codeStart's shape). */
export function CodeValues({ item, form, setForm }) {
  const set = (value, part) => setForm({ ...form, [value]: { ...form[value], ...part } });
  return <ul className="os-code-list">{item.column.values.map((v) => {
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
    })}</ul>;
}
