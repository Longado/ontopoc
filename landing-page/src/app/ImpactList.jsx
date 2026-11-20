import React from "react";
import { getReceipt, getWorkspaceReceipt } from "./api.js";
import { CopyButton } from "./CopyButton.jsx";
import { t } from "./i18n/index.js";
import { impactView, receiptMarkdown, summaryMarkdown, summaryView } from "./impactModel.js";
import { timeText } from "./format.js";
import { useLoad } from "./useLoad.js";

function Figure({ cell }) {
  return (
    <span className={cell.refused ? "impact-refused" : cell.grey ? "impact-grey" : undefined}>
      {cell.text}
      {cell.note && <span className="impact-note">{cell.note}</span>}
    </span>
  );
}

/** The board cards a change moves, as one compact table (看板 · 卡片 · 现在 · 确认后 · 变化), the sentence over it (also when nothing moves), the saved answers that used
 * it and whether the work was capped. `upload`: the columns say before and after an upload; `labels` puts other words on the two number columns (a receipt). */
export function ImpactList({ impact, upload = false, labels = null }) {
  const view = impactView(impact, Boolean(labels));
  const title = labels?.title ?? t(upload ? "review.impact.titleUpload" : "review.impact.title");
  return (
    <section className="impact" aria-label={title}>
      <p className="impact-head"><strong>{title}</strong><span className={view.refused ? "error" : undefined}>{view.sentence}</span></p>
      {view.rows.length > 0 && (
        <div className="impact-wrap">
          <table className="impact-table">
            <thead>
              <tr>
                <th>{t("review.impact.board")}</th><th>{t("review.impact.card")}</th>
                <th className="num">{labels?.now ?? t("review.impact.now")}</th><th className="num">{labels?.after ?? t(upload ? "review.impact.afterUpload" : "review.impact.after")}</th>
                <th>{t("review.impact.change")}</th>
              </tr>
            </thead>
            <tbody>
              {view.rows.map((r) => (
                <tr key={r.key} className={r.change.level === "same" ? "impact-same" : undefined}>
                  <td>{r.board}</td>
                  <td>{r.card}</td>
                  <td className="num"><Figure cell={r.now} /></td>
                  <td className="num"><Figure cell={r.after} /></td>
                  <td className={`impact-change impact-${r.change.level}`}>{r.change.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {view.rows.length > 0 && !labels && <p className="muted small">{t(upload ? "review.impact.basisUpload" : "review.impact.basis")}</p>}
      {view.answers && <p className="muted small">{view.answers}</p>}
      {view.capped && <p className="warn small">{view.capped}</p>}
    </section>
  );
}

/** The receipt after a confirmation: what changed, who proposed and confirmed it on which version, the board numbers before and after; copied as Markdown. */
export function ReceiptPanel({ elements, onClose }) {
  const [state] = useLoad(() => getReceipt(elements), [elements]);
  const receipt = state.data;
  return (
    <section className="card receipt" aria-label={t("review.receipt.title")}>
      <div className="receipt-head">
        <h2>{t("review.receipt.title")}</h2>
        <span className="batch-spacer" />
        {receipt && <CopyButton text={() => receiptMarkdown(receipt)} label={t("review.receipt.copy")} done={t("review.receipt.copied")} className="primary" />}
        <button className="plain" onClick={onClose}>{t("review.receipt.close")}</button>
      </div>
      {state.status === "loading" && <p className="muted">{t("review.receipt.loading")}</p>}
      {state.status === "error" && <p className="error">{t("review.receipt.failed", { error: state.error })}</p>}
      {receipt && (
        <>
          {receipt.items.map((item) => (
            <div key={item.element} className="receipt-item">
              <p><strong>{item.title}</strong></p>
              <p className="small">{item.before != null ? t("review.receipt.before", { text: item.before }) : t("review.receipt.first")}</p>
              <p className="small">{t("review.receipt.after", { text: item.after })}</p>
              <p className="muted small">
                {t("review.receipt.who", { proposed: item.proposed_by ?? t("review.group.unknown"), confirmed: item.confirmed_by ?? t("review.group.unknown"), at: timeText(item.confirmed_at) })}
                {" · "}
                {t("review.receipt.on", { on: Object.entries(item.on ?? {}).map(([name, version]) => t("review.receipt.version", { name, version })).join(t("review.receipt.sep")) || "—" })}
              </p>
            </div>
          ))}
          <ImpactList impact={receipt} labels={{ title: t("review.receipt.numbers"), now: t("review.receipt.from"), after: t("review.receipt.to") }} />
        </>
      )}
    </section>
  );
}

/** What the workspace stands on, for builders: definitions by state, the checks behind the confirmed ones, the rows they read, who confirmed what on which version. */
export function WorkspaceReceipt({ onClose }) {
  const [state] = useLoad(getWorkspaceReceipt, []);
  const summary = state.data;
  const view = summary ? summaryView(summary) : null;
  return (
    <section className="card receipt" aria-label={t("review.summary.title")}>
      <div className="receipt-head">
        <h2>{t("review.summary.title")}</h2>
        <span className="batch-spacer" />
        {summary && <CopyButton text={() => summaryMarkdown(summary)} label={t("review.receipt.copy")} done={t("review.receipt.copied")} className="primary" />}
        <button className="plain" onClick={onClose}>{t("review.receipt.close")}</button>
      </div>
      {state.status === "loading" && <p className="muted">{t("review.receipt.loading")}</p>}
      {state.status === "error" && <p className="error">{t("review.receipt.failed", { error: state.error })}</p>}
      {view && (
        <>
          <ul className="checks">
            {view.kinds.map((k) => <li key={k.kind}>{k.kind}{t("review.receipt.colon")}{k.states}</li>)}
            {view.needs && <li className="warn">{view.needs}</li>}
            <li>{view.checks}</li>
            <li>{view.rows}</li>
          </ul>
          {view.who.length > 0 && (
            <>
              <h3 className="small">{t("review.summary.who")}</h3>
              <div className="impact-wrap">
                <table className="impact-table">
                  <thead><tr><th>{t("review.summary.colWhat")}</th><th>{t("review.summary.colBy")}</th><th>{t("review.summary.colAt")}</th><th>{t("review.summary.colOn")}</th></tr></thead>
                  <tbody>{view.who.map((w) => <tr key={w.key}><td>{w.what}</td><td>{w.by}</td><td>{w.at}</td><td>{w.on}</td></tr>)}</tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
