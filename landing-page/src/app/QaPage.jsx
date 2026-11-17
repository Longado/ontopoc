import React, { useEffect, useRef, useState } from "react";
import { askQuestion, getAnswer, getAsk, runQuery } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText } from "./format.js";
import { answerView, criteriaLine, definitionHref, historyView, isAnswer, isThenAnswer, paramsIn, queryExample, queryParams, queryRecord, rangeNotes, readText, staleHeading, staleLines, standingText, timeWarning } from "./qaModel.js";
import { groupByDay, isThinking, newTurn, savedTurn, sendsOn, settle, suggestions, threadTitle } from "./chatModel.js";
import { ObjectGraph } from "./ObjectGraph.jsx";
import { State } from "./TypesPage.jsx";
import { formatDate, useT } from "./i18n/index.js";
import { Icon } from "./ui/Icon.jsx";
import { useLoad } from "./useLoad.js";

const KIND = { type: "ask.kind.type", meaning: "ask.kind.meaning", relation: "ask.kind.relation", view: "ask.kind.view", derived: "ask.kind.derived" };

/** The definitions a refusal names, bottom of the chain first: what it is, where it stands and why, who could confirm it. */
function Named({ list, mayBuild }) {
  const t = useT();
  return (
    <ul className="named">
      {list.map((d) => (
        <li key={d.id}>
          <p>
            <span className="muted">{t(KIND[d.kind])}</span> <a href={definitionHref(d.id, d.type)}>{d.name}</a> <State item={d} />
          </p>
          <p className="muted">{standingText(d)}</p>
          {d.who_can_confirm?.length > 0 && <p className="muted small">{t("ask.named.confirmers", { names: d.who_can_confirm.join(t("ask.sep")) })}</p>}
        </li>
      ))}
      {mayBuild && list.some((d) => d.state !== "confirmed") && <li><a href="#/confirm">{t("ask.named.toConfirm")}</a></li>}
    </ul>
  );
}

function Refusal({ record, mayBuild }) {
  const t = useT();
  const r = record.refusal;
  return (
    <div className="refusal-card">
      <h2 className="section">{t("ask.refusal.title")}</h2>
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

/** An answer as a message: the figure or table first, the time-word warning when the question's time was not used, one caliber line, and the technical basis folded. */
function AnswerCard({ record, mayBuild, onEdit }) {
  const t = useT();
  const warning = isAnswer(record) ? timeWarning(record) : null;
  const line = isAnswer(record) ? criteriaLine(record, record.asked_at ? timeText(record.asked_at) : "") : "";
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
        </>
      )}
    </section>
  );
}

/** The person's side of a turn: a plain bubble, the query in monospace. */
function UserBubble({ text, query }) {
  const t = useT();
  return (
    <div className="msg msg-user">
      <div className={query ? "bubble bubble-query" : "bubble"}>
        {query && <span className="bubble-tag">{t("ask.chat.queryTurn")}</span>}
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

function Thinking({ query }) {
  const t = useT();
  return (
    <AssistantMsg>
      <div className="thinking" role="status">
        <span className="typing" aria-hidden="true"><i /><i /><i /></span>
        <span>{t("ask.chat.thinking")}</span>
      </div>
      <p className="muted small">{query ? t("ask.query.busy") : t("ask.input.busy")}</p>
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

function TurnView({ turn, mayBuild, onEdit, followUps, onAsk, busy, last, onLoaded }) {
  if (turn.kind === "saved") return <SavedTurn turn={turn} mayBuild={mayBuild} onEdit={onEdit} followUps={followUps} onAsk={onAsk} last={last} onLoaded={onLoaded} />;
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

/** The sticky composer: a growing textarea (Enter sends, Shift+Enter breaks the line), the scope chip, and for a builder the Query toggle. */
function Composer({ scope, mayBuild, mode, setMode, text, setText, query, setQuery, busy, onSend, onRun }) {
  const t = useT();
  const box = useRef(null);
  const [values, setValues] = useState({});
  const isQuery = mode === "query";
  const value = isQuery ? query : text;
  const names = isQuery ? paramsIn(query) : [];
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value, mode]);
  useEffect(() => {
    if (!busy) box.current?.focus({ preventScroll: true });
  }, [busy, mode]);
  const submit = (e) => {
    e?.preventDefault();
    if (!value.trim() || busy) return;
    if (isQuery) onRun(query, queryParams(query, values));
    else onSend(text);
  };
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
      <textarea
        ref={box}
        className={isQuery ? "composer-input mono" : "composer-input"}
        aria-label={isQuery ? t("ask.query.aria") : t("ask.input.aria")}
        rows={isQuery ? 3 : 1}
        value={value}
        maxLength={isQuery ? undefined : 300}
        spellCheck={false}
        placeholder={isQuery ? queryExample(scope) || t("ask.chat.composer.queryPlaceholder") : t("ask.chat.composer.placeholder")}
        disabled={busy}
        onChange={(e) => (isQuery ? setQuery(e.target.value) : setText(e.target.value))}
        onKeyDown={(e) => {
          if (sendsOn({ key: e.key, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, isComposing: e.nativeEvent.isComposing, keyCode: e.keyCode }, mode)) submit(e);
        }}
      />
      <div className="composer-bar">
        <div className="composer-tools">
          {mayBuild && (
            <button type="button" className={isQuery ? "tool on" : "tool"} aria-pressed={isQuery} title={t("ask.chat.composer.queryOn")} onClick={() => setMode(isQuery ? "ask" : "query")}>
              <Icon name="edit" size={13} /> {t("ask.chat.composer.query")}
            </button>
          )}
          <ScopeChip scope={scope} />
        </div>
        {isQuery && <span className="composer-hint muted small">{t("ask.chat.composer.hintQuery")}</span>}
        <button className="primary send" type="submit" disabled={busy || !value.trim()} aria-label={isQuery ? t("ask.chat.composer.run") : t("ask.chat.composer.send")}>
          <Icon name={isQuery ? "play" : "send"} size={16} />
        </button>
      </div>
    </form>
  );
}

/** The history rail: New chat, then the saved questions grouped by the day they were asked. */
function Rail({ scope, activeId, onNew, onPick }) {
  const t = useT();
  const groups = groupByDay(scope?.history ?? []);
  const label = (g) => (g.key === "today" ? t("ask.chat.today") : g.key === "yesterday" ? t("ask.chat.yesterday") : g.key === "undated" ? t("ask.chat.undated") : formatDate(g.when));
  return (
    <aside className="chat-rail" aria-label={t("ask.history.aria")}>
      <button className="chat-new" onClick={onNew}><Icon name="plus" size={14} /> {t("ask.chat.new")}</button>
      <div className="rail-scroll">
        {scope && scope.history.length === 0 && <p className="muted small rail-empty">{t("ask.history.empty")}</p>}
        {groups.map((g) => (
          <section key={g.key} className="rail-group">
            <h2 className="history-title">{label(g)}</h2>
            <ul className="history-list">
              {g.items.map((h) => {
                const v = historyView(h, timeText(h.asked_at));
                return (
                  <li key={h.id}>
                    <a href={`#/qa/${h.id}`} title={v.meta} onClick={onPick} aria-current={h.id === activeId ? "page" : undefined} className={h.id === activeId ? "active" : ""}>
                      <span className="hq">{v.question}</span>
                    </a>
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
  const mayBuild = canBuild(useAuth().user);
  const [info, reload] = useLoad(getAsk, []);
  const [text, setText] = useState("");
  const [mode, setMode] = useState("ask");
  const [query, setQuery] = useState("");
  const [turns, setTurns] = useState([]);
  const [rail, setRail] = useState(false);
  const scope = info.data;
  const turnsRef = useRef(turns);
  turnsRef.current = turns;
  const own = useRef(new Set());   // saved ids this session's thread already holds: opening one of them must not replace the thread
  const thread = useRef(null);
  const busy = isThinking(turns);
  const queryMode = mayBuild ? mode : "ask";

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
  const run = async (queryText, params) => {
    if (!queryText.trim() || isThinking(turnsRef.current)) return;
    const turn = newTurn("query", queryText);
    add(turn);
    try {
      finish(turn, { status: "done", record: queryRecord({ query_text: queryText, ...(await runQuery(queryText, params)) }) });
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

  const was = useRef(route.id);
  useEffect(() => {
    const before = was.current;
    was.current = route.id;
    if (route.id == null) {
      if (before != null) setTurns([]);   // back to a new chat
    } else if (!own.current.has(route.id)) {
      setTurns([savedTurn(route.id)]);   // a past question opens as a thread of one
      setMode("ask");
    }
  }, [route.id]);

  const asked = useRef("");
  useEffect(() => {
    if (!route.ask || asked.current === route.ask) return;
    asked.current = route.ask;   // a question from the home page is asked once as this page opens (the address then becomes the saved answer's)
    send(route.ask);
  }, [route.ask]);

  useEffect(() => {
    const el = thread.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns.length, turns[turns.length - 1]?.status]);

  const ideas = suggestions(scope, []);
  const title = threadTitle(turns);
  return (
    <main className="page chat-page">
      <div className={rail ? "chat rail-open" : "chat"}>
        <Rail scope={scope} activeId={route.id} onNew={newChat} onPick={() => setRail(false)} />
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
                <h2>{t("ask.chat.emptyTitle")}</h2>
                <p className="muted">{scope && scope.types.length === 0 ? t("ask.chat.emptyNoScope") : t("ask.sub")}</p>
                {ideas.length > 0 && (
                  <div className="chips" aria-label={t("ask.chat.try")}>
                    {ideas.map((q) => <button key={q} className="chip" disabled={busy} onClick={() => send(q)}>{q}</button>)}
                  </div>
                )}
              </div>
            ) : (
              <div className="turns" role="log" aria-label={t("ask.chat.thread")} aria-live="polite">
                {turns.map((turn, i) => <TurnView key={turn.id} turn={turn} mayBuild={mayBuild} onEdit={mayBuild ? edit : undefined} followUps={ideas} onAsk={send} busy={busy} last={i === turns.length - 1} onLoaded={(id, patch) => setTurns((ts) => settle(ts, id, patch))} />)}
              </div>
            )}
          </div>
          <div className="composer-wrap">
            <Composer scope={scope} mayBuild={mayBuild} mode={queryMode} setMode={setMode} text={text} setText={setText} query={query} setQuery={setQuery} busy={busy} onSend={send} onRun={run} />
            <p className="composer-fine muted small" title={t("ask.input.hint")}>{t("ask.chat.privacy")}</p>
          </div>
        </section>
      </div>
    </main>
  );
}
