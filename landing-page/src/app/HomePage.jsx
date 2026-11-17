import React, { useState } from "react";
import { getAsk, getDatasets, getNotices, getPipelines, getQueueCount, getRelations, getSources, getTypes, getUsers } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild, isAdmin } from "./authModel.js";
import { timeText } from "./format.js";
import { exampleQuestions, greeting, kpiCards, needsSetup, setupSteps, todoItems, updatedText } from "./homeModel.js";
import { statusText } from "./qaModel.js";
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

const STEP_MARK = { done: "已完成", next: "下一步", todo: "未开始" };

function Checklist({ steps }) {
  const done = steps.filter((s) => s.state === "done").length;
  return (
    <section className="card setup" aria-labelledby="setup-title">
      <div className="setup-head">
        <h2 id="setup-title">开始使用</h2>
        <span className="muted">{done} / {steps.length} 步完成</span>
      </div>
      <p className="muted">做完这四步，同事就能在这里提问、看看板。</p>
      <ol className="steps">
        {steps.map((s, i) => (
          <li key={s.key} className={`step step-${s.state}`}>
            <span className="step-no" aria-hidden="true">{s.state === "done" ? <Icon name="check" size={16} /> : i + 1}</span>
            <div className="step-body">
              <p className="step-title"><strong>{s.title}</strong> <span className={`step-state step-state-${s.state}`}>{STEP_MARK[s.state]}</span></p>
              <p className="muted">{s.text}</p>
              {s.note && <p className="step-note">{s.note}</p>}
            </div>
            {s.extra && <a className="button plain" href={s.extra.href}>{s.extra.label}</a>}
            {s.button && <a className={`button ${s.state === "next" ? "primary" : "secondary"}`} href={s.button.href}>{s.state === "done" ? "查看" : s.button.label}</a>}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Kpis({ cards }) {
  return (
    <section aria-label="关键数字">
      <ul className="kpis">
        {cards.map((c) => (
          <li key={c.key}>
            <a className="kpi" href={c.href}>
              <span className="kpi-label">{c.label}</span>
              <span className="kpi-value">{c.value}</span>
              <span className="kpi-asof muted small">{c.asOf || "已确认"}</span>
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
    <section className="ask-hero" aria-label="问数">
      <form onSubmit={(e) => { e.preventDefault(); ask(text); }}>
        <Icon name="search" size={20} />
        <input type="text" aria-label="问一个问题" value={text} maxLength={300} placeholder={`问一个问题，比如：${examples[0] ?? "订单一共有多少"}`} onChange={(e) => setText(e.target.value)} />
        <button className="primary" type="submit" disabled={!text.trim()}>提问</button>
      </form>
      {examples.length > 0 ? (
        <p className="examples"><span className="muted">试试这些</span>{examples.map((q) => <button key={q} className="example" onClick={() => ask(q)}>{q}</button>)}</p>
      ) : !ready && <p className="muted examples">还没有确认过的对象类型，暂时没有可问的内容。</p>}
    </section>
  );
}

function Todo({ items }) {
  return (
    <section className="card" aria-labelledby="todo-title">
      <h2 id="todo-title">待我处理</h2>
      {items.length ? (
        <ul className="rows">
          {items.map((i) => (
            <li key={i.key}><a href={i.href}><span className={`row-dot dot-${i.key}`} aria-hidden="true" />{i.text}<Icon name="chevron-right" size={16} /></a></li>
          ))}
        </ul>
      ) : <EmptyState icon="check-circle" title="没有要处理的事" text="有新消息或等你确认的东西时，会在这里出现。" />}
    </section>
  );
}

function Recent({ history }) {
  return (
    <section className="card" aria-labelledby="recent-title">
      <h2 id="recent-title">我最近的提问</h2>
      {history.length ? (
        <ul className="rows">
          {history.slice(0, 6).map((h) => (
            <li key={h.id}>
              <a href={hrefFor({ page: "qa", id: h.id })}><span className="row-main">{h.question}</span><span className="muted small">{timeText(h.asked_at)} {statusText(h.status)}</span></a>
            </li>
          ))}
        </ul>
      ) : <EmptyState icon="chat" title="还没有提过问题" text="在上面的框里问第一个问题。" />}
    </section>
  );
}

/** The page the app opens on: the setup checklist while the workspace is not ready (builders and admins), then the daily view: greeting, ask box, to-dos, recent questions. */
export function HomePage() {
  const { user } = useAuth();
  const [state] = useLoad(() => loadHome(user), []);
  const d = state.data;
  const mayBuild = canBuild(user);
  if (!d) return <main className="page"><h1 tabIndex={-1} className="visually-hidden">首页</h1><p className="muted">加载中</p></main>;
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
        <p className="muted">{today.getMonth() + 1} 月 {today.getDate()} 日{fresh && ` · ${fresh}`}</p>
      </header>
      {setup && <Checklist steps={setupSteps({ datasets: d.datasets, types, users: d.users, sources: d.sources, role: user?.role, meId: user?.id ?? null, canConfirm: d.queue > 0 })} />}
      {!setup && cards.length > 0 && <Kpis cards={cards} />}
      {!setup || (d.datasets ?? []).length > 0 ? <AskBox examples={examples} ready={types.some((t) => t.state === "confirmed")} /> : null}
      {(!setup || todos.length > 0) && <div className="home-grid"><Todo items={todos} /><Recent history={d.ask?.history ?? []} /></div>}
    </main>
  );
}
