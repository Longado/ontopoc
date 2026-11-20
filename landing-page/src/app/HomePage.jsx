import React, { useState } from "react";
import { getAsk, getAskTally, getBoards, getDatasets, getNotices, getPipelines, getQueueCount, getRelations, getSources, getTypes, getUsers } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { DemoAskNote } from "./DemoAskNote.jsx";
import { askOff } from "./demoModel.js";
import { useDemoAsk } from "./useDemoAsk.js";
import { canBuild, isAdmin, isGuest } from "./authModel.js";
import { exampleQuestions, greeting, kpiCards, needsSetup, quickActions, setupSteps, tallyView, todoItems, updatedText } from "./homeModel.js";
import { formatDate, formatDateTime, t } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { useLoad } from "./useLoad.js";
import "./boards-home.css";
import { Icon } from "./ui/Icon.jsx";

/** Everything the home page shows, read at once; a list this person may not read comes back as null instead of failing the page. */
async function loadHome(user) {
  const builder = canBuild(user);
  const ok = (p) => p.then((v) => v, () => null);
  const [datasets, types, relations, ask, notices, queue, pipelines, users, sources, boards] = await Promise.all([
    ok(getDatasets()), ok(getTypes()), ok(getRelations()), ok(getAsk()), ok(getNotices()),
    builder ? ok(getQueueCount()) : null, builder ? ok(getPipelines()) : null, isAdmin(user) ? ok(getUsers()) : null, builder ? ok(getSources()) : null,
    isGuest(user) ? ok(getBoards()) : null,
  ]);
  const tally = builder ? await ok(getAskTally()) : null;
  return { datasets, types, relations, ask, notices, queue: queue ?? 0, pipelines, users, sources, boards, tally };
}

const qaStatus = (status) => t(status === "answered" ? "home.qa.answered" : status === "no_data" ? "home.qa.noData" : "home.qa.unanswered");

function Checklist({ steps }) {
  const done = steps.filter((s) => s.state === "done").length;
  return (
    <section className="card setup" aria-labelledby="setup-title">
      <div className="setup-head">
        <div>
          <h2 id="setup-title">{t("home.setup.title")}</h2>
          <p className="muted">{t("home.setup.intro")}</p>
        </div>
        <span className="setup-count">{t("home.setup.progress", { done, total: steps.length })}</span>
      </div>
      <div className="setup-bar" role="progressbar" aria-label={t("home.setup.bar")} aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={done}><span style={{ width: `${(done / steps.length) * 100}%` }} /></div>
      <ol className="steps">
        {steps.map((s, i) => (
          <li key={s.key} className={`step step-${s.state}`}>
            <span className="step-no" aria-hidden="true">{s.state === "done" ? <Icon name="check" size={16} /> : i + 1}</span>
            <div className="step-body">
              <p className="step-title"><strong>{s.title}</strong> <span className={`step-state step-state-${s.state}`}>{t(`home.step.${s.state}`)}</span></p>
              <p className="muted">{s.text}</p>
              {s.note && <p className="step-note">{s.note}</p>}
            </div>
            {s.extra && <a className="button plain" href={s.extra.href}>{s.extra.label}</a>}
            {s.button && <a className={`button ${s.state === "next" ? "primary" : "secondary"}`} href={s.button.href}>{s.state === "done" ? t("home.step.view") : s.button.label}</a>}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Kpis({ cards }) {
  return (
    <section aria-label={t("home.kpi.aria")}>
      <ul className="kpis">
        {cards.map((c) => (
          <li key={c.key}>
            <a className="kpi bh-stat" href={c.href}>
              <span className="kpi-top"><span className="kpi-label">{c.label}</span><Icon name="chevron-right" size={14} /></span>
              <span className="kpi-value">{c.value}</span>
              <span className="kpi-asof">{c.asOf || t("home.kpi.confirmed")}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A guest's first row: three compact cards, two into the first board and one to the README. */
function StartHere({ boards }) {
  const first = boards?.dashboards?.[0];
  const board = first ? `#/boards/${first.id}` : "#/boards";
  const cards = [
    { key: "orders", href: board, icon: "board" },
    { key: "trust", href: board, icon: "check-circle" },
    { key: "refuse", href: "https://github.com/Longado/ontopoc#readme", icon: "alert", external: true },
  ];
  return (
    <section aria-labelledby="start-title">
      <h2 id="start-title" className="bh-section">{t("home.start.title")}</h2>
      <ul className="bh-start">
        {cards.map((c) => (
          <li key={c.key}>
            <a className="bh-start-card" href={c.href} {...(c.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
              <span className="bh-start-icon" aria-hidden="true"><Icon name={c.icon} size={16} /></span>
              <span className="bh-start-title">{t(`home.start.${c.key}.title`)}{c.external && <span className="visually-hidden"> {t("home.start.newTab")}</span>}</span>
              <span className="bh-start-text">{t(`home.start.${c.key}.text`)}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AskBox({ examples, ready }) {
  const [text, setText] = useState("");
  const { user } = useAuth();
  const demoAsk = useDemoAsk();
  if (askOff(user, demoAsk)) return <section className="ask-hero" aria-label={t("home.ask.aria")}><DemoAskNote /></section>;
  const ask = (question) => {
    const q = question.trim();
    if (q) window.location.hash = hrefFor({ page: "qa", id: null, ask: q });
  };
  return (
    <section className="ask-hero" aria-label={t("home.ask.aria")}>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(text); }}>
        <input type="text" aria-label={t("home.ask.input")} value={text} maxLength={300} placeholder={t("home.ask.placeholder", { example: examples[0] ?? t("home.ask.defaultExample") })} onChange={(e) => setText(e.target.value)} />
        <div className="composer-bar">
          <span className="composer-hint"><Icon name="search" size={14} />{t("home.ask.hint")}</span>
          <button className="primary" type="submit" disabled={!text.trim()}>{t("home.ask.submit")}<Icon name="send" size={14} /></button>
        </div>
      </form>
      {examples.length > 0 ? (
        <p className="examples"><span className="muted">{t("home.ask.try")}</span>{examples.map((q) => <button key={q} className="example" onClick={() => ask(q)}>{q}</button>)}</p>
      ) : !ready && <p className="muted examples">{t("home.ask.none")}</p>}
    </section>
  );
}

function Todo({ items }) {
  return (
    <section className="card" aria-labelledby="todo-title">
      <div className="card-head"><h2 id="todo-title">{t("home.todo.title")}</h2></div>
      {items.length ? (
        <ul className="rows">
          {items.map((i) => (
            <li key={i.key}><a href={i.href}><span className={`row-count dot-${i.key}`} aria-hidden="true">{i.count}</span><span className="row-main">{i.text}</span><Icon name="chevron-right" size={16} /></a></li>
          ))}
        </ul>
      ) : <p className="bh-quiet">{t("home.todo.quiet")}</p>}
    </section>
  );
}

function Recent({ history, examples }) {
  return (
    <section className="card" aria-labelledby="recent-title">
      <div className="card-head"><h2 id="recent-title">{t("home.recent.title")}</h2><a className="card-link" href={hrefFor({ page: "qa", id: null })}>{t("home.recent.all")}<Icon name="chevron-right" size={14} /></a></div>
      {history.length ? (
        <ul className="rows">
          {history.slice(0, 6).map((h) => (
            <li key={h.id}>
              <a href={hrefFor({ page: "qa", id: h.id })}><span className={`row-dot qa-${h.status}`} aria-hidden="true" /><span className="row-main">{h.question}</span><span className="muted small">{formatDateTime(h.asked_at)} · {qaStatus(h.status)}</span></a>
            </li>
          ))}
        </ul>
      ) : (
        <>
          <p className="bh-quiet">{t("home.recent.quiet")}</p>
          {examples.length > 0 && <p className="examples examples-center bh-examples">{examples.slice(0, 3).map((q) => <a key={q} className="example" href={hrefFor({ page: "qa", id: null, ask: q })}>{q}</a>)}</p>}
        </>
      )}
    </section>
  );
}

/** For builders and admins: how the team's questions of the last 7 days ended, and which unconfirmed definitions held the most back. */
function Tally({ view }) {
  return (
    <section className="card tally" aria-labelledby="tally-title">
      <div className="card-head"><h2 id="tally-title">{t("home.tally.title")}</h2><span className="muted small">{view.before}</span></div>
      <dl className="tally-figures">
        {view.figures.map((f) => (
          <div key={f.key} className={`tally-figure tally-${f.key}`}><dt>{f.label}</dt><dd>{f.value}{f.note && <span className="muted small">{f.note}</span>}</dd></div>
        ))}
      </dl>
      {view.held.length > 0 && (
        <>
          <h3 className="tally-sub">{t("home.tally.held.title")}</h3>
          <ul className="rows">
            {view.held.map((h) => (
              <li key={h.key}><a href={h.href}><span className="row-count dot-failed" aria-hidden="true">{h.count}</span><span className="row-main">{h.text}</span><Icon name="chevron-right" size={16} /></a></li>
            ))}
          </ul>
        </>
      )}
      <p className="tally-note muted small">{t("home.tally.note")}</p>
    </section>
  );
}

/** The page the app opens on: the setup checklist while the workspace is not ready (builders and admins), then the daily view: greeting, ask box, to-dos, recent questions. */
export function HomePage() {
  const { user } = useAuth();
  const [state] = useLoad(() => loadHome(user), []);
  const d = state.data;
  const mayBuild = canBuild(user);
  if (!d) return <main className="page"><h1 tabIndex={-1} className="visually-hidden">{t("home.title")}</h1><p className="muted">{t("common.loading")}</p></main>;
  const types = d.types ?? [];
  const setup = mayBuild && needsSetup({ datasets: d.datasets, types });
  const failedRuns = (d.pipelines ?? []).filter((p) => p.last_run?.status === "failed").length;
  const todos = todoItems({ unread: d.notices?.unread ?? 0, queue: d.queue, failedRuns, mayBuild });
  const examples = exampleQuestions(types, d.relations ?? []);
  const cards = kpiCards(types, d.datasets);
  const quick = quickActions(mayBuild);
  const today = new Date();
  const fresh = updatedText(d.datasets);
  const guest = isGuest(user);
  const history = d.ask?.history ?? [];
  const tally = mayBuild ? tallyView(d.tally) : null;
  const showTodo = !guest || todos.length > 0;
  const showRecent = !guest || history.length > 0;
  return (
    <main className="page home bh-home">
      <header className="home-head">
        <div>
          <h1 tabIndex={-1}>{greeting(today, user?.display_name ?? "")}</h1>
          <p className="muted bh-date">{formatDate(today, { weekday: "long", month: "long", day: "numeric" })}{fresh && ` · ${fresh}`}</p>
        </div>
        {quick.length > 0 && (
          <nav className="quick" aria-label={t("home.quick.aria")}>
            {quick.map((a) => <a key={a.key} className="quick-link" href={a.href}><Icon name={a.icon} size={14} />{a.label}</a>)}
          </nav>
        )}
      </header>
      {setup && <Checklist steps={setupSteps({ datasets: d.datasets, types, users: d.users, sources: d.sources, role: user?.role, meId: user?.id ?? null, canConfirm: d.queue > 0 })} />}
      {!setup || (d.datasets ?? []).length > 0 ? <AskBox examples={examples} ready={types.some((t) => t.state === "confirmed")} /> : null}
      {guest && !setup && <StartHere boards={d.boards} />}
      {!setup && cards.length > 0 && <Kpis cards={cards} />}
      {(!setup || todos.length > 0) && (showTodo || showRecent) && (
        <div className={`home-grid${showTodo && showRecent ? "" : " bh-single"}`}>
          {showTodo && <Todo items={todos} />}
          {showRecent && <Recent history={history} examples={examples} />}
        </div>
      )}
      {!setup && tally && <Tally view={tally} />}
    </main>
  );
}
