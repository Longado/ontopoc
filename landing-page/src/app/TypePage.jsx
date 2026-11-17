import React, { useState } from "react";
import { Explorer } from "./Explorer.jsx";
import { TypeActions } from "./TypeActions.jsx";
import { confirmType, getTypeUses, getType, getTypeLog, proposeMeanings, setValuesHidden } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText, typeLabel } from "./format.js";
import { ageText } from "./graphModel.js";
import { waitingText } from "./relationModel.js";
import { TYPE_TABS, TYPE_TAB_LABEL, hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { TypeDerived } from "./TypeDerived.jsx";
import { TypeViews } from "./TypeViews.jsx";
import { confirmersText, limitedNote, logText, meaningsSummary, reconfirmText, stateLine, tabCounts, typeSub, usesSummary } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";

const TYPE_CRUMBS = (name) => [{ label: "业务对象" }, { label: "对象类型", href: "#/types" }, { label: name }];

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

/** The meanings of one code column, as a section of their own: read as a table first; 修改含义 turns the meanings into inputs with 提出 and 取消. */
function Meanings({ type, prop, mayBuild, onChanged }) {
  const m = prop.meanings;
  const saved = Object.fromEntries(m.values.map((v) => [v.value, v.label]));
  const [draft, setDraft] = useState(saved);
  const [editing, setEditing] = useState(false);
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
  const cancel = () => {
    setDraft(saved);
    setEditing(false);
  };
  const hasThen = m.state === "needs_look";   // what the rows were when it was confirmed matters only once the data has moved
  const editable = mayBuild && editing;
  return (
    <section className="meanings" aria-label={`${prop.name}的含义`}>
      <div className="section-head">
        <h2 className="section">{prop.name}的含义 <State item={m} /></h2>
        <span className="muted small">{meaningsSummary(m)}</span>
        {mayBuild && !editing && <button className="secondary" onClick={() => setEditing(true)}>修改含义</button>}
      </div>
      <Standing item={m} noun="这组含义" />
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>取值</th><th>含义</th>{hasThen && !m.limited_note && <th className="num">上次确认时行数</th>}{!m.limited_note && <th className="num">现在行数</th>}</tr>
          </thead>
          <tbody>
            {m.values.map((v) => (
              <tr key={v.value}>
                <td>{v.value}</td>
                <td>
                  {editable ? (
                    <input type="text" aria-label={`${prop.column} = ${v.value} 的含义`} value={draft[v.value] ?? ""} placeholder={v.in_data ? "还没有含义" : "数据里已经没有这个值，清空它"}
                      onChange={(e) => setDraft({ ...draft, [v.value]: e.target.value })} />
                  ) : (v.label || <span className="faint">含义未确认</span>)}
                </td>
                {hasThen && !m.limited_note && <td className="num">{v.rows_at_confirmation ?? <span className="faint">—</span>}</td>}
                {!m.limited_note && <td className="num">{v.rows ?? <span className="faint">没有</span>}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {m.limited_note && <p className="muted small">{m.limited_note}</p>}
      {mayBuild && (
        <div className="inline">
          {editing && <button className="primary" onClick={propose} disabled={busy || !changed}>提出这组含义</button>}
          {editing && <button className="plain" onClick={cancel} disabled={busy}>取消</button>}
          {editing && !changed && <span className="muted small">改了含义才能提出</span>}
          {!editing && m.state === "needs_look" && <button className="secondary" onClick={propose} disabled={busy}>提出这组含义</button>}
          {!editing && m.can_confirm && !changed && <button className="primary" onClick={confirm} disabled={busy}>确认这组含义</button>}
          {(editing || m.state === "needs_look") && <span className="muted small">提出后要另一位建设者确认</span>}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

const QA_HELP = "问答会把这一列的具体取值发给模型来写答案。不勾选时，模型只看到列名和统计，看不到具体的值，适合姓名、电话这类敏感的列。勾选或取消马上生效，不用再保存。";

function Properties({ type, mayBuild, reload }) {
  const [error, setError] = useState("");
  const allow = async (column, on) => {
    setError("");
    try {
      await setValuesHidden(type.id, column, !on);   // the box says what is allowed; the service keeps what is hidden
      reload();
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>名称</th><th>来源列</th><th>类型</th><th>主键</th>
              {mayBuild && <th>允许问答读取取值 <span className="help" tabIndex={0} role="img" aria-label={QA_HELP} title={QA_HELP}>?</span></th>}
            </tr>
          </thead>
          <tbody>
            {type.properties.map((p) => (
              <tr key={p.column}>
                <td>{p.name}{p.fan && <span className="warn small block">{p.fan}</span>}</td>
                <td className="muted">{p.column}</td>
                <td>{p.enum ? <>{typeLabel(p.type)}代码 {p.meanings.state ? <State item={p.meanings} /> : <span className="muted small">含义未写</span>}</> : typeLabel(p.type)}</td>
                <td>{p.key ? "是" : ""}</td>
                {mayBuild && (
                  <td>
                    {p.key ? <span className="faint">主键不发</span> : (
                      <label className="check">
                        <input type="checkbox" checked={!p.hide_values} onChange={(e) => allow(p.column, e.target.checked)} aria-label={`${p.name}：允许问答读取取值`} />
                        {p.hide_values ? "不发给模型" : "可以发"}
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

const USE_HREF = {
  views: (id) => hrefFor({ page: "type", id, tab: "views" }),
  derived: (id) => hrefFor({ page: "type", id, tab: "derived" }),
  actions: (id) => hrefFor({ page: "type", id, tab: "actions" }),
  relations: (_id, item) => hrefFor({ page: "relation", id: item.id }),
  answers: (_id, item) => hrefFor({ page: "qa", id: item.id }),
};

/** 用到它的: one line with a count for each kind; it opens to the names. Kinds nothing uses are not listed. */
function Uses({ id, uses }) {
  if (!uses?.used_by.length) return null;
  return (
    <details className="uses">
      <summary><span className="muted">用到它的</span> {usesSummary(uses)}</summary>
      <dl className="defs">
        {uses.used_by.map((u) => (
          <React.Fragment key={u.kind}>
            <dt>{u.label} {u.count}</dt>
            <dd>{u.items.map((item, i) => <span key={item.id}>{i > 0 && "、"}<a href={USE_HREF[u.kind](id, item)}>{item.name}</a>{item.state && item.state !== "confirmed" && <span className="muted small"> {item.state === "needs_look" ? "需再看" : "待确认"}</span>}</span>)}</dd>
          </React.Fragment>
        ))}
      </dl>
    </details>
  );
}

export function TypePage({ route }) {
  const { id, tab } = route;
  const [state, reload] = useLoad(() => getType(id), [id]);
  const [uses] = useLoad(() => (state.data?.waiting ? Promise.resolve(null) : getTypeUses(id)), [id, state.data?.version, state.data?.waiting]);   // a waiting type has no uses to show
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
  const uploaded = uses.data?.data.uploaded_at ? `${ageText(uses.data.data.uploaded_at)}${uses.data.data.who ? `，${uses.data.data.who}` : ""}` : "";
  const counts = t && !t.waiting ? tabCounts(t, uses.data) : {};
  return (
    <main className="page">
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !t && <p className="muted">加载中</p>}
      {t?.waiting && (
        <>
          <PageHeader crumbs={TYPE_CRUMBS(t.name)} title={t.name} status={<State item={t} />} />
          <p className="warn">{reconfirmText(t.waiting_for)}</p>
          <p className="muted">确认之前不显示它的属性和对象。</p>
        </>
      )}
      {t && !t.waiting && (
        <>
          <PageHeader crumbs={TYPE_CRUMBS(t.name)} title={t.name} status={<State item={t} />} sub={typeSub(t, uploaded)}
            actions={mayBuild && (
              <>
                {!t.columns_kept && <a className="button secondary" href={hrefFor({ page: "typeedit", id })}>修改</a>}
                {t.can_confirm && <button className="primary" onClick={confirm} disabled={busy}>确认这个对象类型</button>}
              </>
            )} />
          {error && <p className="error">{error}</p>}
          <div className="type-notes">
            {t.description && <p>{t.description}</p>}
            {t.columns_kept > 0 && <p className="faint small">有 {t.columns_kept} 个属性不让你看</p>}
            {t.visible_to && t.visible_to !== "everyone" && <p className="muted small">只有{t.visible_to.length ? t.visible_to.join("、") : "管理员"}看得到</p>}
            {!t.rows_limited && !t.columns_kept && <p className="small"><a href={hrefFor({ page: "dataset", name: t.dataset, tab: "fields" })}>看来源数据集 {t.dataset}</a></p>}
            {limitedNote(t) && <p className="muted small">{limitedNote(t)}</p>}
            <Standing item={t} noun="这个对象类型" />
            <Uses id={id} uses={uses.data} />
          </div>
          <nav className="tabs" aria-label="对象类型的页面">
            {TYPE_TABS.filter((k) => k !== "actions" || mayBuild).map((k) => (
              <a key={k} href={hrefFor({ page: "type", id, tab: k })} aria-current={k === tab ? "page" : undefined} className={k === tab ? "active" : ""}>
                {TYPE_TAB_LABEL[k]}{counts[k] != null && <span className="tab-count">{counts[k]}</span>}
              </a>
            ))}
          </nav>
          {tab === "props" && <Properties type={t} mayBuild={mayBuild} reload={reload} />}
          {tab === "derived" && <TypeDerived type={t} mayBuild={mayBuild} />}
          {tab === "views" && <TypeViews type={t} mayBuild={mayBuild} />}
          {tab === "actions" && mayBuild && <TypeActions type={t} mayBuild={mayBuild} />}
          {tab === "objects" && <Explorer key={`${id}|${route.q ?? ""}`} id={id} route={route} />}
          {tab === "log" && <Log id={id} />}
        </>
      )}
    </main>
  );
}
