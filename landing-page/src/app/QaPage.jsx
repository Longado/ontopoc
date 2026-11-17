import React, { useEffect, useRef, useState } from "react";
import { askQuestion, getAnswer, getAsk, runQuery } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText } from "./format.js";
import { answerView, criteriaLine, definitionHref, historyView, isAnswer, isThenAnswer, paramsIn, queryExample, queryParams, queryRecord, rangeNotes, readText, scopeText, staleHeading, staleLines, standingText, timeWarning } from "./qaModel.js";
import { ObjectGraph } from "./ObjectGraph.jsx";
import { State } from "./TypesPage.jsx";
import { useT } from "./i18n/index.js";
import { PageHeader } from "./ui/PageHeader.jsx";
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

/** An answer as a card: the figure or table first, the time-word warning when the question's time was not used, one caliber line, and the technical basis folded. */
function AnswerCard({ record, mayBuild, onEdit, title }) {
  const t = useT();
  const warning = isAnswer(record) ? timeWarning(record) : null;
  const line = isAnswer(record) ? criteriaLine(record, record.asked_at ? timeText(record.asked_at) : "") : "";
  return (
    <section className="turn qa-card">
      {title && <h2 className="question">{title}</h2>}
      {record.asked_at && <p className="muted small">{timeText(record.asked_at)}</p>}
      {record.withheld ? <p className="warn">{record.reason}</p> : (
        <>
          {isAnswer(record) ? <Answer record={record} /> : <Refusal record={record} mayBuild={mayBuild} />}
          {warning && <p className="time-warn" role="alert">{warning}</p>}
          {line && <p className="criteria">{line}</p>}
          <details className="basis">
            <summary>{t("ask.card.basis")}</summary>
            <Basis record={record} onEdit={onEdit} />
          </details>
        </>
      )}
    </section>
  );
}

function Saved({ id, mayBuild, onEdit }) {
  const t = useT();
  const [state] = useLoad(() => getAnswer(id), [id]);
  const r = state.data;
  if (state.status === "error") return <p className="error">{state.missing ? t("ask.saved.missing") : state.error}</p>;
  if (!r) return <p className="muted">{t("ask.loading")}</p>;
  return <AnswerCard record={r} mayBuild={mayBuild} onEdit={onEdit} title={r.question} />;
}

/** The query box: OntoPoc Query run as this person, by the same engine as a question, with no model; nothing is kept. */
function QueryBox({ scope, text, setText, mayBuild }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [values, setValues] = useState({});
  const names = paramsIn(text);
  const run = async (e) => {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(queryRecord({ query_text: text, ...(await runQuery(text, queryParams(text, values))) }));
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };
  return (
    <>
      <form className="query" onSubmit={run}>
        <textarea aria-label={t("ask.query.aria")} rows={6} value={text} spellCheck={false} placeholder={queryExample(scope) || t("ask.query.placeholder")} disabled={busy} onChange={(e) => setText(e.target.value)} />
        {names.length > 0 && (
          <div className="inline wide" role="group" aria-label={t("ask.query.params")}>
            {names.map((n) => (
              <label key={n} className="field">
                <span className="caption">${n}</span>
                <input type="text" aria-label={t("ask.query.param", { name: n })} value={values[n] ?? ""} disabled={busy} onChange={(e) => setValues({ ...values, [n]: e.target.value })} />
              </label>
            ))}
          </div>
        )}
        <button className="primary" type="submit" disabled={busy || !text.trim()}>{t("ask.query.run")}</button>
      </form>
      {mayBuild
        ? <details className="query-help"><summary>{t("ask.query.help")}</summary><p className="hint">{t("ask.query.helpBefore")}<code>{t("ask.query.sample")}</code>{t("ask.query.helpAfter")}<a href="https://github.com/Longado/ontopoc/blob/main/docs/QUERY.md" target="_blank" rel="noreferrer">{t("ask.query.helpLink")}</a></p></details>
        : <p className="hint">{t("ask.query.viewerHint")}</p>}
      {busy && <p className="muted" role="status">{t("ask.query.busy")}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {result && (
        <AnswerCard record={result} mayBuild={mayBuild} />
      )}
    </>
  );
}

export function QaPage({ route }) {
  const t = useT();
  const mayBuild = canBuild(useAuth().user);
  const [info, reload] = useLoad(getAsk, []);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("ask");
  const [query, setQuery] = useState("");
  const scope = info.data;
  const edit = (text) => {
    setQuery(text);
    setMode("query");
  };
  const ask = async (e, question = text) => {
    e?.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const saved = await askQuestion(question);
      setText("");
      reload();
      window.location.hash = `#/qa/${saved.id}`;
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };
  const asked = useRef("");
  useEffect(() => {
    if (!route.ask || asked.current === route.ask) return;
    asked.current = route.ask;   // a question from the home page is asked once as this page opens (the address then becomes the saved answer's)
    setText(route.ask);
    ask(null, route.ask);
  }, [route.ask]);
  return (
    <main className="page">
      <PageHeader title={t("ask.title")} sub={t("ask.sub")} />
      {info.status === "error" && <p className="error">{info.error}</p>}
      <div className="qa">
        <aside className="history" aria-label={t("ask.history.aria")}>
          <h2 className="history-title">{t("ask.history.title")}</h2>
          {scope && scope.history.length === 0 && <p className="muted small">{t("ask.history.empty")}</p>}
          <ul className="history-list">
            {scope?.history.map((h) => {
              const v = historyView(h, timeText(h.asked_at));
              return (
                <li key={h.id}>
                  <a href={`#/qa/${h.id}`} onClick={() => setMode("ask")} aria-current={h.id === route.id ? "page" : undefined} className={h.id === route.id ? "active" : ""}>
                    <span className="hq">{v.question}</span>
                    <span className="muted small block">{v.meta}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        </aside>
        <section>
          {scope && (
            <details className="scope">
              <summary>{scopeText(scope)}</summary>
              <p className="muted">{scope.types.length ? scope.types.map((type) => type.name).join(t("ask.sep")) : t("ask.scope.empty")}</p>
              {scope.views?.length > 0 && <p className="muted">{t("ask.scope.views", { names: scope.views.map((v) => v.name).join(t("ask.sep")) })}</p>}
              {scope.left_out.length > 0 && (
                <>
                  <p className="muted scope-sub">{t("ask.scope.leftOut")}</p>
                  <ul className="named">
                    {scope.left_out.map((d) => <li key={d.id}><a href={definitionHref(d.id, d.type)}>{d.name}</a> <State item={d} /></li>)}
                  </ul>
                </>
              )}
            </details>
          )}
          <div className="seg" role="group" aria-label={t("ask.mode.aria")}>
            <button className={mode === "ask" ? "on" : ""} aria-pressed={mode === "ask"} onClick={() => setMode("ask")}>{t("ask.mode.ask")}</button>
            <button className={mode === "query" ? "on" : ""} aria-pressed={mode === "query"} onClick={() => setMode("query")}>{t("ask.mode.query")}</button>
          </div>
          {mode === "query" ? <QueryBox scope={scope} text={query} setText={setQuery} mayBuild={mayBuild} /> : (
            <>
              <form className="ask" onSubmit={ask}>
                <input type="text" aria-label={t("ask.input.aria")} value={text} maxLength={300} placeholder={t("ask.input.placeholder")} disabled={busy} onChange={(e) => setText(e.target.value)} />
                <button className="primary" type="submit" disabled={busy || !text.trim()}>{t("ask.input.submit")}</button>
              </form>
              <p className="hint">{t("ask.input.hint")}</p>
              {busy && <p className="muted" role="status">{t("ask.input.busy")}</p>}
              {error && <p className="error" role="alert">{error}</p>}
            </>
          )}
          {mode === "ask" && route.id && <Saved key={route.id} id={route.id} mayBuild={mayBuild} onEdit={edit} />}
        </section>
      </div>
    </main>
  );
}
