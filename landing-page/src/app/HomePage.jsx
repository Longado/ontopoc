import React, { useState } from "react";
import { getAsk, getDatasets, getNotices, getPipelines, getQueueCount, getRelations, getSources, getTypes, getUsers } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild, isAdmin } from "./authModel.js";
import { exampleQuestions, greeting, kpiCards, needsSetup, setupSteps, todoItems, updatedText } from "./homeModel.js";
import { formatDate, formatDateTime, t } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { Icon } from "./ui/Icon.jsx";

/** Everything the home page shows, read at once; a list this person may not read comes back as null instead of failing the page. */
async function loadHome(user) {
  const builder = canBuild(user);
  const ok = (p) => p.then((v) => v, () => null);
  const [datasets, types, relations, ask, notices, queue, pipelines, users, sources] = await Promise.all([
    ok(getDatasets()), ok(getTypes()), ok(getRelations()), ok(getAsk()), ok(getNotices()),
    builder ? ok(getQueueCount()) : null, builder ? ok(getPipelines()) : null, isAdmin(user) ? ok(getUsers()) : null, builder ? ok(getSources()) : null,
  ]);
  return { datasets, types, relations, ask, notices, queue: queue ?? 0, pipelines, users, sources };
}

const qaStatus = (status) => t(status === "answered" ? "home.qa.answered" : status === "no_data" ? "home.qa.noData" : "home.qa.unanswered");

function Checklist({ steps }) {
  const done = steps.filter((s) => s.state === "done").length;
  return (
    <section className="card setup" aria-labelledby="setup-title">
      <div className="setup-head">
        <h2 id="setup-title">{t("home.setup.title")}</h2>
        <span className="muted">{t("home.setup.progress", { done, total: steps.length })}</span>
      </div>
      <p className="muted">{t("home.setup.intro")}</p>
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
            <a className="kpi" href={c.href}>
              <span className="kpi-label">{c.label}</span>
              <span className="kpi-value">{c.value}</span>
              <span className="kpi-asof muted small">{c.asOf || t("home.kpi.confirmed")}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AskBox({ examples, ready }) {
  const [text, setText] = useState("");
  const ask = (question) => {
    const q = question.trim();
    if (q) window.location.hash = hrefFor({ page: "qa", id: null, ask: q });
  };
  return (
    <section className="ask-hero" aria-label={t("home.ask.aria")}>
      <form onSubmit={(e) => { e.preventDefault(); ask(text); }}>
        <Icon name="search" size={20} />
        <input type="text" aria-label={t("home.ask.input")} value={text} maxLength={300} placeholder={t("home.ask.placeholder", { example: examples[0] ?? t("home.ask.defaultExample") })} onChange={(e) => setText(e.target.value)} />
        <button className="primary" type="submit" disabled={!text.trim()}>{t("home.ask.submit")}</button>
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
      <h2 id="todo-title">{t("home.todo.title")}</h2>
      {items.length ? (
        <ul className="rows">
          {items.map((i) => (
            <li key={i.key}><a href={i.href}><span className={`row-dot dot-${i.key}`} aria-hidden="true" />{i.text}<Icon name="chevron-right" size={16} /></a></li>
          ))}
        </ul>
      ) : <EmptyState icon="check-circle" title={t("home.todo.emptyTitle")} text={t("home.todo.emptyText")} />}
    </section>
  );
}

function Recent({ history }) {
  return (
    <section className="card" aria-labelledby="recent-title">
      <h2 id="recent-title">{t("home.recent.title")}</h2>
      {history.length ? (
        <ul className="rows">
          {history.slice(0, 6).map((h) => (
            <li key={h.id}>
              <a href={hrefFor({ page: "qa", id: h.id })}><span className="row-main">{h.question}</span><span className="muted small">{formatDateTime(h.asked_at)} · {qaStatus(h.status)}</span></a>
            </li>
          ))}
        </ul>
      ) : <EmptyState icon="chat" title={t("home.recent.emptyTitle")} text={t("home.recent.emptyText")} />}
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
  const today = new Date();
  const fresh = updatedText(d.datasets);
  return (
    <main className="page home">
      <header className="home-head">
        <h1 tabIndex={-1}>{greeting(today, user?.display_name ?? "")}</h1>
        <p className="muted">{formatDate(today, { weekday: "long", month: "long", day: "numeric" })}{fresh && ` · ${fresh}`}</p>
      </header>
      {setup && <Checklist steps={setupSteps({ datasets: d.datasets, types, users: d.users, sources: d.sources, role: user?.role, meId: user?.id ?? null, canConfirm: d.queue > 0 })} />}
      {!setup && cards.length > 0 && <Kpis cards={cards} />}
      {!setup || (d.datasets ?? []).length > 0 ? <AskBox examples={examples} ready={types.some((t) => t.state === "confirmed")} /> : null}
      {(!setup || todos.length > 0) && <div className="home-grid"><Todo items={todos} /><Recent history={d.ask?.history ?? []} /></div>}
    </main>
  );
}
