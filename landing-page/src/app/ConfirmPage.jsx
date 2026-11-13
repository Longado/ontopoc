import React, { useState } from "react";
import { confirmItem, decideRecord, getQueue, sendBack, withdrawRecord } from "./api.js";
import { timeText } from "./format.js";
import { itemAction, itemHref, waitingText } from "./relationModel.js";
import { State } from "./TypesPage.jsx";
import { confirmersText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

import { viewWaitingText } from "./viewModel.js";

const KIND = { type: "对象类型", meaning: "取值含义", relation: "关系", view: "视图", action: "行为", approval: "行为提交" };

function Card({ item, onChanged }) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const action = itemAction(item);
  const act = async (run) => {
    setBusy(true);
    setError("");
    try {
      await run();
      onChanged();
    } catch (e) {
      setError(e.message);
      if (e.code === 409) onChanged();   // what was read has moved: show what is there now
    }
    setBusy(false);
  };
  return (
    <section className="card">
      <div className="page-head">
        <h2 className="item-title">{KIND[item.kind]} <a href={itemHref(item)}>{item.title}</a></h2>
        <State item={item} />
      </div>
      <p className="muted small">{item.kind === "approval" ? (item.state === "needs_look" ? "数据变了，不能批准；可以驳回，提交的人可以撤回后重新提交" : "") : stateLine(item, "它") || "需要再看一次"}</p>
      <ul className="checks">
        {item.lines.map((l, i) => <li key={i} className={l.ok ? "" : "warn"}>{l.text}</li>)}
      </ul>
      {item.kind === "approval" && !asking && (
        <div className="inline">
          {item.can_confirm && <button className="primary" disabled={busy} onClick={() => act(() => decideRecord(item.record, "approve"))}>批准</button>}
          {item.can_confirm && <button className="secondary" disabled={busy} onClick={() => setAsking(true)}>驳回</button>}
          {item.can_withdraw && <button className="secondary" disabled={busy} onClick={() => act(() => withdrawRecord(item.record))}>撤回</button>}
          {item.state === "needs_look" && !item.can_withdraw && <button className="secondary" disabled={busy} onClick={() => setAsking(true)}>驳回</button>}
        </div>
      )}
      {item.kind === "approval" && asking && (
        <div className="inline wide">
          <input type="text" aria-label="驳回的说明" value={reason} maxLength={300} placeholder="说明（可以不写）" onChange={(e) => setReason(e.target.value)} />
          <button className="primary" disabled={busy} onClick={() => act(() => decideRecord(item.record, "reject", reason))}>驳回</button>
          <button className="plain" onClick={() => setAsking(false)}>取消</button>
        </div>
      )}
      {item.kind === "approval" && !item.can_confirm && !item.can_withdraw && item.state === "pending" && <p className="muted">需要另一位构建者批准，提交的人自己不能批准。</p>}
      {item.kind !== "approval" && action === "confirm" && !asking && (
        <div className="inline">
          <button className="primary" disabled={busy} onClick={() => act(() => confirmItem(item.element, item.version, item.seen))}>确认</button>
          <button className="secondary" disabled={busy} onClick={() => setAsking(true)}>退回</button>
        </div>
      )}
      {item.kind !== "approval" && action === "confirm" && asking && (
        <div className="inline wide">
          <input type="text" aria-label="退回的理由" value={reason} maxLength={300} placeholder="写明哪里不对" onChange={(e) => setReason(e.target.value)} />
          <button className="primary" disabled={busy || !reason.trim()} onClick={() => act(() => sendBack(item.element, item.version, reason))}>退回</button>
          <button className="plain" onClick={() => setAsking(false)}>取消</button>
        </div>
      )}
      {item.kind !== "approval" && action === "wait" && (
        <p className="muted">{item.model_draft ? "模型写的草稿，等一位构建者看过确认。" : "需要另一位构建者确认，不能由提出的人自己确认。"}{confirmersText(item) && ` ${confirmersText(item)}`}</p>
      )}
      {item.kind !== "approval" && action === "blocked" && <p className="warn">{item.kind === "view" ? viewWaitingText(item) : waitingText(item)}</p>}
      {action === "repropose" && <p><a href={itemHref(item)}>到类型的属性页，按现在的数据写新的含义</a> <span className="muted small">提出后由另一位确认</span></p>}
      {error && <p className="error">{error}</p>}
      <p className="muted small">{item.proposed_by ? `${item.proposed_by} 提出` : "写入"} {timeText(item.written_at)}</p>
    </section>
  );
}

export function ConfirmPage() {
  const [state, reload] = useLoad(getQueue, []);
  const [mineOnly, setMineOnly] = useState(false);
  const items = (state.data?.items ?? []).filter((i) => !mineOnly || i.can_confirm);
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>待确认</h1>
        <div className="head-actions">
          <label className="check"><input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} /> 只看我能确认的</label>
        </div>
      </div>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && <p className="muted" style={{ marginBottom: 16 }}>共 {state.data.items.length} 项，其中 {state.data.count} 项你现在能确认</p>}
      {state.data && !state.data.items.length && <p className="muted">没有要确认的。新提出的定义、数据变了需要再看的，会出现在这里。</p>}
      <div className="cards">
        {items.map((item) => <Card key={`${item.element}@${item.version}@${item.state}`} item={item} onChanged={reload} />)}
      </div>
    </main>
  );
}
