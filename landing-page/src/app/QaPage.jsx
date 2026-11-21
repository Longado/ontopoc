import React, { useEffect, useRef, useState } from "react";
import { aiDraft, askQuestion, draftMeanings, getAnswer, getAsk, getAssistantTurns, getDatasets, getModelReady, getPipeline, getPipelines, getType, getTypes, keepAssistantTurn, markAssistantTurn, proposeMeanings, runQuery, suggestTypes, updateType } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { AnswerCheck } from "./CheckedNumber.jsx";
import { DemoAskNote } from "./DemoAskNote.jsx";
import { QUICK_START_URL, askOff, holdAsk } from "./demoModel.js";
import { useDemoAsk } from "./useDemoAsk.js";
import { canBuild, isAdmin } from "./authModel.js";
import { allowedMode, commandChoices, datasetSpec, defaultSelected, isNoModel, loadThread, meaningsPayloads, modesFor, nextVersion, parseCommand, privacyKey, proposePayload, saveThread, scopeKind, stashDraft, textOptional } from "./assistantModel.js";
import { MeaningsCard, NoModel, PlanCard, ProposalCard } from "./AssistantCards.jsx";
import { filterByMode, filterModes, pastTurn, railItems, scopeOf } from "./assistantHistoryModel.js";
import { PastTurn, modeLabel } from "./PastTurn.jsx";
import { timeText } from "./format.js";
import { answerView, criteriaLine, dataAsOf, definitionHref, historyView, namedLines, isAnswer, isThenAnswer, paramsIn, queryExample, queryParams, queryRecord, rangeNotes, readText, staleHeading, staleLines, standingText, timeWarning } from "./qaModel.js";
import { groupByDay, isThinking, newTurn, savedTurn, sendsOn, settle, suggestions, threadTitle } from "./chatModel.js";
import { ObjectGraph } from "./ObjectGraph.jsx";
import { State } from "./TypesPage.jsx";
import { formatDate, useT } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { Icon } from "./ui/Icon.jsx";
import { useLoad } from "./useLoad.js";

const MODEL_KINDS = ["model", "pipeline", "meanings"];   // the turn kinds that call the model and answer with a card
const KIND = { type: "ask.kind.type", meaning: "ask.kind.meaning", relation: "ask.kind.relation", view: "ask.kind.view", derived: "ask.kind.derived" };

/** The definitions a refusal names, bottom of the chain first: what it is, where it stands and why, who could confirm it. */
function Named({ list, mayBuild }) {
  const t = useT();
  return (
    <ul className="named">
      {namedLines(list).map((d) => d.plain ? <li key={d.key}><p>{d.text}</p></li> : (
        <li key={d.key}>
          <p>
            <span className="muted">{t(KIND[d.kind])}</span> <a href={d.href}>{d.name}</a> <State item={d} />
          </p>
          <p className="muted">{standingText(d)}</p>
          {d.who_can_confirm?.length > 0 && <p className="muted small">{t("ask.named.confirmers", { names: d.who_can_confirm.join(t("ask.sep")) })}</p>}
        </li>
      ))}
      {mayBuild && list.some((d) => d.id && d.state !== "confirmed") && <li><a href="#/confirm">{t("ask.named.toConfirm")}</a></li>}
    </ul>
  );
}

function Refusal({ record, mayBuild }) {
  const t = useT();
  const r = record.refusal;
  return (
    <div className="refusal-card">
      <h2 className="section"><Icon name="info" size={16} />{t("ask.refusal.title")}</h2>
      {r?.kind === "unsettled" && (
        <>
          <p>{t("ask.refusal.unsettled")}</p>
          <Named list={r.definitions} mayBuild={mayBuild} />
        </>
      )}
      {r?.kind === "not_in_scope" && (
        <>
          {r.left_out?.some((d) => d.kind === "relation" && d.state === "confirmed") && <p>{t("ask.refusal.relationLeftOut")}</p>}
          <p className={r.left_out?.some((d) => d.kind === "relation" && d.state === "confirmed") ? "muted" : undefined}>{record.reason}</p>
          <p className="muted">{t("ask.refusal.inScope", { list: r.in_scope.length ? r.in_scope.join(t("ask.sep")) : t("ask.refusal.noTypes") })}</p>
          {r.left_out?.length > 0 && (
            <>
              <p className="muted refusal-sub">{t("ask.refusal.leftOut")}</p>
              <Named list={r.left_out} mayBuild={mayBuild} />
            </>
          )}
        </>
      )}
      {r?.kind === "definition_unmet" && (
        <>
          <p>{record.reason}</p>
          <ul className="named">
            {r.definitions.map((u, i) => <li key={i}><p>{u.definition}</p><p className="muted">{u.why}</p></li>)}
          </ul>
        </>
      )}
      {!r && <p>{record.reason}</p>}
    </div>
  );
}

export function Answer({ record }) {
  const t = useT();
  const view = answerView(record);
  const notes = staleLines(record);
  const then = isThenAnswer(record);
  return (
    <div className={then ? "answer then" : "answer"}>
      {then && <p className="warn">{staleHeading(record)}</p>}
      <div className="big">{then && <span className="small muted">{t("ask.answer.then")} </span>}{view.big}</div>
      {view.note && <p className="muted">{view.note}</p>}
      {view.graph && <ObjectGraph graph={view.graph} />}
      {view.table && (
        <div className="table-wrap">
          <table>
            <thead><tr>{view.table.head.map((h, i) => <th key={h} className={i ? "num" : ""}>{h}</th>)}</tr></thead>
            <tbody>{view.table.rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} className={j ? "num" : ""}>{v}</td>)}</tr>)}</tbody>
          </table>
          {view.table.total > view.table.rows.length && <p className="muted small table-note">{t("ask.answer.shown", { shown: view.table.rows.length, total: view.table.total })}</p>}
        </div>
      )}
      {rangeNotes(record).map((n) => <p className="warn" key={n}>{n}</p>)}
      {notes.length > 0 && <p className="warn">{then ? notes.join(t("ask.stale.sep")) : t("ask.stale.withHeading", { heading: staleHeading(record), notes: notes.join(t("ask.stale.sep")) })}</p>}
    </div>
  );
}

/** How the question was read, what it stood on, what it read, and the steps: under every answer and every refusal. */
export function Basis({ record, onEdit }) {
  const t = useT();
  const read = readText(record.datasets);
  return (
    <>
      <dl className="defs">
        {record.query_text && (
          <>
            <dt>{t("ask.basis.query")}</dt>
            <dd>
              <pre className="query-text">{record.query_text}</pre>
              {onEdit && <button className="plain" onClick={() => onEdit(record.query_text)}>{t("ask.basis.edit")}</button>}
            </dd>
          </>
        )}
        {record.reasoning && (
          <>
            <dt>{t("ask.basis.understood")}</dt>
            <dd>
              {record.reasoning}
              {record.path && <span className="muted"> {record.path}</span>}
              {record.understood?.map((u) => <span className="muted small block" key={u.definition}>{t("ask.basis.understoodLine", { definition: u.definition, how: u.how })}</span>)}
            </dd>
          </>
        )}
        {record.definitions.length > 0 && (
          <>
            <dt>{t("ask.basis.definitions")}</dt>
            <dd>
              {record.definitions.map((d) => (
                <span className="block" key={d.id}>
                  {t(KIND[d.kind])} <a href={definitionHref(d.id, d.type)}>{d.name}</a> <span className="muted">{d.confirmed_by ? t("ask.basis.confirmedBy", { by: d.confirmed_by, when: timeText(d.confirmed_at) }) : ""}</span>
                  {d.says && <span className="muted small block">{d.says}</span>}
                </span>
              ))}
            </dd>
          </>
        )}
        {read.length > 0 && <><dt>{t("ask.basis.read")}</dt><dd>{read.map((line) => <span className="block" key={line}>{line}</span>)}</dd></>}
        {record.limited_by_rule?.length > 0 && (
          <>
            <dt>{t("ask.basis.limited")}</dt>
            <dd>{record.limited_by_rule.map((l) => <span className="block" key={l.type}>{t("ask.basis.limitedLine", { name: l.name, rule: l.rule })}</span>)}</dd>
          </>
        )}
      </dl>
      {record.steps.length > 0 && (
        <details className="trace">
          <summary>{t("ask.basis.steps")}</summary>
          <ol>
            {record.steps.map((s, i) => (
              <li key={i} className={s.failed ? "warn" : ""}>
                <strong>{s.name}</strong> {s.text}
                {s.query && <code>{JSON.stringify(s.query)}</code>}
              </li>
            ))}
          </ol>
        </details>
      )}
    </>
  );
}

/** One answer that cannot be drawn stays one card that says so, with the service's own sentence: the rest of the page and the app go on. */
class CardBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return <section className="qa-card"><p className="warn">{this.props.fallback}</p>{this.props.reason && <p className="muted">{this.props.reason}</p>}</section>;
  }
}

function AnswerCard(props) {
  const t = useT();
  return <CardBoundary fallback={t("ask.card.broken")} reason={props.record?.reason}><AnswerCardBody {...props} /></CardBoundary>;
}

/** An answer as a message: the figure or table first, the time-word warning when the question's time was not used, one caliber line, and the technical basis folded. */
function AnswerCardBody({ record, mayBuild, onEdit }) {
  const t = useT();
  const warning = isAnswer(record) ? timeWarning(record) : null;
  const line = isAnswer(record) ? criteriaLine(record, dataAsOf(record, timeText)) : "";
  return (
    <section className="qa-card">
      {record.withheld ? <p className="warn">{record.reason}</p> : (
        <>
          {isAnswer(record) ? <Answer record={record} /> : <Refusal record={record} mayBuild={mayBuild} />}
          {warning && <p className="time-warn" role="alert">{warning}</p>}
          {line && <p className="criteria">{line}</p>}
          <details className="basis">
            <summary>{t("ask.card.basis")}</summary>
            <Basis record={record} onEdit={onEdit} />
          </details>
          {record.asked_at && <p className="muted small qa-when">{timeText(record.asked_at)}</p>}
          {mayBuild && <AnswerCheck record={record} />}
        </>
      )}
    </section>
  );
}

/** The person's side of a turn: a plain bubble, the query in monospace. */
function UserBubble({ text, query, mode }) {
  const t = useT();
  const tag = query ? t("ask.chat.queryTurn") : MODEL_KINDS.includes(mode) ? t(`ask.assistant.turn.${mode}`) : "";
  return (
    <div className="msg msg-user">
      <div className={query ? "bubble bubble-query" : "bubble"}>
        {tag && <span className="bubble-tag">{tag}</span>}
        {query ? <pre>{text}</pre> : text}
      </div>
    </div>
  );
}

/** The assistant's side of a turn: the OntoPoc mark, then what it says. */
function AssistantMsg({ children, label }) {
  const t = useT();
  return (
    <div className="msg msg-bot">
      <span className="bot-mark" aria-hidden="true" />
      <div className="bot-body" aria-label={label ?? t("ask.chat.assistant")}>{children}</div>
    </div>
  );
}

function Thinking({ query, mode }) {
  const t = useT();
  return (
    <AssistantMsg>
      <div className="thinking" role="status">
        <span className="typing" aria-hidden="true"><i /><i /><i /></span>
        <span>{t("ask.chat.thinking")}</span>
      </div>
      <p className="muted small">{query ? t("ask.query.busy") : MODEL_KINDS.includes(mode) ? t(`ask.assistant.busy.${mode}`) : t("ask.input.busy")}</p>
    </AssistantMsg>
  );
}

function FollowUps({ list, onAsk, disabled }) {
  const t = useT();
  if (!list.length) return null;
  return (
    <div className="followups">
      <span className="muted small">{t("ask.chat.followUp")}</span>
      <div className="chips">{list.map((q) => <button key={q} className="chip" disabled={disabled} onClick={() => onAsk(q)}>{q}</button>)}</div>
    </div>
  );
}

/** A saved answer opened on its own: its question as the person's message, then the answer card. */
function SavedTurn({ turn, mayBuild, onEdit, followUps, onAsk, last, onLoaded }) {
  const t = useT();
  const [state] = useLoad(() => getAnswer(turn.savedId), [turn.savedId]);
  const r = state.data;
  useEffect(() => {
    if (state.status !== "loading") onLoaded(turn.id, state.status === "error" ? { status: "error", error: state.error } : { status: "done", record: state.data });
  }, [state.status]);
  if (state.status === "error") return <AssistantMsg><p className="error">{state.missing ? t("ask.saved.missing") : state.error}</p></AssistantMsg>;
  if (!r) return <Thinking />;
  return (
    <>
      <UserBubble text={r.question} />
      <AssistantMsg><AnswerCard record={r} mayBuild={mayBuild} onEdit={onEdit} /><FollowUps list={last && !isAnswer(r) ? followUps : []} onAsk={onAsk} /></AssistantMsg>
    </>
  );
}

function TurnView({ turn, mayBuild, admin, onEdit, followUps, onAsk, busy, last, onLoaded, cards }) {
  if (turn.kind === "past") return <PastTurn turnId={turn.turnId} onDraftAgain={cards.again} onDeleted={cards.deleted} />;
  if (turn.kind === "saved") return <SavedTurn turn={turn} mayBuild={mayBuild} onEdit={onEdit} followUps={followUps} onAsk={onAsk} last={last} onLoaded={onLoaded} />;
  if (MODEL_KINDS.includes(turn.kind)) {
    return (
      <>
        <UserBubble text={turn.text} mode={turn.kind} />
        {turn.status === "thinking" && <Thinking mode={turn.kind} />}
        {turn.status === "error" && <AssistantMsg>{turn.noModel ? <NoModel admin={admin} /> : <p className="error" role="alert">{turn.error}</p>}</AssistantMsg>}
        {turn.status === "done" && (
          <AssistantMsg>
            {turn.kind === "pipeline" ? <PlanCard plan={turn.plan} busy={busy} onAnswer={(id, values) => cards.answer(turn, id, values)} onApply={() => cards.apply(turn)} onRevise={(request) => cards.revise(turn, request)} onDiscard={() => cards.discard(turn)} request={turn.text} version={turn.version ?? 1} />
              : turn.kind === "meanings" ? <MeaningsCard meanings={turn.meanings} busy={busy} onToggle={(column, value, keep) => cards.toggleMeaning(turn, column, value, keep)} onApply={() => cards.applyMeanings(turn)} />
              : <ProposalCard proposal={turn.proposal} busy={turn.proposal.busy} onPropose={() => cards.propose(turn)} onAck={(id) => cards.ack(turn, id)} />}
          </AssistantMsg>
        )}
      </>
    );
  }
  const r = turn.record;
  const unanswered = r && (!isAnswer(r) || r.status === "no_data");
  return (
    <>
      <UserBubble text={turn.text} query={turn.kind === "query"} />
      {turn.status === "thinking" && <Thinking query={turn.kind === "query"} />}
      {turn.status === "error" && <AssistantMsg><p className="error" role="alert">{turn.error}</p></AssistantMsg>}
      {turn.status === "done" && r && (
        <AssistantMsg>
          <AnswerCard record={r} mayBuild={mayBuild} onEdit={onEdit} />
          {last && unanswered && turn.kind === "ask" && <FollowUps list={followUps} onAsk={onAsk} disabled={busy} />}
        </AssistantMsg>
      )}
    </>
  );
}

/** A scope chip that opens a small popover: shared by the three kinds of scope. */
function ChipPop({ label, aria, children }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => !wrap.current?.contains(e.target) && setOpen(false);   // a click anywhere else closes it
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  return (
    <span className="scope-chip-wrap" ref={wrap}>
      <button type="button" className="scope-chip" aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen(!open)} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
        {label}
        <Icon name="chevron-down" size={12} />
      </button>
      {open && <div className="scope-pop" role="dialog" aria-label={aria}>{children(() => setOpen(false))}</div>}
    </span>
  );
}

/** Model mode: the datasets the model may read about. */
function DatasetsChip({ datasets, chosen, setChosen }) {
  const t = useT();
  const toggle = (name, on) => setChosen(on ? [...chosen, name] : chosen.filter((x) => x !== name));
  return (
    <ChipPop label={chosen.length ? t("ask.assistant.scope.datasets", { count: chosen.length }) : t("ask.assistant.scope.datasets.none")} aria={t("ask.assistant.scope.datasets.title")}>
      {() => (
        <>
          <p className="muted small">{t("ask.assistant.scope.datasets.title")}</p>
          {datasets.length === 0 && <p>{t("ask.assistant.scope.datasets.empty")}</p>}
          <div className="as-pick">
            {datasets.map((d) => <label key={d.name}><input type="checkbox" checked={chosen.includes(d.name)} onChange={(e) => toggle(d.name, e.target.checked)} />{d.name}</label>)}
          </div>
        </>
      )}
    </ChipPop>
  );
}

/** Pipeline mode: one pipeline to draft over, or one dataset to start a new pipeline from. */
function TargetChip({ pipelines, datasets, target, setTarget }) {
  const t = useT();
  const label = !target ? t("ask.assistant.scope.target.none") : t(target.kind === "pipeline" ? "ask.assistant.scope.target.pipeline" : "ask.assistant.scope.target.dataset", { name: target.name });
  return (
    <ChipPop label={label} aria={t("ask.assistant.scope.target.none")}>
      {(close) => (
        <>
          {pipelines.length === 0 && datasets.length === 0 && <p>{t("ask.assistant.scope.target.empty")}</p>}
          {pipelines.length > 0 && <p className="muted small">{t("ask.assistant.scope.target.pipelines")}</p>}
          <div className="as-pick">
            {pipelines.map((p) => <button type="button" key={p.id} className={target?.kind === "pipeline" && target.name === p.id ? "on" : ""} onClick={() => { setTarget({ kind: "pipeline", name: p.id, label: p.name }); close(); }}>{p.name}</button>)}
          </div>
          {datasets.length > 0 && <p className="muted small scope-sub">{t("ask.assistant.scope.target.datasets")}</p>}
          <div className="as-pick">
            {datasets.map((d) => <button type="button" key={d.name} className={target?.kind === "dataset" && target.name === d.name ? "on" : ""} onClick={() => { setTarget({ kind: "dataset", name: d.name, label: d.name }); close(); }}>{d.name}</button>)}
          </div>
        </>
      )}
    </ChipPop>
  );
}

/** Meanings mode: the one object type whose code meanings are drafted (a type this person may open; the service refuses one with properties kept from them). */
function TypeChip({ types, type, setType }) {
  const t = useT();
  return (
    <ChipPop label={type ? t("ask.assistant.scope.type", { name: type.label }) : t("ask.assistant.scope.type.none")} aria={t("ask.assistant.scope.type.none")}>
      {(close) => (
        <>
          {types.length === 0 && <p>{t("ask.assistant.scope.type.empty")}</p>}
          <div className="as-pick">
            {types.map((x) => <button type="button" key={x.id} className={type?.id === x.id ? "on" : ""} onClick={() => { setType({ id: x.id, label: x.name }); close(); }}>{x.name}</button>)}
          </div>
        </>
      )}
    </ChipPop>
  );
}

/** What can be asked about: a chip in the composer that opens the list of types in scope, the views, and what is left out. */
function ScopeChip({ scope }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  if (!scope) return null;
  return (
    <span className="scope-chip-wrap">
      <button type="button" className="scope-chip" aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen(!open)} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
        {t("ask.chat.scope", { count: scope.types.length })}
        <Icon name="chevron-down" size={12} />
      </button>
      {open && (
        <div className="scope-pop" role="dialog" aria-label={t("ask.chat.scope.aria")}>
          <p>{scope.types.length ? scope.types.map((type) => type.name).join(t("ask.sep")) : t("ask.scope.empty")}</p>
          {scope.views?.length > 0 && <p className="muted">{t("ask.scope.views", { names: scope.views.map((v) => v.name).join(t("ask.sep")) })}</p>}
          {scope.left_out.length > 0 && (
            <>
              <p className="muted scope-sub">{t("ask.scope.leftOut")}</p>
              <ul className="named">
                {scope.left_out.map((d) => <li key={d.id}><a href={definitionHref(d.id, d.type)}>{d.name}</a> <State item={d} /></li>)}
              </ul>
            </>
          )}
        </div>
      )}
    </span>
  );
}

/** The sticky composer: a growing textarea (Enter sends, Shift+Enter breaks the line), the mode chips (a viewer has Ask only), the scope chip of the mode,
 * and the privacy line of the mode. "/model", "/pipeline", "/query" and "/ask" switch the mode. */
function Composer({ scope, mayBuild, mode, setMode, text, setText, query, setQuery, busy, onSend, onRun, scopes }) {
  const t = useT();
  const box = useRef(null);
  const [values, setValues] = useState({});
  const isQuery = mode === "query";
  const value = isQuery ? query : text;
  const names = isQuery ? paramsIn(query) : [];
  const typed = isQuery ? query : text;
  const choices = commandChoices(typed, mayBuild);
  const modes = modesFor(mayBuild);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value, mode]);
  useEffect(() => {
    if (!busy) box.current?.focus({ preventScroll: true });
  }, [busy, mode]);
  const switchTo = (next, rest = "") => {
    setMode(next);
    if (next === "query") { setQuery(rest); setText(""); } else { setText(rest); }
  };
  const change = (v) => {
    const c = /^\s*\/[a-z]+\s/i.test(v) ? parseCommand(v, mayBuild) : null;   // "/model " with the space: the command is complete
    if (c) switchTo(c.mode, c.text);
    else if (isQuery) setQuery(v);
    else setText(v);
  };
  const submit = (e) => {
    e?.preventDefault();
    const c = parseCommand(value, mayBuild);
    if (c) return switchTo(c.mode, c.text);   // "/model" alone only switches
    if (!value.trim() && !textOptional(mode)) return;
    if (busy) return;
    if (isQuery) onRun(query, queryParams(query, values));
    else onSend(mode, text);
  };
  const empty = textOptional(mode) ? false : !value.trim();
  return (
    <form className="composer" onSubmit={submit}>
      {names.length > 0 && (
        <div className="composer-params" role="group" aria-label={t("ask.query.params")}>
          {names.map((n) => (
            <label key={n} className="field">
              <span className="caption">${n}</span>
              <input type="text" aria-label={t("ask.query.param", { name: n })} value={values[n] ?? ""} disabled={busy} onChange={(e) => setValues({ ...values, [n]: e.target.value })} />
            </label>
          ))}
        </div>
      )}
      {choices.length > 0 && (
        <div className="as-commands" role="listbox" aria-label={t("ask.assistant.commands")}>
          {choices.map((m) => <button type="button" role="option" key={m} onClick={() => switchTo(m)}><code>/{m}</code> <span className="muted">{t(`ask.assistant.mode.${m}.hint`)}</span></button>)}
        </div>
      )}
      <textarea
        ref={box}
        className={isQuery ? "composer-input mono" : "composer-input"}
        aria-label={isQuery ? t("ask.query.aria") : t("ask.input.aria")}
        rows={isQuery ? 3 : 1}
        value={value}
        maxLength={isQuery ? undefined : 300}
        spellCheck={false}
        placeholder={isQuery ? queryExample(scope) || t("ask.chat.composer.queryPlaceholder") : mayBuild ? t(`ask.assistant.placeholder.${mode}`) : t("ask.chat.composer.placeholder")}
        disabled={busy}
        onChange={(e) => change(e.target.value)}
        onKeyDown={(e) => {
          if (sendsOn({ key: e.key, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, isComposing: e.nativeEvent.isComposing, keyCode: e.keyCode }, mode)) submit(e);
        }}
      />
      <div className="composer-bar">
        <div className="composer-tools">
          {modes.length > 1 && (
            <div className="mode-chips" role="group" aria-label={t("ask.assistant.mode.aria")}>
              {modes.map((m) => <button key={m} type="button" className={m === mode ? "mode on" : "mode"} aria-pressed={m === mode} title={t(`ask.assistant.mode.${m}.hint`)} onClick={() => switchTo(m, m === "query" ? query : text)}>{t(`ask.assistant.mode.${m}`)}</button>)}
            </div>
          )}
          {scopeKind(mode) === "types" && <ScopeChip scope={scope} />}
          {scopeKind(mode) === "datasets" && <DatasetsChip datasets={scopes.datasets} chosen={scopes.chosen} setChosen={scopes.setChosen} />}
          {scopeKind(mode) === "target" && <TargetChip pipelines={scopes.pipelines} datasets={scopes.datasets} target={scopes.target} setTarget={scopes.setTarget} />}
          {scopeKind(mode) === "type" && <TypeChip types={scopes.types} type={scopes.type} setType={scopes.setType} />}
        </div>
        {isQuery && <span className="composer-hint muted small">{t("ask.chat.composer.hintQuery")}</span>}
        <button className="primary send" type="submit" disabled={busy || empty} aria-label={isQuery ? t("ask.chat.composer.run") : t("ask.chat.composer.send")}>
          <Icon name={isQuery ? "play" : "send"} size={16} />
        </button>
      </div>
    </form>
  );
}

/** The history rail: New chat, a filter by mode, then every turn (saved Ask questions and the builder modes) grouped by the day, each with a small mode chip. */
function Rail({ scope, turns, activeId, activeTurn, onNew, onPick, onOpenTurn }) {
  const t = useT();
  const [only, setOnly] = useState("");
  const items = railItems(scope?.history ?? [], turns ?? []);
  const modes = filterModes(items);
  const groups = groupByDay(filterByMode(items, modes.includes(only) ? only : ""));
  const label = (g) => (g.key === "today" ? t("ask.chat.today") : g.key === "yesterday" ? t("ask.chat.yesterday") : g.key === "undated" ? t("ask.chat.undated") : formatDate(g.when));
  return (
    <aside className="chat-rail" aria-label={t("ask.history.aria")}>
      <button className="chat-new" onClick={onNew}><Icon name="plus" size={14} /> {t("ask.chat.new")}</button>
      {modes.length > 0 && (
        <div className="rail-filter mode-chips" role="group" aria-label={t("ask.rail.filter")}>
          {["", ...modes].map((m) => <button key={m || "all"} type="button" className={m === only ? "mode on" : "mode"} aria-pressed={m === only} onClick={() => setOnly(m)}>{m ? modeLabel(t, m) : t("ask.rail.all")}</button>)}
        </div>
      )}
      <div className="rail-scroll">
        {scope && items.length === 0 && <p className="muted small rail-empty">{t("ask.history.empty")}</p>}
        {items.length > 0 && groups.length === 0 && <p className="muted small rail-empty">{t("ask.rail.none")}</p>}
        {groups.map((g) => (
          <section key={g.key} className="rail-group">
            <h2 className="history-title">{label(g)}</h2>
            <ul className="history-list">
              {g.items.map((h) => {
                const v = h.turn ? { question: h.question, meta: timeText(h.asked_at) } : historyView(h, timeText(h.asked_at));
                const active = h.turn ? h.id === activeTurn : h.id === activeId;
                const chip = modes.length > 0 && <span className={`rail-mode m-${h.mode}`}>{modeLabel(t, h.mode)}</span>;
                return (
                  <li key={h.key}>
                    {h.turn ? (
                      <a href="#/qa" title={v.meta} onClick={(e) => { e.preventDefault(); onOpenTurn(h.id); }} aria-current={active ? "page" : undefined} className={active ? "active" : ""}>
                        {chip}<span className="hq">{v.question}</span>
                      </a>
                    ) : (
                      <a href={`#/qa/${h.id}`} title={v.meta} onClick={onPick} aria-current={active ? "page" : undefined} className={active ? "active" : ""}>
                        {chip}<span className="hq">{v.question}</span>
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </aside>
  );
}

export function QaPage({ route }) {
  const t = useT();
  const me = useAuth().user;
  const mayBuild = canBuild(me);
  const demoAsk = useDemoAsk();
  const noAsk = askOff(me, demoAsk);
  const who = me?.username ?? "";
  const [info, reload] = useLoad(getAsk, []);
  const [text, setText] = useState("");
  const [mode, setMode] = useState("ask");
  const [query, setQuery] = useState("");
  const [turns, setTurns] = useState(() => { const kept = loadThread(window.sessionStorage, who); return route.id == null || kept.some((x) => x.record?.id === route.id) ? kept : []; });
  const [rail, setRail] = useState(false);
  const admin = isAdmin(useAuth().user);
  const [datasets] = useLoad(() => (mayBuild ? getDatasets() : Promise.resolve([])), [mayBuild]);
  const [pipelines] = useLoad(() => (mayBuild ? getPipelines() : Promise.resolve([])), [mayBuild]);
  const [chosen, setChosen] = useState([]);   // Model mode: the datasets the model may read about
  const [target, setTarget] = useState(null);   // Pipeline mode: {kind: "pipeline" | "dataset", name, label}
  const [types] = useLoad(() => (mayBuild ? getTypes() : Promise.resolve([])), [mayBuild]);
  const [typeScope, setTypeScope] = useState(null);   // Meanings mode: {id, label}, the object type whose code meanings are drafted
  const [past, reloadPast] = useLoad(() => (mayBuild ? getAssistantTurns() : Promise.resolve({ turns: [] })), [mayBuild]);   // the builder-mode turns kept for this person
  const scope = info.data;
  const turnsRef = useRef(turns);
  turnsRef.current = turns;
  const own = useRef(new Set(turns.map((x) => x.record?.id).filter((x) => x != null)));   // saved ids this session's thread already holds: opening one of them must not replace the thread
  const thread = useRef(null);
  const busy = isThinking(turns);
  const queryMode = allowedMode(mode, mayBuild);

  const add = (turn) => setTurns((ts) => [...ts, turn]);
  const finish = (turn, patch) => setTurns((ts) => settle(ts, turn.id, patch));

  const send = async (question) => {
    const q = String(question ?? "").trim();
    if (!q || isThinking(turnsRef.current)) return;
    const turn = newTurn("ask", q);
    add(turn);
    setText("");
    setMode("ask");
    try {
      const saved = await askQuestion(q);
      own.current.add(saved.id);
      finish(turn, { status: "done", record: saved });
      reload();
      if (turnsRef.current.some((x) => x.id === turn.id)) window.location.hash = `#/qa/${saved.id}`;
    } catch (err) {
      finish(turn, { status: "error", error: err.message });
    }
  };
  /** Keeps a finished builder-mode turn in this person's history (the rail). Failing to keep one never gets in the way of the card. */
  const keep = async (turn, mode, message, scopeKept, card) => {
    try {
      const { id } = await keepAssistantTurn({ mode, message, scope: scopeKept, card });
      setTurns((ts) => settle(ts, turn.id, { histId: id }));
      reloadPast();
    } catch {
      // the history is a convenience
    }
  };
  /** What happened to the card next (applied, saved as <name>, not applied), written against the turn kept for it. */
  const mark = (turn, state, name) => {
    if (turn.histId) markAssistantTurn(turn.histId, { state, ...(name ? { name } : {}) }).then(reloadPast, () => {});
  };
  /** A past builder-mode turn opens in place, read-only. */
  const openTurn = (id) => {
    setTurns([pastTurn(id)]);
    setRail(false);
    if (route.id != null) window.location.hash = "#/qa";
  };
  /** "Draft again": the composer gets the same mode, scope and message back. Nothing is run and nothing is applied. */
  const again = (d) => {
    setMode(d.mode);
    if (d.mode === "query") setQuery(d.text); else setText(d.text);
    if (d.mode === "model") setChosen(d.datasets);
    if (d.mode === "pipeline" && d.target) setTarget(d.target);
    if (d.mode === "meanings" && d.types?.[0]) {
      const found = (types.data ?? []).find((x) => x.id === d.types[0]);
      setTypeScope({ id: d.types[0], label: found?.name ?? d.types[0] });
    }
  };
  /** The three model-backed modes over their existing endpoints. Nothing is saved or run by the assistant itself: a card is pending until the person acts on it. */
  const sendIn = (inMode, raw) => {
    if (inMode === "ask") return send(raw);
    if (isThinking(turnsRef.current)) return;
    const question = String(raw ?? "").trim();
    const noModel = (turn) => finish(turn, { status: "error", noModel: true });
    if (inMode === "model") {
      if (!chosen.length) { add({ ...newTurn("model", question || chosen.join(", ")), status: "error", error: t("ask.assistant.error.pickDatasets") }); return; }
      const turn = newTurn("model", question || chosen.join(t("ask.sep")));
      add(turn);
      setText("");
      (async () => {
        try {
          if (!(await getModelReady())) return noModel(turn);
          const result = await suggestTypes(chosen, question);
          const details = await Promise.all(result.proposed.map((p) => getType(p.id).catch(() => null)));
          finish(turn, { status: "done", proposal: { result, details, datasets: chosen, proposed: 0, busy: false, error: "" } });
          keep(turn, "model", question, scopeOf("model", { chosen }), result);
        } catch (err) {
          if (isNoModel(err.message)) noModel(turn); else finish(turn, { status: "error", error: err.message });
        }
      })();
      return;
    }
    if (inMode === "meanings") {
      if (!typeScope) { add({ ...newTurn("meanings", question), status: "error", error: t("ask.assistant.error.pickType") }); return; }
      const turn = newTurn("meanings", question || typeScope.label);
      add(turn);
      setText("");
      (async () => {
        try {
          if (!(await getModelReady())) return noModel(turn);
          const result = await draftMeanings(typeScope.id, question);
          finish(turn, { status: "done", meanings: { result, typeLabel: typeScope.label, choices: {}, applied: null, busy: false, error: "" } });
          keep(turn, "meanings", question || typeScope.label, scopeOf("meanings", { type: typeScope }), result);
        } catch (err) {
          if (isNoModel(err.message)) noModel(turn); else finish(turn, { status: "error", error: err.message });
        }
      })();
      return;
    }
    if (!target) { add({ ...newTurn("pipeline", question), status: "error", error: t("ask.assistant.error.pickTarget") }); return; }
    setText("");
    draftPlan(question, target);
  };
  /** One pipeline draft over `tgt`. `revises` is the turn whose card this one replaces: the old card is kept and frozen, the new one is its next version. */
  const draftPlan = (question, tgt, revises) => {
    const turn = { ...newTurn("pipeline", question), version: nextVersion(turnsRef.current, revises), ...(revises ? { revises } : {}) };
    add(turn);
    (async () => {
      try {
        if (!(await getModelReady())) return finish(turn, { status: "error", noModel: true });
        const spec = tgt.kind === "pipeline" ? (await getPipeline(tgt.name)).spec : datasetSpec(tgt.name);
        const selected = tgt.kind === "pipeline" ? defaultSelected(spec) : "in1";
        if (!selected) throw new Error(t("ask.assistant.error.pickTarget"));
        const draft = await aiDraft(tgt.kind === "pipeline" ? tgt.name : undefined, spec, [selected], question);
        finish(turn, { status: "done", plan: { draft, answers: {}, spec, selected, target: tgt, scopeLabel: tgt.label, newPipeline: tgt.kind === "dataset", busy: false } });
        keep(turn, "pipeline", question, scopeOf("pipeline", { target: tgt }), draft);
        if (revises) setTurns((ts) => ts.map((x) => (x.id === revises ? { ...x, plan: { ...x.plan, supersededBy: turn.id } } : x)));   // only once the new version exists
      } catch (err) {
        if (isNoModel(err.message)) finish(turn, { status: "error", noModel: true }); else finish(turn, { status: "error", error: err.message });
      }
    })();
  };
  const patchPlan = (turn, patch) => setTurns((ts) => ts.map((x) => (x.id === turn.id ? { ...x, plan: { ...x.plan, ...patch } } : x)));
  const patchProposal = (turn, patch) => setTurns((ts) => ts.map((x) => (x.id === turn.id ? { ...x, proposal: { ...x.proposal, ...patch } } : x)));
  const patchMeanings = (turn, patch) => setTurns((ts) => ts.map((x) => (x.id === turn.id ? { ...x, meanings: { ...x.meanings, ...patch } } : x)));
  const cards = {
    // answering a question re-checks the draft with the person's own words; the service calls no model for it
    answer: async (turn, id, values) => {
      const plan = turn.plan;
      const answers = { ...plan.answers, [id]: values };
      patchPlan(turn, { answers, busy: true });
      try {
        const draft = await aiDraft(plan.target.kind === "pipeline" ? plan.target.name : undefined, plan.spec, [plan.selected], turn.text, { raw: plan.draft.raw, answers });
        patchPlan(turn, { draft, busy: false });
      } catch (err) {
        patchPlan(turn, { busy: false, answers: plan.answers });
      }
    },
    // Apply: the steps wait for the editor, which applies them the way its own AI panel does; nothing is saved
    apply: (turn) => {
      const plan = turn.plan;
      const name = plan.target.kind === "pipeline" ? plan.target.name : `new:${plan.target.name}`;
      stashDraft(window.sessionStorage, name, plan.draft.steps, plan.draft.draft_receipt, turn.histId);
      patchPlan(turn, { applied: true, appliedAt: new Date().toISOString() });
      mark(turn, "applied", plan.target.kind === "pipeline" ? plan.target.name : "");
      window.location.hash = plan.target.kind === "pipeline" ? hrefFor({ page: "pipeline", name: plan.target.name, view: "edit" }) : hrefFor({ page: "pipelinenew", dataset: plan.target.name });
    },
    // Revise: the changed request is a new turn with a new version of the card; this one is kept and frozen
    revise: (turn, request) => {
      if (isThinking(turnsRef.current) || !String(request ?? "").trim()) return;
      draftPlan(String(request).trim(), turn.plan.target, turn.id);
    },
    discard: (turn) => { patchPlan(turn, { discarded: true }); mark(turn, "not_applied"); },
    again,
    deleted: () => { setTurns([]); reloadPast(); },
    // Meanings: keep/skip one drafted code; Apply sends the kept ones through the type's own meanings path, one column at a time (a second builder confirms them)
    toggleMeaning: (turn, column, value, keep) => patchMeanings(turn, { choices: { ...turn.meanings.choices, [`${column}|${value}`]: keep } }),
    applyMeanings: async (turn) => {
      patchMeanings(turn, { busy: true, error: "" });
      let count = 0;
      try {
        for (const payload of meaningsPayloads(turn.meanings.result, turn.meanings.choices)) {
          // meanings are only proposed here; a second builder confirms them in the review queue, so no "drafted" marker is written
          await proposeMeanings(payload.id, payload.column, payload.values);
          count += payload.values.length;
        }
        patchMeanings(turn, { busy: false, applied: count });
        if (count) mark(turn, "applied", turn.meanings.result?.type ?? "");
        reload();
      } catch (err) {
        patchMeanings(turn, { busy: false, error: err.message });
        if (count) mark(turn, "applied", turn.meanings.result?.type ?? "");   // the columns before the one that failed were put forward
      }
    },
    // an open assumption on a type proposal is acknowledged by the person; the card re-checks by code, no model
    ack: (turn, id) => patchProposal(turn, { acked: { ...(turn.proposal.acked ?? {}), [id]: true } }),
    // Propose: the model drafts become this person's proposals through the normal update path; a second person confirms in the review queue
    propose: async (turn) => {
      patchProposal(turn, { busy: true, error: "" });
      let count = 0;
      try {
        for (const ty of turn.proposal.details.filter(Boolean)) {
          const payload = proposePayload({ ...ty, receipt: (turn.proposal.result?.proposed ?? []).find((p) => p.id === ty.id)?.draft_receipt });
          if (!payload) continue;
          await updateType(payload);
          count += 1;
        }
        patchProposal(turn, { busy: false, proposed: count });
        reload();
      } catch (err) {
        patchProposal(turn, { busy: false, proposed: count, error: err.message });
      }
      if (count) mark(turn, "saved", turn.proposal.details.filter(Boolean).map((ty) => ty.id).join(", "));
    },
  };
  const run = async (queryText, params) => {
    if (!queryText.trim() || isThinking(turnsRef.current)) return;
    const turn = newTurn("query", queryText);
    add(turn);
    try {
      const ran = await runQuery(queryText, params);
      finish(turn, { status: "done", record: queryRecord({ query_text: queryText, ...ran }) });
      keep(turn, "query", queryText, scopeOf("query"), { query_text: queryText, status: ran.status ?? "answered" });
    } catch (err) {
      finish(turn, { status: "error", error: err.message });
    }
  };
  const edit = (queryText) => {
    setQuery(queryText);
    setMode("query");
  };
  const newChat = () => {
    setTurns([]);
    setText("");
    setRail(false);
    if (window.location.hash !== "#/qa") window.location.hash = "#/qa";
  };

  useEffect(() => {
    if (datasets.data?.length === 1 && !chosen.length) setChosen([datasets.data[0].name]);   // the only dataset is the one to read
  }, [datasets.data]);

  const was = useRef(route.id);
  useEffect(() => {
    const before = was.current;
    was.current = route.id;
    if (route.id == null) {
      if (before != null && turnsRef.current[0]?.kind !== "past") setTurns([]);   // back to a new chat (a past turn just opened from the rail stays)
    } else if (!own.current.has(route.id) && !turnsRef.current.some((x) => x.record?.id === route.id)) {
      setTurns([savedTurn(route.id)]);   // a past question opens as a thread of one
      setMode("ask");
    }
  }, [route.id]);

  const asked = useRef("");
  useEffect(() => {
    if (!route.ask || asked.current === route.ask || holdAsk(me, demoAsk)) return;
    asked.current = route.ask;   // a question from the home page is asked once as this page opens (the address then becomes the saved answer's)
    send(route.ask);
  }, [route.ask, demoAsk]);

  useEffect(() => {
    const el = thread.current;
    if (!el) return;
    const last = turns[turns.length - 1];
    const card = last?.status === "done" && MODEL_KINDS.includes(last.kind) ? el.querySelector(".msg-bot:last-child .as-card") : null;
    // a plan or proposal card is read from its top; everything else follows the end of the thread
    if (card) el.scrollTo({ top: Math.max(0, card.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop - 72), behavior: "smooth" });
    else el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns.length, turns[turns.length - 1]?.status]);

  useEffect(() => { saveThread(window.sessionStorage, who, turns); }, [turns]);

  const ideas = suggestions(scope, []);
  const title = threadTitle(turns);
  if (noAsk && turns.length === 0 && route.id == null) {
    return (
      <main className="page chat-page chat-off">
        <div className="chat-off-state">
          <span className="chat-off-icon" aria-hidden="true"><Icon name="chat" size={22} /></span>
          <h1 tabIndex={-1}>{t("auth.guest.askOff.title")}</h1>
          <p>{t("auth.guest.askOff.body")}</p>
          <div className="chat-off-actions">
            <a className="button primary" href={hrefFor({ page: "boards" })}>{t("auth.guest.openBoards")}</a>
            <a className="button secondary" href={QUICK_START_URL} target="_blank" rel="noopener noreferrer">{t("auth.guest.runItself")}</a>
          </div>
        </div>
      </main>
    );
  }
  return (
    <main className="page chat-page">
      <div className={rail ? "chat rail-open" : "chat"}>
        <Rail scope={scope} turns={past.data?.turns} activeId={route.id} activeTurn={turns[0]?.kind === "past" ? turns[0].turnId : null} onNew={newChat} onPick={() => setRail(false)} onOpenTurn={openTurn} />
        {rail && <div className="rail-dim" onClick={() => setRail(false)} />}
        <section className="chat-main">
          <header className="chat-head">
            <button className="icon-button secondary rail-toggle" aria-label={t("ask.chat.historyToggle")} aria-expanded={rail} onClick={() => setRail(!rail)}><Icon name="menu" size={16} /></button>
            <h1 tabIndex={-1}>{t("ask.title")}</h1>
            <span className="chat-title muted">{title || t("ask.chat.untitled")}</span>
          </header>
          <div className="thread" ref={thread}>
            {info.status === "error" && <p className="error">{info.error}</p>}
            {turns.length === 0 ? (
              <div className="chat-empty">
                <span className="bot-mark big" aria-hidden="true" />
                <h2>{mayBuild ? t("ask.assistant.empty.title") : t("ask.chat.emptyTitle")}</h2>
                <p className="muted">{mayBuild ? t("ask.assistant.empty.sub") : scope && scope.types.length === 0 ? t("ask.chat.emptyNoScope") : t("ask.sub")}</p>
                {mayBuild && (
                  <div className="chips" aria-label={t("ask.assistant.mode.aria")}>
                    {modesFor(true).filter((m) => m !== "query").map((m) => <button key={m} className="chip" disabled={busy} onClick={() => setMode(m)}>{t(`ask.assistant.empty.${m}`)}</button>)}
                  </div>
                )}
                {!noAsk && ideas.length > 0 && queryMode === "ask" && (
                  <div className="chips" aria-label={t("ask.chat.try")}>
                    {ideas.map((q) => <button key={q} className="chip" disabled={busy} onClick={() => send(q)}>{q}</button>)}
                  </div>
                )}
              </div>
            ) : (
              <div className="turns" role="log" aria-label={t("ask.chat.thread")} aria-live="polite">
                {turns.map((turn, i) => <TurnView key={turn.id} turn={turn} mayBuild={mayBuild} onEdit={mayBuild ? edit : undefined} admin={admin} cards={cards} followUps={ideas} onAsk={send} busy={busy} last={i === turns.length - 1} onLoaded={(id, patch) => setTurns((ts) => settle(ts, id, patch))} />)}
              </div>
            )}
          </div>
          {noAsk ? <div className="composer-wrap"><DemoAskNote /></div> : <div className="composer-wrap">
            <Composer scope={scope} mayBuild={mayBuild} mode={queryMode} setMode={setMode} text={text} setText={setText} query={query} setQuery={setQuery} busy={busy} onSend={sendIn} onRun={run}
              scopes={{ datasets: datasets.data ?? [], pipelines: pipelines.data ?? [], chosen, setChosen, target, setTarget, types: (types.data ?? []).filter((x) => x.dataset), type: typeScope, setType: setTypeScope }} />
            <p className="composer-fine muted small" title={t(privacyKey(queryMode))}>{t(`${privacyKey(queryMode)}Short`)}</p>
          </div>}
        </section>
      </div>
    </main>
  );
}
