import { useEffect, useState } from "react";

import { adoptAll, ruleGroups, ruleStatus, toggleRule } from "./rulesModel.js";
import { typeLabel } from "./ontologyStudioModel.js";

const ruleText = (r) => (r.kind === "required" ? <><b>{r.field}</b><em>必填</em></> : <><b>{r.before}</b><i aria-label="不晚于">→</i><b>{r.after}</b></>);

/** Rules code found in the data: adopted ones checked on every run, candidates to adopt or decline. */
export function RulesView({ run, canSave, busy, error, onSave }) {
  const [live, setLive] = useState(null);   // runs saved before rules existed ask the service once
  useEffect(() => {
    setLive(null);
    if (run.evaluation.rules || !run.saved_as) return;
    fetch(`/api/ontology/runs/${run.saved_as}/rules`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then(setLive, () => setLive(null));
  }, [run.saved_as, run.evaluation.rules]);
  const rules = run.evaluation.rules || live;
  if (!rules) return <section className="pr-card"><p className="pr-muted">{run.saved_as ? "读取中…" : "示例结果没有规则。"}</p></section>;
  const state = { adopted: rules.adopted.map((r) => r.id), declined: rules.declined };
  const save = (next) => canSave && onSave(next);
  const groups = ruleGroups(rules.candidates, run.ontology);
  return <>
    <section className="pr-card os-rules">
      <div className="pr-card-head"><h2>采纳的规则 <small>{rules.adopted.length}</small></h2></div>
      {!rules.adopted.length ? <p className="os-empty-line">—</p> : <ul className="os-rule-list">{rules.adopted.map((r) => { const status = ruleStatus(r); return <li key={r.id} className={`is-${status.kind}`}>
        <span className="os-rule-mark" aria-label={status.label} title={status.label}>{status.mark}</span>
        <span className="os-rule-type">{typeLabel(run.ontology, r.type)}</span><span className="os-rule-text">{ruleText(r)}</span>
        {r.violations?.count > 0 && <span className="os-rule-examples">{r.violations.examples.map((x) => <code key={x}>{x}</code>)}</span>}
        <button type="button" className="pr-link" disabled={busy || !canSave} onClick={() => save(toggleRule(state, r.id, "remove"))}>撤回</button>
      </li>; })}</ul>}
    </section>
    <section className="pr-card os-rules">
      <div className="pr-card-head"><h2>数据里找到的 <small>{rules.candidates.length}</small></h2>
        {rules.declined.length > 0 && <button type="button" className="pr-link" disabled={busy || !canSave} onClick={() => save({ ...state, declined: [] })} title="把不要的规则放回来">恢复不要的 {rules.declined.length} 条</button>}</div>
      {!groups.length && <p className="os-empty-line">—</p>}
      {groups.map((g) => <div key={g.type} className="os-rule-group">
        <h3>{g.label}</h3>
        {g.required.length > 0 && <div className="os-rule-row">
          <span className="os-rule-kind">必填</span>
          <span className="os-chips">{g.required.map((r) => <button key={r.id} type="button" disabled={busy || !canSave} title={`${r.holds} 个都有值，点一下采纳`} onClick={() => save(toggleRule(state, r.id, "adopt"))}>＋ {r.field}</button>)}</span>
          <span className="os-rule-actions"><button type="button" className="pr-link" disabled={busy || !canSave} onClick={() => save(adoptAll(state, g.required))}>全部采纳</button>
            <button type="button" className="pr-link os-muted-link" disabled={busy || !canSave} onClick={() => save(g.required.reduce((s, r) => toggleRule(s, r.id, "decline"), state))}>都不要</button></span>
        </div>}
        {g.orders.map((r) => <div key={r.id} className="os-rule-row">
          <span className="os-rule-kind">先后</span>
          <span className="os-rule-text" title={`${r.holds} 个都是这个顺序`}>{ruleText(r)}</span>
          <span className="os-rule-actions"><button type="button" className="pr-link" disabled={busy || !canSave} onClick={() => save(toggleRule(state, r.id, "adopt"))}>采纳</button>
            <button type="button" className="pr-link os-muted-link" disabled={busy || !canSave} onClick={() => save(toggleRule(state, r.id, "decline"))}>不要</button></span>
        </div>)}
      </div>)}
      {error && <p role="alert" className="pr-error">{error}</p>}
    </section>
  </>;
}
