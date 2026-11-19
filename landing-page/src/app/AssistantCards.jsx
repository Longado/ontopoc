import React, { useEffect, useRef, useState } from "react";
import { QuestionList, SeesNote } from "./AiBox.jsx";
import { actionState, meaningsCard, planCard, proposalCard } from "./assistantModel.js";
import { formatNumber, useT } from "./i18n/index.js";
import { useAuth } from "./Auth.jsx";
import { isGuest } from "./authModel.js";
import { DemoAskNote } from "./DemoAskNote.jsx";
import { failureLines, friendlyError, kindLine } from "./pipelineModel.js";
import { definitionHref } from "./qaModel.js";
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
        <ul className="as-list done">{done.length ? done.map((x) => <li key={x.key}><Icon name="check" size={13} />{x.text ?? t(`ask.assistant.${prefix}.done.${x.key}`, x)}</li>) : <li className="muted">{t("ask.assistant.card.none")}</li>}</ul>
      </div>
      <div>
        <h4>{t("ask.assistant.card.notDone")}</h4>
        <ul className="as-list not">{notDone.length ? notDone.map((x) => <li key={x.key}><i aria-hidden="true" />{x.key === "failed" ? t(`ask.assistant.${prefix}.not.failed`, { text: friendlyError(String(x.text).replace(/^(Check failed|核对没通过)[:：]\s*/, ""), steps) }) : x.text ?? t(`ask.assistant.${prefix}.not.${x.key}`, x)}</li>) : <li className="muted">{t("ask.assistant.card.none")}</li>}</ul>
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
  if (isGuest(useAuth().user)) return <DemoAskNote />;
  return (
    <div className="as-notice" role="status">
      <strong>{t("ask.assistant.nomodel.title")}</strong>
      <p>{t("ask.assistant.nomodel.text")}</p>
      {admin ? <a className="button secondary" href={hrefFor({ page: "settings" })}>{t("ask.assistant.nomodel.link")}</a> : <p className="muted small">{t("ask.assistant.nomodel.admin")}</p>}
    </div>
  );
}

/** A pipeline plan, pending: the step chain with row counts, the basis, the key assumptions (open ones are asked here), what was done and not done. Nothing is saved or run. */
export function PlanCard({ plan, busy, onAnswer, onApply, onRevise, onDiscard, request = "", version = 1 }) {
  const t = useT();
  const [revising, setRevising] = useState(false);
  const [change, setChange] = useState(request);
  const form = useRef(null);
  useEffect(() => { if (revising) form.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }, [revising]);
  const { draft, answers, scopeLabel } = plan;
  const c = planCard(draft, answers);
  const open = (draft.questions ?? []).filter((q) => !(answers[q.id] ?? []).length);
  const act = actionState(c, plan);
  const frozen = plan.supersededBy || plan.discarded || plan.applied;
  const state = plan.supersededBy ? "superseded" : plan.discarded ? "discarded" : plan.applied ? "applied" : !c.canApply && c.blocked === "failed" ? "needs" : "pending";
  const flow = c.flow.length ? c.flow.map((x) => n(x)).join(" → ") : "";
  const rowsLine = flow ? t("ask.assistant.plan.flow", { rows: flow }) : "";
  return (
    <section className={frozen ? "as-card frozen" : "as-card"} aria-label={t("ask.assistant.plan.kind")}>
      <header className="as-head">
        <span className="as-kind"><Icon name="pipeline" size={13} />{t("ask.assistant.plan.kind")}</span>
        {version > 1 && <span className="as-version">{t("ask.assistant.card.version", { n: version })}</span>}
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
                    {failureLines({ failures: s.failures }).map((l) => <p key={l} className="warn small">{l}</p>)}
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
            {c.assumptions.filter((a) => a.state !== "open").map((a, i) => {
              const tag = a.by === "you" ? "answered" : a.state;
              return (
                <li key={i}><span className={`as-tag ${tag}`}>{t(`ask.assistant.assume.${tag}`)}</span> {a.text}{a.answer && <span className="muted small"> ({t("ask.assistant.assume.answer", { text: a.answer })})</span>}{a.definition && <> <a className="small" href={definitionHref(a.definition)}>{t("ask.assistant.assume.definition")}</a></>}</li>
              );
            })}
          </ul>
          <QuestionList questions={open} answers={answers} onAnswer={onAnswer} busy={busy || Boolean(plan.busy) || Boolean(frozen)} />
        </Row>
        <Row label={t("ask.assistant.card.checked")}>
          <Checked done={c.done} notDone={c.notDone} prefix="plan" steps={plan.spec.steps} />
        </Row>
      </dl>
      <SeesNote sees={draft.sees} />
      {plan.supersededBy && <p className="as-note muted small">{t("ask.assistant.plan.supersededBy")}</p>}
      {revising && !plan.supersededBy && (
        <form className="as-revise" ref={form} onSubmit={(e) => { e.preventDefault(); if (change.trim()) { onRevise(change); setRevising(false); } }}>
          <label htmlFor={`revise-${plan.selected}-${version}`}>{t("ask.assistant.plan.reviseTitle")}</label>
          <textarea id={`revise-${plan.selected}-${version}`} rows={2} value={change} onChange={(e) => setChange(e.target.value)} autoFocus />
          <div className="as-revise-actions">
            <button className="primary" type="submit" disabled={!change.trim() || busy}>{t("ask.assistant.plan.reviseSend")}</button>
            <button className="secondary" type="button" onClick={() => setRevising(false)}>{t("ask.assistant.plan.reviseCancel")}</button>
            <span className="muted small">{t("ask.assistant.plan.revises", { n: version })}</span>
          </div>
        </form>
      )}
      <footer className="as-actions">
        <button className="primary" disabled={!act.apply.enabled || busy} onClick={onApply}>{t("ask.assistant.plan.apply")}</button>
        <button className="secondary" disabled={!act.revise || busy} onClick={() => setRevising(!revising)}>{plan.applied ? t("ask.assistant.plan.changeNote") : t("ask.assistant.plan.revise")}</button>
        <button className="secondary" disabled={!act.discard || busy} onClick={onDiscard}>{t("ask.assistant.plan.discard")}</button>
        <span className="muted small">{act.apply.reason ? t(`ask.assistant.plan.blocked.${act.apply.reason}`) : plan.newPipeline ? t("ask.assistant.plan.applyNoteNew") : t("ask.assistant.plan.applyNote")}</span>
      </footer>
    </section>
  );
}

/** A type proposal: each suggested object type with its key, properties and basis, the dropped ones with their reasons, and "Propose these types". */
export function ProposalCard({ proposal, busy, onPropose, onAck }) {
  const t = useT();
  const c = proposalCard(proposal.result, proposal.details, proposal.acked ?? {});
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
                {x.basis && <p className="small as-basis"><span className="muted">{t("ask.assistant.card.basis")}</span> {x.basis}</p>}
                {x.leftOut.length > 0 && <p className="small as-basis"><span className="muted">{t("ask.assistant.model.leftOut", { count: x.leftOut.length })}</span> {x.leftOut.map((k) => <code key={k} className="as-key">{k}</code>)}</p>}
                {x.properties.length > 0 && (
                  <ul className="as-props">
                    {x.properties.map((p) => <li key={p.column}><code>{p.column}</code>{p.name && <span className="muted"> {p.name}</span>}{p.why && <span className="muted small"> · {t("ask.assistant.model.for", { text: p.why })}</span>}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </Row>
        {c.assumptions.length > 0 && (
          <Row label={t("ask.assistant.card.assume")}>
            <ul className="as-assume">
              {c.assumptions.map((a) => (
                <li key={a.id}>
                  <span className={`as-tag ${a.state}`}>{t(`ask.assistant.assume.${a.state}`)}</span> {a.text}{a.definition && <> <a className="small" href={definitionHref(a.definition)}>{t("ask.assistant.assume.definition")}</a></>}
                  {a.state === "open" && !done && <> <button type="button" className="secondary small as-ack" disabled={busy} onClick={() => onAck(a.id)}>{t("ask.assistant.model.ack")}</button></>}
                </li>
              ))}
            </ul>
          </Row>
        )}
        {c.rejected.length > 0 && (
          <Row label={t("ask.assistant.model.rejected", { count: c.rejected.length })}>
            <ul className="as-rejected">{c.rejected.map((r, i) => <li key={i}><strong>{r.name}</strong> <span className="muted">{r.reason}</span></li>)}</ul>
          </Row>
        )}
        <Row label={t("ask.assistant.card.checked")}>
          <Checked done={c.done.filter((x) => !(done && x.key === "kept"))} notDone={c.notDone} prefix="model" />
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
            <span className="muted small">{c.blocked ? t("ask.assistant.model.blocked.open") : t("ask.assistant.model.proposeNote")}</span>
          </>
        )}
      </footer>
    </section>
  );
}

/** A meanings draft for one object type: per code column, each code with its drafted meaning, the flags the code worked out, and a keep/skip toggle; Apply puts
 * the kept meanings forward through the type's own meanings path (a second builder confirms them). Nothing is saved until then. */
export function MeaningsCard({ meanings, busy, onToggle, onApply }) {
  const t = useT();
  const { result, choices = {}, typeLabel } = meanings;
  const c = meaningsCard(result, choices);
  const done = meanings.applied != null;
  const working = busy || Boolean(meanings.busy);
  const drafted = c.columns.some((x) => x.values.some((v) => v.hasDraft));
  return (
    <section className="as-card" aria-label={t("ask.assistant.meanings.kind")}>
      <header className="as-head">
        <span className="as-kind"><Icon name="cube" size={13} />{t("ask.assistant.meanings.kind")}</span>
        <span className="as-scope muted">{t("ask.assistant.meanings.on", { type: typeLabel })}</span>
        <span className={`as-state ${done ? "proposed" : drafted ? "pending" : "needs"}`}>{t(done ? "ask.assistant.card.proposed" : drafted ? "ask.assistant.card.pending" : "ask.assistant.card.needs")}</span>
      </header>
      <dl className="as-rows">
        <Row label={t("ask.assistant.card.result")}>
          {c.columns.length === 0 && <span className="muted">{t("ask.assistant.meanings.none")}</span>}
          {c.columns.map((col) => (
            <div key={col.column} className="as-meaning-col">
              <p className="as-type-head"><strong>{col.column}</strong> <span className="muted small">{t("ask.assistant.meanings.rows", { rows: n(col.rows) })}</span>{col.confirmed && <> <span className="as-tag confirmed">{t("ask.assistant.meanings.confirmed")}</span></>}</p>
              <table className="as-meanings">
                <thead><tr><th>{t("ask.assistant.meanings.code")}</th><th>{t("ask.assistant.meanings.meaning")}</th><th /></tr></thead>
                <tbody>
                  {col.values.map((v) => (
                    <tr key={v.value} className={v.hasDraft && !v.keep ? "skipped" : ""}>
                      <td><code>{v.value}</code> <span className="muted small">{t("ask.assistant.meanings.valueRows", { rows: n(v.rows ?? 0) })}</span></td>
                      <td>
                        {v.hasDraft ? <strong>{v.label}</strong> : v.current ? <span>{v.current}</span> : <span className="faint">{t("ask.assistant.meanings.noMeaning")}</span>}
                        {!v.hasDraft && v.current && <span className="muted small"> {t("ask.assistant.meanings.onFile")}</span>}
                        {v.flags.map((f) => <span key={f} className={`as-tag ${f === "unmeant" ? "open" : ""}`}>{t(`ask.assistant.meanings.flag.${f}`, { current: v.current })}</span>)}
                        {v.hasDraft && v.basis && <p className="muted small">{t("ask.assistant.card.basis")}: {v.basis}</p>}
                      </td>
                      <td>{v.hasDraft && !done && <label className="small"><input type="checkbox" checked={v.keep} disabled={working} aria-label={t("ask.assistant.meanings.keepAria", { column: col.column, value: v.value })} onChange={(e) => onToggle(col.column, v.value, e.target.checked)} /> {t("ask.assistant.meanings.keep")}</label>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {col.gone.length > 0 && <p className="small warn">{t("ask.assistant.meanings.gone", { codes: col.gone.join(t("ask.sep")) })}</p>}
            </div>
          ))}
        </Row>
        {c.assumptions.length > 0 && (
          <Row label={t("ask.assistant.card.assume")}>
            <ul className="as-assume">
              {c.assumptions.map((a) => <li key={a.id}><span className={`as-tag ${a.state}`}>{t(`ask.assistant.assume.${a.state}`)}</span> {a.text}{a.definition && <> <a className="small" href={definitionHref(a.definition)}>{t("ask.assistant.assume.definition")}</a></>}</li>)}
            </ul>
          </Row>
        )}
        {(c.skipped.length > 0 || c.rejected.length > 0) && (
          <Row label={t("ask.assistant.meanings.left")}>
            <ul className="as-rejected">
              {c.skipped.map((s) => <li key={s.column}><strong>{s.column}</strong> <span className="muted">{s.reason}</span></li>)}
              {c.rejected.map((r, i) => <li key={i}><strong>{r.item}</strong> <span className="muted">{r.reason}</span></li>)}
            </ul>
          </Row>
        )}
        <Row label={t("ask.assistant.card.checked")}>
          <Checked done={c.done} notDone={c.notDone.filter((x) => !(done && x.key === "saved"))} prefix="meanings" />
        </Row>
      </dl>
      {meanings.error && <p className="error" role="alert">{meanings.error}</p>}
      <footer className="as-actions">
        {done ? (
          <>
            <span className="as-ok"><Icon name="check" size={14} />{t("ask.assistant.meanings.appliedAll", { count: meanings.applied })}</span>
            <a className="button secondary" href={hrefFor({ page: "type", id: result.type, tab: "props" })}>{t("ask.assistant.model.open")}</a>
          </>
        ) : (
          <>
            <button className="primary" disabled={!c.canApply || working} onClick={onApply}>{working ? t("ask.assistant.meanings.applying") : t("ask.assistant.meanings.apply", { count: c.kept })}</button>
            <span className="muted small">{c.blocked ? t("ask.assistant.meanings.blocked.none") : t("ask.assistant.meanings.applyNote")}</span>
          </>
        )}
      </footer>
    </section>
  );
}
