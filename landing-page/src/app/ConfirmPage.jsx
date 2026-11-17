import React, { useState } from "react";
import { confirmItem, decideRecord, getQueue, sendBack, withdrawRecord } from "./api.js";
import { KIND, groupTitle } from "./batchModel.js";
import { QUEUE_LEGEND, approveWarning, batchPlan, batchSummary, queueCounts, queueRow, rejectProblem, sortByProblem } from "./confirmModel.js";
import { timeText } from "./format.js";
import { itemHref } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { confirmersText } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { waitingText as derivedWaitingText } from "./derivedModel.js";
import { viewWaitingText } from "./viewModel.js";
import { waitingText } from "./relationModel.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { Icon } from "./ui/Icon.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

/** Why nothing can be done in the row, in words. */
function waitWords(item, mode) {
  if (mode === "blocked") return item.kind === "view" ? viewWaitingText(item) : item.kind === "derived" ? derivedWaitingText(item) : waitingText(item);
  if (item.kind === "approval") return "需要另一位建设者批准，提交的人自己不能批准";
  return `${item.model_draft ? "模型写的草稿，等一位建设者看过确认" : "需要另一位建设者确认，不能由提出的人自己确认"}${confirmersText(item) ? `。${confirmersText(item)}` : ""}`;
}

/** One item of the queue as one compact row: what it is and its state, one line of what changed, the real problems set apart, and 确认 / 退回 in the row. */
function Row({ item, picked, onPick, onChanged }) {
  const row = queueRow(item);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sure, setSure] = useState(false);   // 批准 writes a new version of a dataset: the first click asks, the second does it
  const warning = approveWarning(item);
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
  const confirm = () => act(() => (row.mode === "approve" ? decideRecord(item.record, "approve") : confirmItem(item.element, item.version, item.seen)));
  const sendBackNow = () => act(() => (item.kind === "approval" ? decideRecord(item.record, "reject", reason.trim()) : sendBack(item.element, item.version, reason.trim())));
  const needReason = rejectProblem(reason);
  const batchable = row.mode === "confirm" || row.mode === "approve";
  return (
    <li className={`q-row${row.hasError ? " q-error" : ""}`}>
      <div className="q-main">
        {batchable ? (
          <input type="checkbox" className="q-pick" checked={picked} onChange={(e) => onPick(item.element, e.target.checked)} aria-label={`选中：${item.title}`} />
        ) : <span className="q-pick" />}
        <div className="q-body">
          <div className="q-title">
            <span className="q-kind">{row.kind}</span>
            <a href={itemHref(item)}>{item.title}</a>
            <State item={item} />
            <span className="q-tag muted small">{row.tag}</span>
          </div>
          {row.summary && <p className={`q-summary${row.summaryLevel === "ok" ? "" : " q-" + row.summaryLevel}`}>{row.summary}</p>}
          {row.problems.map((p, i) => (
            <p key={i} className={`q-problem q-${p.level}`}><Icon name="alert" size={14} /> {p.text}</p>
          ))}
          {!row.summary && !row.problems.length && item.kind === "pipeline" && <p className="muted small">改了什么要在管道页里看</p>}
          {(row.mode === "wait" || row.mode === "blocked") && <p className="muted small">{waitWords(item, row.mode)}</p>}
          {row.mode === "repropose" && <p className="small"><a href={itemHref(item)}>到类型的属性页，按现在的数据写新的含义</a> <span className="muted">提出后由另一位确认</span></p>}
          {sure && (
            <div className="q-warn" role="alert">
              <p><Icon name="alert" size={14} /> {warning}</p>
              <p className="inline">
                <button className="primary" disabled={busy} onClick={() => { setSure(false); confirm(); }}>确认批准，写成新版本</button>
                <button className="plain" onClick={() => setSure(false)}>先不批准</button>
              </p>
            </div>
          )}
          {asking && (
            <div className="q-ask">
              <input type="text" aria-label="退回的理由" value={reason} maxLength={300} placeholder="写明哪里不对（必填）" autoFocus onChange={(e) => setReason(e.target.value)} />
              <button className="danger" disabled={busy || Boolean(needReason)} onClick={sendBackNow}>退回</button>
              <button className="plain" onClick={() => { setAsking(false); setReason(""); }}>取消</button>
              {needReason && reason !== "" && <span className="muted small">{needReason}</span>}
            </div>
          )}
          {error && <p className="error small">{error}</p>}
          <p className="muted small q-meta">{item.proposed_by ? `${item.proposed_by} 提出` : "写入"} {timeText(item.written_at)}</p>
        </div>
        {!asking && !sure && (
          <div className="q-actions">
            {row.mode === "confirm" && <button className="primary" disabled={busy} onClick={confirm}>确认</button>}
            {row.mode === "approve" && <button className="primary" disabled={busy} onClick={() => setSure(true)}>批准</button>}
            {row.canReject && <button className="secondary" disabled={busy} onClick={() => setAsking(true)}>退回</button>}
            {row.mode === "withdraw" && <button className="secondary" disabled={busy} onClick={() => act(() => withdrawRecord(item.record))}>撤回</button>}
            {row.mode === "open" && <a className="button primary" href={itemHref(item)}>{item.kind === "pipeline" ? "看改了什么" : "选新值，再确认"}</a>}
          </div>
        )}
      </div>
    </li>
  );
}

/** What one upload moved, as one row: the things it sent back, and the way into the screen that confirms them together. */
function GroupRow({ group, items }) {
  const byElement = Object.fromEntries(items.map((i) => [i.element, i]));
  return (
    <li className={`q-row q-group${group.items.some((e) => queueRow(byElement[e]).hasError) ? " q-error" : ""}`}>
      <div className="q-main">
        <span className="q-pick" />
        <div className="q-body">
          <div className="q-title">
            <span className="q-kind">一次上传</span>
            <strong>{groupTitle(group.dataset, group.version, group.items.length)}</strong>
            <span className="muted small">{group.uploaded_by ?? "未署名"} 上传 {timeText(group.uploaded_at)}</span>
          </div>
          {group.items.map((element) => {
            const item = byElement[element];
            const row = queueRow(item);
            return (
              <div key={element} className="q-member">
                <p className="q-summary"><span className="q-kind">{row.kind}</span> <a href={itemHref(item)}>{item.title}</a> <State item={item} /></p>
                {row.summary && <p className={`q-summary q-sub${row.summaryLevel === "ok" ? "" : " q-" + row.summaryLevel}`}>{row.summary}</p>}
                {row.problems.map((p, i) => <p key={i} className={`q-problem q-${p.level}`}><Icon name="alert" size={14} /> {p.text}</p>)}
              </div>
            );
          })}
          {group.hidden > 0 && <p className="warn small">还有 {group.hidden} 项你看不到</p>}
        </div>
        <div className="q-actions">
          <a className="button primary" href={hrefFor({ page: "confirmgroup", dataset: group.dataset, version: group.version })}>一起看</a>
        </div>
      </div>
    </li>
  );
}

export function ConfirmPage() {
  const [state, reload] = useLoad(getQueue, []);
  const [mineOnly, setMineOnly] = useState(false);
  const [picked, setPicked] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState("");
  const [askBatch, setAskBatch] = useState(false);   // a batch that approves data changes asks once, in words
  const data = state.data;
  const items = sortByProblem((data?.items ?? []).filter((i) => (!mineOnly || i.can_confirm) && !i.group));
  const pickedHere = new Set([...picked].filter((e) => items.some((i) => i.element === e)));
  const plan = batchPlan(items, pickedHere);
  const batchable = items.filter((i) => ["confirm", "approve"].includes(queueRow(i).mode));
  const risky = plan.filter((p) => queueRow(items.find((i) => i.element === p.key)).hasError).length;
  const pick = (element, on) => {
    const next = new Set(picked);
    if (on) next.add(element);
    else next.delete(element);
    setPicked(next);
  };
  const approvals = plan.filter((p) => p.call === "approve").map((p) => items.find((i) => i.element === p.key));
  const runBatch = async () => {
    setAskBatch(false);
    setBusy(true);
    setSaid("");
    const results = [];
    for (const step of plan) {
      try {
        if (step.call === "approve") await decideRecord(step.record, "approve");
        else await confirmItem(step.element, step.version, step.seen);
        results.push({ title: step.title, ok: true });
      } catch (e) {
        results.push({ title: step.title, ok: false, error: e.message });
      }
    }
    setPicked(new Set());
    setSaid(batchSummary(results));
    setBusy(false);
    reload();
  };
  return (
    <main className="page has-bar">
      <PageHeader crumbs={[{ label: "业务对象" }, { label: "待确认" }]} title="待确认" sub={data ? queueCounts(data).text : undefined}
        actions={<label className="check"><input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} /> 只看我能确认的</label>} />
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !data && <p className="muted">加载中</p>}
      {said && <p className="notice-line" role="status">{said}</p>}
      {data && data.items.length > 0 && <p className="muted small q-legend">{QUEUE_LEGEND}</p>}
      {data?.hidden_by_rules > 0 && <p className="warn">有 {data.hidden_by_rules} 项因为行规则你看不到。要看，请管理员在权限页给你开“全部行”。</p>}
      {data && !data.items.length && !data.hidden_by_rules && (
        <EmptyState icon="check-circle" title="没有要确认的" text="新提出的定义、数据变了需要再看的，会出现在这里。" />
      )}
      {data && data.items.length > 0 && (
        <ul className="queue">
          {(data.groups ?? []).map((g) => <GroupRow key={g.key} group={g} items={data.items} />)}
          {items.map((item) => <Row key={`${item.element}@${item.version}@${item.state}`} item={item} picked={pickedHere.has(item.element)} onPick={pick} onChanged={reload} />)}
        </ul>
      )}
      {batchable.length > 0 && (
        <div className="batch-bar" role="region" aria-label="批量确认">
          <span>{pickedHere.size ? `已选 ${pickedHere.size} 项` : `${batchable.length} 项可以直接确认`}</span>
          {askBatch && (
            <span className="q-warn q-warn-bar" role="alert">
              所选里有 {approvals.length} 项数据改动：批准后相关数据集各会有新版本，用到它们的已确认的定义会重新检查，可能变成需再看。
              <button className="primary" onClick={runBatch}>仍然处理</button>
              <button className="plain" onClick={() => setAskBatch(false)}>先不</button>
            </span>
          )}
          {risky > 0 && <span className="q-error-text">所选里有 {risky} 项带问题，确认前请先看过</span>}
          <span className="batch-spacer" />
          <button className="secondary" onClick={() => setPicked(new Set(batchable.filter((i) => !queueRow(i).hasError).map((i) => i.element)))}>全选没有问题的</button>
          {pickedHere.size > 0 && <button className="plain" onClick={() => setPicked(new Set())}>清除</button>}
          <button className="primary" disabled={busy || !plan.length} onClick={() => (approvals.length ? setAskBatch(true) : runBatch())}>{busy ? "处理中" : plan.length ? `${approvals.length === plan.length ? "批准" : "确认"}所选 ${plan.length} 项` : "先勾选要处理的"}</button>
        </div>
      )}
    </main>
  );
}
