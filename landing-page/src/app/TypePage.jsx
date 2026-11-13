import React, { useState } from "react";
import { rowKey } from "./actionModel.js";
import { TypeActions, RunAction } from "./TypeActions.jsx";
import { confirmType, getActions, getType, getTypeLog, getTypeObjects, proposeMeanings, setValuesHidden } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText, typeLabel } from "./format.js";
import { waitingText } from "./relationModel.js";
import { TYPE_TABS, TYPE_TAB_LABEL, hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { TypeViews } from "./TypeViews.jsx";
import { codeCell, confirmersText, logText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

/** What stands behind a state, in one place: the line, who could confirm, and why it needs another look. */
function Standing({ item, noun }) {
  const line = stateLine(item, noun);
  return (
    <>
      {line && <p className="muted">{line}</p>}
      {waitingText(item) && <p className="warn">{waitingText(item)}</p>}
      {confirmersText(item) && <p className="muted small">{confirmersText(item)}</p>}
      {item.state === "needs_look" && item.reason && (
        <div className="reason">
          <strong>为什么需要再看</strong>
          <p>{item.reason}</p>
        </div>
      )}
    </>
  );
}

/** The meanings of one code column: the values as the data has them, the meaning written for each, and the two things a person can do with them. */
function Meanings({ type, prop, mayBuild, onChanged }) {
  const m = prop.meanings;
  const saved = Object.fromEntries(m.values.map((v) => [v.value, v.label]));
  const [draft, setDraft] = useState(saved);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const changed = m.values.some((v) => (draft[v.value] ?? "") !== v.label);
  const act = async (run) => {
    setBusy(true);
    setError("");
    try {
      await run();
      onChanged();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  const propose = () => act(() => proposeMeanings(type.id, prop.column, m.values.map((v) => ({ value: v.value, label: draft[v.value] ?? "" }))));
  const confirm = () => act(() => confirmType(type.id, m.version, m.seen, prop.column));
  const hasThen = m.state === "needs_look";   // what the rows were when it was confirmed matters only once the data has moved
  return (
    <section>
      <h2 className="section">{prop.name}的含义 <State item={m} /></h2>
      <Standing item={m} noun="这组含义" />
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>取值</th><th>含义</th>{hasThen && <th className="num">上次确认时行数</th>}<th className="num">现在行数</th></tr>
          </thead>
          <tbody>
            {m.values.map((v) => (
              <tr key={v.value}>
                <td>{v.value}</td>
                <td>
                  {mayBuild ? (
                    <input type="text" aria-label={`${prop.column} = ${v.value} 的含义`} value={draft[v.value] ?? ""} placeholder={v.in_data ? "还没有含义" : "数据里已经没有这个值，清空它"}
                      onChange={(e) => setDraft({ ...draft, [v.value]: e.target.value })} />
                  ) : (v.label || <span className="faint">含义未确认</span>)}
                </td>
                {hasThen && <td className="num">{v.rows_at_confirmation ?? <span className="faint">—</span>}</td>}
                <td className="num">{v.rows ?? <span className="faint">没有</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {mayBuild && (
        <div className="inline">
          {(changed || m.state === "needs_look") && <button className="secondary" onClick={propose} disabled={busy}>提出这组含义</button>}
          {m.can_confirm && !changed && <button className="primary" onClick={confirm} disabled={busy}>确认这组含义</button>}
          {m.state === "needs_look" && <span className="muted small">提出后要另一位构建者确认</span>}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function Properties({ type, mayBuild, reload }) {
  const [error, setError] = useState("");
  const hide = async (column, on) => {
    setError("");
    try {
      await setValuesHidden(type.id, column, on);
      reload();
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead><tr><th>名称</th><th>来源列</th><th>类型</th><th>主键</th>{mayBuild && <th>问答</th>}</tr></thead>
          <tbody>
            {type.properties.map((p) => (
              <tr key={p.column}>
                <td>{p.name}</td>
                <td className="muted">{p.column}</td>
                <td>{p.enum ? <>{typeLabel(p.type)}代码 {p.meanings.state && <State item={p.meanings} />}</> : typeLabel(p.type)}</td>
                <td>{p.key ? "是" : ""}</td>
                {mayBuild && (
                  <td>
                    {p.key ? <span className="faint">不发取值</span> : (
                      <label className="check">
                        <input type="checkbox" checked={p.hide_values} onChange={(e) => hide(p.column, e.target.checked)} aria-label={`${p.name}：不把取值发给模型`} />
                        不发取值
                      </label>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="error">{error}</p>}
      {type.properties.filter((p) => p.enum).map((p) => (
        <Meanings key={`${p.column}-${p.meanings.version ?? 0}-${p.meanings.state}`} type={type} prop={p} mayBuild={mayBuild} onChanged={reload} />
      ))}
    </>
  );
}

function Objects({ id, pageNo, mayBuild }) {
  const [state, reload] = useLoad(() => getTypeObjects(id, pageNo), [id, pageNo]);
  const [actions] = useLoad(() => (mayBuild ? getActions(id) : Promise.resolve({ actions: [] })), [id, mayBuild]);
  const [running, setRunning] = useState(null);   // {action, key, text}: the form open for one object
  const o = state.data;
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!o) return <p className="muted">加载中</p>;
  const at = (n) => hrefFor({ page: "type", id, tab: "objects", pageNo: n });
  const runnable = (actions.data?.actions ?? []).filter((a) => a.state === "confirmed");
  return (
    <>
      <p className="muted small" style={{ marginBottom: 8 }}>
        来自 {o.dataset} 第 {o.dataset_version} 版，共 {o.total} 行，第 {o.total ? (o.page - 1) * o.limit + 1 : 0}–{Math.min(o.page * o.limit, o.total)} 行
        {o.rows_limited && "；行规则限制了你能看到的行"}
      </p>
      {running && <RunAction key={`${running.action.id}/${running.text}`} action={running.action} objectKey={running.key} objectText={running.text} onDone={reload} onCancel={() => setRunning(null)} />}
      <div className="table-wrap tall">
        <table>
          <thead><tr>{o.columns.map((c) => <th key={c.column}>{c.name}</th>)}{runnable.length > 0 && <th />}</tr></thead>
          <tbody>
            {o.rows.map((row, r) => (
              <tr key={r}>
                {row.map((v, i) => {
                  const column = o.columns[i].column;
                  if (!o.enums[column]) return <td key={i} className="cell" title={v ?? undefined}>{v ?? <span className="faint">—</span>}</td>;
                  const cell = codeCell(v, o.enums[column]);
                  return <td key={i}>{cell.value}{cell.note && <span className="muted small"> {cell.note}</span>}</td>;
                })}
                {runnable.length > 0 && (
                  <td className="keep">
                    {runnable.map((a) => <button key={a.id} className="plain" onClick={() => setRunning({ action: a, ...rowKey(o.columns, row) })}>{a.name}</button>)}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {o.pages > 1 && (
        <nav className="pager" aria-label="对象分页">
          {o.page > 1 ? <a href={at(o.page - 1)}>上一页</a> : <span className="faint">上一页</span>}
          <span>{o.page} / {o.pages}</span>
          {o.page < o.pages ? <a href={at(o.page + 1)}>下一页</a> : <span className="faint">下一页</span>}
        </nav>
      )}
    </>
  );
}

function Log({ id }) {
  const [state] = useLoad(() => getTypeLog(id), [id]);
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">加载中</p>;
  return (
    <div className="table-wrap">
      <table className="log">
        <thead><tr><th>时间</th><th>谁</th><th>发生了什么</th></tr></thead>
        <tbody>
          {state.data.map((e, i) => {
            const t = logText(e);
            return <tr key={i}><td className="keep">{timeText(e.at)}</td><td className="keep">{t.who}</td><td>{t.text}</td></tr>;
          })}
        </tbody>
      </table>
    </div>
  );
}

export function TypePage({ route }) {
  const { id, tab, pageNo } = route;
  const [state, reload] = useLoad(() => getType(id), [id]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const mayBuild = canBuild(useAuth().user);
  const t = state.data;
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmType(id, t.version, t.seen);
      reload();
    } catch (e) {
      setError(e.message);
      if (e.code === 409) reload();   // what was read has moved: show what is there now
    }
    setBusy(false);
  };
  return (
    <main className="page">
      <a className="back" href="#/types">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        对象类型
      </a>
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !t && <p className="muted">加载中</p>}
      {t && (
        <>
          <div className="page-head">
            <h1 tabIndex={-1}>{t.name} <span className="muted id">{t.id}</span> <State item={t} /></h1>
            {mayBuild && (
              <div className="head-actions">
                <a className="button secondary" href={hrefFor({ page: "typeedit", id })}>修改</a>
                {t.can_confirm && <button className="primary" onClick={confirm} disabled={busy}>确认这个对象类型</button>}
              </div>
            )}
          </div>
          {error && <p className="error">{error}</p>}
          <p className="facts">
            <span>来源 <a href={hrefFor({ page: "dataset", name: t.dataset, tab: "fields" })}>{t.dataset}</a> 第 {t.dataset_version} 版</span>
            <span>{t.rows} 个对象</span>
            {t.description && <span>{t.description}</span>}
            {t.visible_to && t.visible_to !== "everyone" && <span>只有{t.visible_to.length ? t.visible_to.join("、") : "管理员"}看得到</span>}
          </p>
          <Standing item={t} noun="这个对象类型" />
          <nav className="tabs" aria-label="对象类型的页面" style={{ marginTop: 16 }}>
            {TYPE_TABS.filter((k) => k !== "actions" || mayBuild).map((k) => (
              <a key={k} href={hrefFor({ page: "type", id, tab: k })} aria-current={k === tab ? "page" : undefined} className={k === tab ? "active" : ""}>{TYPE_TAB_LABEL[k]}</a>
            ))}
          </nav>
          {tab === "props" && <Properties type={t} mayBuild={mayBuild} reload={reload} />}
          {tab === "views" && <TypeViews type={t} mayBuild={mayBuild} />}
          {tab === "actions" && mayBuild && <TypeActions type={t} mayBuild={mayBuild} />}
          {tab === "objects" && <Objects id={id} pageNo={pageNo} mayBuild={mayBuild} />}
          {tab === "log" && <Log id={id} />}
        </>
      )}
    </main>
  );
}
