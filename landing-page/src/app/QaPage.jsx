import React, { useState } from "react";
import { askQuestion, getAnswer, getAsk } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText } from "./format.js";
import { answerView, definitionHref, isAnswer, isThenAnswer, readText, scopeText, staleHeading, staleLines, standingText, statusText } from "./qaModel.js";
import { State } from "./TypesPage.jsx";
import { useLoad } from "./useLoad.js";

const KIND = { type: "对象类型", meaning: "含义", relation: "关系", view: "视图" };

/** The definitions a refusal names, bottom of the chain first: what it is, where it stands and why, who could confirm it. */
function Named({ list, mayBuild }) {
  return (
    <ul className="named">
      {list.map((d) => (
        <li key={d.id}>
          <p>
            <span className="muted">{KIND[d.kind]}</span> <a href={definitionHref(d.id, d.type)}>{d.name}</a> <State item={d} />
          </p>
          <p className="muted">{standingText(d)}</p>
          {d.who_can_confirm?.length > 0 && <p className="muted small">可以确认的人：{d.who_can_confirm.join("、")}</p>}
        </li>
      ))}
      {mayBuild && list.length > 0 && <li><a href="#/confirm">去待确认</a></li>}
    </ul>
  );
}

function Refusal({ record, mayBuild }) {
  const r = record.refusal;
  return (
    <div className="refusal-card">
      <h2 className="section">没有回答</h2>
      {r?.kind === "unsettled" && (
        <>
          <p>问题用到的定义还不能用，没有照旧的定义回答。</p>
          <Named list={r.definitions} mayBuild={mayBuild} />
        </>
      )}
      {r?.kind === "not_in_scope" && (
        <>
          <p>{record.reason}</p>
          <p className="muted">你能问的是 {r.in_scope.length ? r.in_scope.join("、") : "（还没有已确认的对象类型）"}，回答它需要的东西不在里面。</p>
          {r.left_out?.length > 0 && (
            <>
              <p className="muted" style={{ marginTop: 12 }}>这些还不在范围里：</p>
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

function Answer({ record }) {
  const view = answerView(record);
  const notes = staleLines(record);
  const then = isThenAnswer(record);
  return (
    <div className={then ? "answer then" : "answer"}>
      {then && <p className="warn">{staleHeading(record)}</p>}
      <div className="big">{then && <span className="small muted">当时的答案 </span>}{view.big}</div>
      {view.note && <p className="muted">{view.note}</p>}
      {view.table && (
        <div className="table-wrap">
          <table>
            <thead><tr>{view.table.head.map((h, i) => <th key={h} className={i ? "num" : ""}>{h}</th>)}</tr></thead>
            <tbody>{view.table.rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} className={j ? "num" : ""}>{v}</td>)}</tr>)}</tbody>
          </table>
          {view.table.total > view.table.rows.length && <p className="muted small">只显示前 {view.table.rows.length} 组，共 {view.table.total} 组</p>}
        </div>
      )}
      {notes.length > 0 && <p className="warn">{then ? "" : `${staleHeading(record)}：`}{notes.join("；")}</p>}
    </div>
  );
}

/** How the question was read, what it stood on, what it read, and the steps: under every answer and every refusal. */
function Basis({ record }) {
  const read = readText(record.datasets);
  return (
    <>
      <dl className="defs">
        {record.reasoning && (
          <>
            <dt>理解为</dt>
            <dd>
              {record.reasoning}
              {record.path && <span className="muted"> {record.path}</span>}
              {record.understood?.map((u) => <span className="muted small block" key={u.definition}>{u.definition}：{u.how}</span>)}
            </dd>
          </>
        )}
        {record.definitions.length > 0 && (
          <>
            <dt>用到的定义</dt>
            <dd>
              {record.definitions.map((d) => (
                <span className="block" key={d.id}>
                  {KIND[d.kind]} <a href={definitionHref(d.id, d.type)}>{d.name}</a> <span className="muted">{d.confirmed_by ? `${d.confirmed_by} 于 ${timeText(d.confirmed_at)} 确认` : ""}</span>
                </span>
              ))}
            </dd>
          </>
        )}
        {read.length > 0 && <><dt>读取的数据</dt><dd>{read.map((t) => <span className="block" key={t}>{t}</span>)}</dd></>}
        {record.limited_by_rule?.length > 0 && (
          <>
            <dt>只算了你看得到的行</dt>
            <dd>{record.limited_by_rule.map((l) => <span className="block" key={l.type}>{l.name}：行规则限制了行（{l.rule}），数是按这些行算的</span>)}</dd>
          </>
        )}
      </dl>
      {record.steps.length > 0 && (
        <details className="trace">
          <summary>查看步骤</summary>
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

function Saved({ id, mayBuild }) {
  const [state] = useLoad(() => getAnswer(id), [id]);
  const r = state.data;
  if (state.status === "error") return <p className="error">{state.missing ? "没有这条问题" : state.error}</p>;
  if (!r) return <p className="muted">加载中</p>;
  return (
    <section className="turn">
      <h2 className="question">{r.question}</h2>
      <p className="muted small">{timeText(r.asked_at)}</p>
      {r.withheld ? <p className="warn">{r.reason}</p> : (
        <>
          {isAnswer(r) ? <Answer record={r} /> : <Refusal record={r} mayBuild={mayBuild} />}
          <Basis record={r} />
        </>
      )}
    </section>
  );
}

export function QaPage({ route }) {
  const mayBuild = canBuild(useAuth().user);
  const [info, reload] = useLoad(getAsk, []);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scope = info.data;
  const ask = async (e) => {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const saved = await askQuestion(text);
      setText("");
      reload();
      window.location.hash = `#/qa/${saved.id}`;
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };
  return (
    <main className="page">
      <h1 tabIndex={-1}>问答</h1>
      {info.status === "error" && <p className="error">{info.error}</p>}
      <div className="qa">
        <aside className="history" aria-label="我问过的问题">
          <h2 className="small">我问过的</h2>
          {scope && scope.history.length === 0 && <p className="muted small">还没有</p>}
          {scope?.history.map((h) => (
            <a key={h.id} href={`#/qa/${h.id}`} aria-current={h.id === route.id ? "page" : undefined} className={h.id === route.id ? "active" : ""}>
              {h.question}
              <span className="muted small block">{timeText(h.asked_at)} {statusText(h.status)}</span>
            </a>
          ))}
        </aside>
        <section>
          {scope && (
            <details className="scope">
              <summary>{scopeText(scope)}</summary>
              <p className="muted">{scope.types.length ? scope.types.map((t) => t.name).join("、") : "还没有已确认的对象类型：先到对象类型页确认"}</p>
              {scope.views?.length > 0 && <p className="muted">视图：{scope.views.map((v) => v.name).join("、")}</p>}
              {scope.left_out.length > 0 && (
                <>
                  <p className="muted" style={{ marginTop: 8 }}>不在范围里：</p>
                  <ul className="named">
                    {scope.left_out.map((d) => <li key={d.id}><a href={definitionHref(d.id, d.type)}>{d.name}</a> <State item={d} /></li>)}
                  </ul>
                </>
              )}
            </details>
          )}
          <form className="ask" onSubmit={ask}>
            <input type="text" aria-label="问题" value={text} maxLength={300} placeholder="问一个问题" disabled={busy} onChange={(e) => setText(e.target.value)} />
            <button className="primary" type="submit" disabled={busy || !text.trim()}>提问</button>
          </form>
          <p className="hint">模型只看到类型、属性、含义，以及取值不多又重复出现的列的取值，看不到数据行。</p>
          {busy && <p className="muted" role="status">正在回答，通常几秒到半分钟</p>}
          {error && <p className="error" role="alert">{error}</p>}
          {route.id && <Saved key={route.id} id={route.id} mayBuild={mayBuild} />}
        </section>
      </div>
    </main>
  );
}
