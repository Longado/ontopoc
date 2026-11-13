import { useEffect, useRef, useState } from "react";

import { linkedHint } from "./cardModel.js";
import { CodeValues, NewerLink } from "./CodeMeaningForm.jsx";
import { REPEAT_CHOICES, codeBody, codeProblem, codeStart, dropFor, repeatBody } from "./openItemsModel.js";
import { cardEntry, isTyping, movedIndex, reopenedLine, replyAsks, replyForKey, replyProblem, replyRoute, stackLine } from "./reviewStackModel.js";

const REPEAT_HINT = Object.fromEntries(REPEAT_CHOICES.map(([rule, , hint]) => [rule, hint]));
const SHOWN_FACTS = 5;

function Examples({ examples }) {
  return <div className="os-stack-rows">
    <p className="pr-muted">{examples.table} 里的 {examples.rows.length} 行</p>
    <div className="os-table-scroll"><table className="os-fields">
      <thead><tr>{examples.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
      <tbody>{examples.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell || "—"}</td>)}</tr>)}</tbody>
    </table></div>
  </div>;
}

function Facts({ facts }) {
  const [all, setAll] = useState(false);
  if (!facts.length) return null;
  return <>
    <ul className="os-open-facts">{(all ? facts : facts.slice(0, SHOWN_FACTS)).map((f, i) => <li key={i}>{f}</li>)}</ul>
    {facts.length > SHOWN_FACTS && <button type="button" className="pr-link os-more-groups" onClick={() => setAll(!all)}>{all ? `只看前 ${SHOWN_FACTS} 条` : `展开其余 ${facts.length - SHOWN_FACTS} 条`}</button>}
  </>;
}

/** The form under the reply bar: what the picked reply still needs (a column, words) and the button that sends it. */
function ReplyForm({ item, reply, draft, setDraft, client, onSend, onCancel }) {
  const ref = useRef(null);
  const asks = replyAsks(item, reply);
  const route = replyRoute(item, reply);
  const problem = replyProblem(item, reply, draft, client.by) || (route === "code" && reply.id === "confirm" ? codeProblem(item, draft.codes) : "");
  const hint = linkedHint(item, { choice: reply.id, text: draft.text, basis: draft.basis });
  useEffect(() => { ref.current?.querySelector(asks?.required ? "textarea" : "select, button[type=submit]")?.focus(); }, [reply.id]);   // words that are required first; else the button, so Enter sends
  return <form ref={ref} className="os-reply-form" onSubmit={(e) => { e.preventDefault(); if (!problem && !client.busy) onSend(); }}
    onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onCancel(); } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !problem && !client.busy) onSend(); }}>
    {reply.id === "keep_latest" && <label>按哪一列定最新
      <select className="os-select" value={draft.column} onChange={(e) => setDraft({ column: e.target.value })}>
        <option value="">{item.repeat.columns.length ? "选一列（只列出数字或日期列）" : "这几行里没有一列能分出先后"}</option>
        {item.repeat.columns.map((c) => <option key={c} value={c}>{c}</option>)}
      </select></label>}
    {asks && <label>{asks.label}<textarea rows={2} maxLength={300} value={draft.text} onChange={(e) => setDraft({ text: e.target.value })} /></label>}
    {asks && <label>出处（选填，例如“10-27 会议”）<input maxLength={200} value={draft.basis} onChange={(e) => setDraft({ basis: e.target.value })} /></label>}
    {REPEAT_HINT[reply.id] && <p className="pr-muted">{REPEAT_HINT[reply.id]}</p>}
    {hint && <p className="pr-muted">{hint}</p>}
    <div className="os-go">
      <button type="submit" className="pr-primary" disabled={client.busy || Boolean(problem)} title={problem || undefined}>{client.busy ? "保存中…" : `记下“${reply.label}”`}</button>
      <button type="button" className="pr-link" onClick={onCancel}>取消</button>
    </div>
  </form>;
}

function StackCard({ item, run, onGo, requery, client, picked, setPicked, draft, setDraft }) {
  const mine = requery.question === item.question;
  const drop = dropFor(run, item);
  const reply = item.replies?.find((r) => r.id === picked) ?? null;
  const frozen = client.newer && ["code_meaning", "repeated_key"].includes(item.kind);   // definitions are changed on the newer run
  const send = async () => {
    const route = replyRoute(item, reply);
    const done = route === "code" ? (reply.id === "confirm" ? await client.onSaveCodes(item, codeBody(item, draft.codes)) : await client.onDismissCodes(item))
      : route === "repeat" ? await client.onSaveRepeat(item, repeatBody({ rule: reply.id, column: draft.column }))
        : await client.onReply(cardEntry(item, reply, draft));
    if (done) setPicked(null);
  };
  return <article className="os-stack-card" aria-label={`第 ${item.number} 件`}>
    <p className="os-open-ask"><b>{item.ask}</b>{item.from_model && <em className="os-chip-note" title="这一条是模型说的，代码没有核对过">模型的说法</em>}</p>
    {item.reopened && <p className="os-stack-reopened">{reopenedLine(item.reopened)}</p>}
    {item.examples && <Examples examples={item.examples} />}
    {item.kind === "code_meaning" ? <CodeValues item={item} form={draft.codes} setForm={(codes) => setDraft({ codes })} /> : <Facts facts={item.facts || []} />}
    {item.check && <p className={`os-stack-check is-${item.check.status}`}><b>核对</b> {item.check.text}</p>}
    {frozen ? <NewerLink client={client} /> : item.replies?.length > 0
      ? <div className="os-replies" role="group" aria-label="怎么答复">{item.replies.map((r, i) => <button key={r.id} type="button" className="os-reply" aria-pressed={picked === r.id}
        disabled={!client.can || client.busy} title={client.can ? REPEAT_HINT[r.id] : client.why} onClick={() => setPicked(picked === r.id ? null : r.id)}>
        <kbd>{i + 1}</kbd>{r.label}</button>)}</div>
      : <p className="pr-muted">这件事要照它的要求去做，做完它就从这里消失，不用在这里答复。</p>}
    {reply && !frozen && <ReplyForm item={item} reply={reply} draft={draft} setDraft={setDraft} client={client} onSend={send} onCancel={() => setPicked(null)} />}
    <div className="os-open-actions">
      <button type="button" className="os-graph-link" onClick={() => onGo(item.target)}>看依据 →</button>
      {drop && <button type="button" className="os-graph-link" disabled={!requery.can || requery.busy} title={requery.can ? "不再加这个条件，由代码重算这道题，不调模型" : requery.why}
        onClick={() => requery.onRequery({ question: item.question }, drop)}>{requery.busy && mine ? "重算中…" : "去掉这个条件重算"}</button>}
      {item.kind === "code_meaning" && !item.column.values.some((v) => v.recommendation) && !frozen && <button type="button" className="os-graph-link" disabled={client.busy || !client.canDraft}
        title={client.canDraft ? "请字段释义员按上面的事实猜一遍，只是建议" : client.draftWhy} onClick={() => client.onDraftCodes()}>让模型给个建议</button>}
    </div>
    {client.error?.key === item.id && <p role="alert" className="pr-error">{client.error.text}</p>}
  </article>;
}

/** 要确认的事 as a stack: one card at a time, a progress line, replies on the keys 1 to 4, J and K to move. */
export function ReviewStack({ run, items, decided, onGo, requery, client }) {
  const [at, setAt] = useState(0);
  const [picked, setPicked] = useState(null);
  const [drafts, setDrafts] = useState({});
  const index = Math.min(at, items.length - 1);
  const item = items[index];
  const draftOf = (it) => ({ text: "", basis: "", column: "", codes: it.kind === "code_meaning" ? codeStart(it) : null, ...drafts[it.id] });
  const setDraft = (part) => setDrafts((was) => ({ ...was, [item.id]: { ...draftOf(item), ...part } }));
  const go = (key) => { setAt(movedIndex(index, key, items.length)); setPicked(null); };
  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape" && isTyping(e.target)) { e.target.blur(); return; }
      if (isTyping(e.target)) return;
      if (e.key === "j" || e.key === "k") { e.preventDefault(); go(e.key); return; }
      const reply = replyForKey(item, e.key);
      if (reply && client.can && !client.busy && !(client.newer && ["code_meaning", "repeated_key"].includes(item.kind))) { e.preventDefault(); setPicked(reply.id); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const shown = { ...item, number: index + 1 };
  return <section className="os-stack" aria-label="要确认的事">
    <div className="os-stack-head">
      <p className="os-stack-line" aria-live="polite"><b>{stackLine(items.length, decided)}</b></p>
      <label className="os-stack-who">确认人<input value={client.by} maxLength={40} onChange={(e) => client.setBy(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); }} /></label>
      <span className="os-stack-nav">
        <button type="button" className="os-graph-link" disabled={index === 0} onClick={() => go("k")} title="上一件（K）">上一件</button>
        <span>{index + 1} / {items.length}</span>
        <button type="button" className="os-graph-link" disabled={index === items.length - 1} onClick={() => go("j")} title="下一件（J）">下一件</button>
      </span>
    </div>
    <StackCard key={item.id} item={shown} run={run} onGo={onGo} requery={requery} client={client} picked={picked} setPicked={setPicked} draft={draftOf(item)} setDraft={setDraft} />
  </section>;
}
