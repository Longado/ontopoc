import React from "react";
import { QuestionList, SeesNote } from "./AiBox.jsx";
import { planCard, proposalCard } from "./assistantModel.js";
import { formatNumber, useT } from "./i18n/index.js";
import { friendlyError, kindLine } from "./pipelineModel.js";
import { hrefFor } from "./routeModel.js";
import { Icon } from "./ui/Icon.jsx";

const n = (v) => formatNumber(Number(v));

/** "Done / Not done", worded from the keys the model of the card produced (what the response contains, nothing more). */
function Checked({ done, notDone, prefix, steps = [] }) {
  const t = useT();
  return (
    <div className="as-checked">
      <div>
        <h4>{t("ask.assistant.card.done")}</h4>
        <ul className="as-list done">{done.length ? done.map((x) => <li key={x.key}><Icon name="check" size={13} />{t(`ask.assistant.${prefix}.done.${x.key}`, x)}</li>) : <li className="muted">{t("ask.assistant.card.none")}</li>}</ul>
      </div>
      <div>
        <h4>{t("ask.assistant.card.notDone")}</h4>
        <ul className="as-list not">{notDone.length ? notDone.map((x) => <li key={x.key}><i aria-hidden="true" />{t(`ask.assistant.${prefix}.not.${x.key}`, { ...x, text: x.key === "failed" ? friendlyError(x.text, steps) : x.text })}</li>) : <li className="muted">{t("ask.assistant.card.none")}</li>}</ul>
      </div>
    </div>
  );
}

function Row({ label, children }) {
  return <div className="as-row"><dt>{label}</dt><dd>{children}</dd></div>;
}

/** When no model is configured: a plain assistant message, with a way to Settings for an admin. */
export function NoModel({ admin }) {
  const t = useT();
  return (
    <div className="as-notice" role="status">
      <strong>{t("ask.assistant.nomodel.title")}</strong>
      <p>{t("ask.assistant.nomodel.text")}</p>
      {admin ? <a className="button secondary" href={hrefFor({ page: "settings" })}>{t("ask.assistant.nomodel.link")}</a> : <p className="muted small">{t("ask.assistant.nomodel.admin")}</p>}
    </div>
  );
}

/** A pipeline plan, pending: the step chain with row counts, the basis, the key assumptions (open ones are asked here), what was done and not done. Nothing is saved or run. */
export function PlanCard({ plan, busy, onAnswer, onApply, onRevise }) {
  const t = useT();
  const { draft, answers, scopeLabel } = plan;
  const c = planCard(draft, answers);
  const open = (draft.questions ?? []).filter((q) => !(answers[q.id] ?? []).length);
  const state = !c.canApply && c.blocked === "failed" ? "needs" : "pending";
  const flow = c.flow.length ? c.flow.map((x) => n(x)).join(" → ") : "";
  const rowsLine = flow ? t("ask.assistant.plan.flow", { rows: flow }) : "";
  return (
    <section className="as-card" aria-label={t("ask.assistant.plan.kind")}>
      <header className="as-head">
        <span className="as-kind"><Icon name="pipeline" size={13} />{t("ask.assistant.plan.kind")}</span>
        <span className="as-scope muted">{t("ask.assistant.plan.on", { scope: scopeLabel })}</span>
        <span className={`as-state ${state}`}>{t(`ask.assistant.card.${state}`)}</span>
      </header>
      <dl className="as-rows">
        <Row label={t("ask.assistant.card.result")}>
          {c.steps.length ? (flow ? t("ask.assistant.plan.result", { count: c.steps.length, flow: rowsLine }) : t("ask.assistant.plan.resultNoCounts", { count: c.steps.length })) : t("ask.assistant.plan.blocked.empty")}
          {c.steps.length > 0 && (
            <ol className="as-chain">
              {c.steps.map((s, i) => (
                <li key={s.id}>
                  <span className="as-num">{i + 1}</span>
                  <div>
                    <p><strong>{s.summary}</strong> <span className="muted small">{kindLine(draft.steps[i].step)}</span></p>
                    {s.rowsIn && <p className="muted small">{t("ask.assistant.plan.stepRows", { from: s.rowsIn.map(n).join(" + "), to: s.rowsOut == null ? "?" : n(s.rowsOut) })}{s.calls != null && t("ask.draft.calls", { n: n(s.calls) })}</p>}
                    {s.operators.map((o, k) => <p key={k} className="muted small">{o}</p>)}
                    {s.failures.map((l) => <p key={l} className="warn small">{l}</p>)}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Row>
        {draft.basis && <Row label={t("ask.assistant.card.basis")}><span>{draft.basis}</span> <span className="muted small">{draft.label}</span></Row>}
        <Row label={t("ask.assistant.card.assume")}>
          {c.assumptions.length === 0 && <span className="muted">{t("ask.assistant.card.none")}</span>}
          <ul className="as-assume">
            {c.assumptions.filter((a) => a.state !== "open").map((a, i) => (
              <li key={i}><span className={`as-tag ${a.state}`}>{t(`ask.assistant.assume.${a.state}`)}</span> {a.text}{a.answer && <span className="muted small"> ({t("ask.assistant.assume.answer", { text: a.answer })})</span>}</li>
            ))}
          </ul>
          <QuestionList questions={open} answers={answers} onAnswer={onAnswer} busy={busy} />
        </Row>
        <Row label={t("ask.assistant.card.checked")}>
          <Checked done={c.done} notDone={c.notDone} prefix="plan" steps={plan.spec.steps} />
        </Row>
      </dl>
      <SeesNote sees={draft.sees} />
      <footer className="as-actions">
        <button className="primary" disabled={!c.canApply || busy} onClick={onApply}>{t("ask.assistant.plan.apply")}</button>
        <button className="secondary" disabled={busy} onClick={onRevise}>{t("ask.assistant.plan.revise")}</button>
        <span className="muted small">{c.blocked ? t(`ask.assistant.plan.blocked.${c.blocked}`) : plan.newPipeline ? t("ask.assistant.plan.applyNoteNew") : t("ask.assistant.plan.applyNote")}</span>
      </footer>
    </section>
  );
}

/** A type proposal: each suggested object type with its key, properties and basis, the dropped ones with their reasons, and "Propose these types". */
export function ProposalCard({ proposal, busy, onPropose }) {
  const t = useT();
  const c = proposalCard(proposal.result, proposal.details);
  const done = proposal.proposed;
  return (
    <section className="as-card" aria-label={t("ask.assistant.model.kind")}>
      <header className="as-head">
        <span className="as-kind"><Icon name="cube" size={13} />{t("ask.assistant.model.kind")}</span>
        <span className="as-scope muted">{t("ask.assistant.model.on", { datasets: proposal.datasets.join(t("ask.sep")) })}</span>
        <span className={`as-state ${done ? "proposed" : c.types.length ? "pending" : "needs"}`}>{t(done ? "ask.assistant.card.proposed" : c.types.length ? "ask.assistant.card.pending" : "ask.assistant.card.needs")}</span>
      </header>
      <dl className="as-rows">
        <Row label={t("ask.assistant.card.result")}>
          {c.types.length ? t("ask.assistant.model.result", { count: c.types.length }) : t("ask.assistant.model.none")}
          <ul className="as-types">
            {c.types.map((x) => (
              <li key={x.id}>
                <p className="as-type-head"><strong>{x.name}</strong> <code>{x.id}</code> <a className="small" href={hrefFor({ page: "type", id: x.id, tab: "props" })}>{t("ask.assistant.model.open")}</a></p>
                <p className="small"><span className="muted">{t("ask.assistant.model.dataset")}</span> {x.dataset} <span className="muted as-gap">{t("ask.assistant.model.key")}</span> {x.key.map((k) => <code key={k} className="as-key">{k}</code>)}</p>
                <p className="small as-basis"><span className="muted">{t("ask.assistant.card.basis")}</span> {x.basis || <span className="muted">{t("ask.assistant.model.noBasis")}</span>}</p>
                {x.properties.length > 0 && (
                  <ul className="as-props">
                    {x.properties.map((p) => <li key={p.column}><code>{p.column}</code>{p.name && <span className="muted"> {p.name}</span>}{p.why && <span className="muted small"> · {t("ask.assistant.model.for", { text: p.why })}</span>}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </Row>
        {c.rejected.length > 0 && (
          <Row label={t("ask.assistant.model.rejected", { count: c.rejected.length })}>
            <ul className="as-rejected">{c.rejected.map((r, i) => <li key={i}><strong>{r.name}</strong> <span className="muted">{r.reason}</span></li>)}</ul>
          </Row>
        )}
        <Row label={t("ask.assistant.card.checked")}>
          <Checked done={c.done} notDone={c.notDone} prefix="model" />
        </Row>
      </dl>
      {proposal.error && <p className="error" role="alert">{proposal.error}</p>}
      <footer className="as-actions">
        {done ? (
          <>
            <span className="as-ok"><Icon name="check" size={14} />{t("ask.assistant.model.proposedAll", { count: done })}</span>
            <a className="button secondary" href="#/confirm">{t("ask.assistant.model.queue")}</a>
          </>
        ) : (
          <>
            <button className="primary" disabled={!c.canPropose || busy} onClick={onPropose}>{busy ? t("ask.assistant.model.proposing") : t("ask.assistant.model.propose")}</button>
            <span className="muted small">{t("ask.assistant.model.proposeNote")}</span>
          </>
        )}
      </footer>
    </section>
  );
}
