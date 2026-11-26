import React, { useState } from "react";
import { confirmConflictNote, confirmItem, decideRecord, getQueue, previewImpact, sendBack, withdrawRecord } from "./api.js";
import { ImpactList, ReceiptPanel, WorkspaceReceipt } from "./ImpactList.jsx";
import { KIND, groupTitle } from "./batchModel.js";
import { approveWarning, batchPlan, batchSummary, queueCounts, queueLegend, queueRow, rejectProblem, sortByProblem } from "./confirmModel.js";
import { t } from "./i18n/index.js";
import { timeText } from "./format.js";
import { itemHref } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { citeLine, confirmersText, conflictLine, conflictNoteLine } from "./typeModel.js";
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
  if (item.kind === "approval") return t("review.row.waitApproval");
  return `${item.model_draft ? t("review.row.waitDraft") : t("review.row.waitConfirm")}${confirmersText(item) ? `. ${confirmersText(item)}` : ""}`;
}

/** One item of the queue as one compact row: what it is and its state, one line of what changed, the real problems set apart, and Confirm / Send back in the row. */
function Row({ item, picked, onPick, onChanged, onConfirmed }) {
  const row = queueRow(item);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sure, setSure] = useState(false);   // Approve writes a new version of a dataset: the first click asks, the second does it
  const [impact, setImpact] = useState(null);   // Confirm first shows what it would do to the board numbers: null, {status: loading | ready | failed, data, error}
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
  const confirm = () => act(async () => {
    if (row.mode === "approve") return decideRecord(item.record, "approve");
    await confirmItem(item.element, item.version, item.seen);
    onConfirmed?.([item.element]);
  });
  const look = async () => {   // the same body the confirmation sends, run on a copy of the workspace
    setImpact({ status: "loading" });
    try {
      setImpact({ status: "ready", data: await previewImpact({ element: item.element, version: item.version, ...(item.seen ? { seen: item.seen } : {}) }) });
    } catch (e) {
      setImpact({ status: "failed", error: e.message });
    }
  };
  const sendBackNow = () => act(() => (item.kind === "approval" ? decideRecord(item.record, "reject", reason.trim()) : sendBack(item.element, item.version, reason.trim())));
  const needReason = rejectProblem(reason);
  const batchable = row.mode === "confirm" || row.mode === "approve";
  return (
    <li className={`q-row${row.hasError ? " q-error" : ""}`}>
      <div className="q-main">
        {batchable ? (
          <input type="checkbox" className="q-pick" checked={picked} onChange={(e) => onPick(item.element, e.target.checked)} aria-label={t("review.row.pickAria", { title: item.title })} />
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
          {!row.summary && !row.problems.length && item.kind === "pipeline" && <p className="muted small">{t("review.row.pipelineSee")}</p>}
          {(row.mode === "wait" || row.mode === "blocked") && <p className="muted small">{waitWords(item, row.mode)}</p>}
          {row.mode === "repropose" && <p className="small"><a href={itemHref(item)}>{t("review.row.repropose")}</a> <span className="muted">{t("review.row.reproposeNote")}</span></p>}
          {sure && (
            <div className="q-warn" role="alert">
              <p><Icon name="alert" size={14} /> {warning}</p>
              <p className="inline">
                <button className="primary" disabled={busy} onClick={() => { setSure(false); confirm(); }}>{t("review.row.sureApprove")}</button>
                <button className="plain" onClick={() => setSure(false)}>{t("review.row.notYet")}</button>
              </p>
            </div>
          )}
          {impact && (
            <div className="q-impact">
              {impact.status === "loading" && <p className="muted small">{t("review.impact.loading")}</p>}
              {impact.status === "failed" && <p className="warn small">{t("review.impact.failed", { error: impact.error })}</p>}
              {impact.status === "ready" && <ImpactList impact={impact.data} />}
              <p className="inline">
                <button className="primary" disabled={busy || impact.status === "loading" || Boolean(impact.data?.refused)} onClick={() => { setImpact(null); confirm(); }}>{t("review.impact.confirmNow")}</button>
                <button className="plain" onClick={() => setImpact(null)}>{t("review.impact.notYet")}</button>
              </p>
            </div>
          )}
          {asking && (
            <div className="q-ask">
              <input type="text" aria-label={t("review.row.reasonAria")} value={reason} maxLength={300} placeholder={t("review.row.reasonPlaceholder")} autoFocus onChange={(e) => setReason(e.target.value)} />
              <button className="danger" disabled={busy || Boolean(needReason)} onClick={sendBackNow}>{t("review.row.sendBack")}</button>
              <button className="plain" onClick={() => { setAsking(false); setReason(""); }}>{t("common.cancel")}</button>
              {needReason && reason !== "" && <span className="muted small">{needReason}</span>}
            </div>
          )}
          {error && <p className="error small">{error}</p>}
          <p className="muted small q-meta">{item.proposed_by ? t("review.row.proposedBy", { who: item.proposed_by }) : t("review.row.written")} · {timeText(item.written_at)}</p>
        </div>
        {!asking && !sure && !impact && (
          <div className="q-actions">
            {row.mode === "confirm" && <button className="primary" disabled={busy} onClick={look}>{t("review.row.confirm")}</button>}
            {row.mode === "approve" && <button className="primary" disabled={busy} onClick={() => setSure(true)}>{t("review.row.approve")}</button>}
            {row.canReject && <button className="secondary" disabled={busy} onClick={() => setAsking(true)}>{t("review.row.sendBack")}</button>}
            {row.mode === "withdraw" && <button className="secondary" disabled={busy} onClick={() => act(() => withdrawRecord(item.record))}>{t("review.row.withdraw")}</button>}
            {row.mode === "open" && <a className="button primary" href={itemHref(item)}>{item.kind === "pipeline" ? t("review.row.seeChange") : t("review.row.pickValues")}</a>}
          </div>
        )}
      </div>
    </li>
  );
}

/** Two rules of a type that disagree (cited_rules): both rules with what each cites, the rows that meet both conditions, and the "known" note. A note waiting for
 * a second person is confirmed here; a note is written on the type's page. */
function ConflictRow({ item, onChanged }) {
  const c = item.conflict;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmConflictNote(item.id, item.key);
      onChanged();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  return (
    <li className="q-row">
      <div className="q-main">
        <span className="q-pick" />
        <div className="q-body">
          <div className="q-title">
            <span className="q-kind">{t("types.conflicts.title")}</span>
            <a href={hrefFor({ page: "type", id: item.id, tab: "props" })}>{item.title}</a>
          </div>
          <p className="q-problem q-warn"><Icon name="alert" size={14} /> {conflictLine(c)}</p>
          {c.rules.map((r) => <p key={r.index} className="q-summary small">{r.says}{r.cite && <span className="muted"> — {citeLine(r.cite)}</span>}</p>)}
          {c.note && <p className="muted small">{conflictNoteLine(c.note)}</p>}
          {error && <p className="error small">{error}</p>}
        </div>
        <div className="q-actions">
          {item.can_confirm ? <button className="primary" disabled={busy} onClick={confirm}>{t("types.conflicts.confirm")}</button>
            : <a className="button secondary" href={hrefFor({ page: "type", id: item.id, tab: "props" })}>{t("types.conflicts.record")}</a>}
        </div>
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
            <span className="q-kind">{t("review.kind.upload")}</span>
            <strong>{groupTitle(group.dataset, group.version, group.items.length)}</strong>
            <span className="muted small">{t("review.group.uploadedBy", { who: group.uploaded_by ?? t("review.group.unknown"), time: timeText(group.uploaded_at) })}</span>
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
          {group.hidden > 0 && <p className="warn small">{t("review.group.hidden", { count: group.hidden })}</p>}
        </div>
        <div className="q-actions">
          <a className="button primary" href={hrefFor({ page: "confirmgroup", dataset: group.dataset, version: group.version })}>{t("review.group.together")}</a>
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
  const [receiptFor, setReceiptFor] = useState(null);   // the definitions just confirmed: their receipt is shown at the top until closed
  const [summary, setSummary] = useState(false);
  const data = state.data;
  const items = sortByProblem((data?.items ?? []).filter((i) => (!mineOnly || i.can_confirm) && !i.group && i.kind !== "conflict"));
  const conflicts = (data?.items ?? []).filter((i) => i.kind === "conflict" && (!mineOnly || i.can_confirm));   // two rules that disagree: listed apart, confirmed by their own note
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
        results.push({ title: step.title, ok: true, element: step.call === "approve" ? null : step.element });
      } catch (e) {
        results.push({ title: step.title, ok: false, error: e.message });
      }
    }
    setPicked(new Set());
    setSaid(batchSummary(results));
    const confirmed = results.filter((r) => r.ok && r.element).map((r) => r.element);
    if (confirmed.length) setReceiptFor(confirmed);
    setBusy(false);
    reload();
  };
  return (
    <main className="page has-bar">
      <PageHeader crumbs={[{ label: t("review.page.crumbGroup") }, { label: t("review.page.title") }]} title={t("review.page.title")} sub={data ? queueCounts(data).text : undefined}
        actions={<>
          <button className="secondary" onClick={() => setSummary(!summary)} aria-expanded={summary}>{t("review.summary.button")}</button>
          <label className="check"><input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} /> {t("review.page.mine")}</label>
        </>} />
      {summary && <WorkspaceReceipt onClose={() => setSummary(false)} />}
      {receiptFor && <ReceiptPanel elements={receiptFor} onClose={() => setReceiptFor(null)} />}
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>}
      {state.status === "loading" && !data && <p className="muted">{t("common.loading")}</p>}
      {said && <p className="notice-line" role="status">{said}</p>}
      {data && data.items.length > 0 && <p className="muted small q-legend">{queueLegend()}</p>}
      {data?.hidden_by_rules > 0 && <p className="warn">{t("review.page.hiddenRules", { count: data.hidden_by_rules })}</p>}
      {data && !data.items.length && !data.hidden_by_rules && (
        <EmptyState icon="check-circle" title={t("review.page.emptyTitle")} text={t("review.page.emptyText")} />
      )}
      {data && data.items.length > 0 && (
        <ul className="queue">
          {(data.groups ?? []).map((g) => <GroupRow key={g.key} group={g} items={data.items} />)}
          {items.map((item) => <Row key={`${item.element}@${item.version}@${item.state}`} item={item} picked={pickedHere.has(item.element)} onPick={pick} onChanged={reload} onConfirmed={setReceiptFor} />)}
          {conflicts.map((item) => <ConflictRow key={item.element} item={item} onChanged={reload} />)}
        </ul>
      )}
      {batchable.length > 0 && (
        <div className="batch-bar" role="region" aria-label={t("review.batch.aria")}>
          <span>{pickedHere.size ? t("review.batch.selected", { count: pickedHere.size }) : t("review.batch.ready", { count: batchable.length })}</span>
          {askBatch && (
            <span className="q-warn q-warn-bar" role="alert">
              {t("review.batch.warn", { count: approvals.length })}
              <button className="primary" onClick={runBatch}>{t("review.batch.proceed")}</button>
              <button className="plain" onClick={() => setAskBatch(false)}>{t("review.batch.notNow")}</button>
            </span>
          )}
          {risky > 0 && <span className="q-error-text">{t("review.batch.risky", { count: risky })}</span>}
          <span className="batch-spacer" />
          <button className="secondary" onClick={() => setPicked(new Set(batchable.filter((i) => !queueRow(i).hasError).map((i) => i.element)))}>{t("review.batch.allClean")}</button>
          {pickedHere.size > 0 && <button className="plain" onClick={() => setPicked(new Set())}>{t("review.batch.clear")}</button>}
          <button className="primary" disabled={busy || !plan.length} onClick={() => (approvals.length ? setAskBatch(true) : runBatch())}>{busy ? t("review.batch.working") : plan.length ? t(approvals.length === plan.length ? "review.batch.approve" : "review.batch.confirm", { count: plan.length }) : t("review.batch.pickFirst")}</button>
        </div>
      )}
    </main>
  );
}
