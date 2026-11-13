import React, { useState } from "react";
import { confirmItem, getRelation, getRelationLog, getRelations } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText } from "./format.js";
import { CARDINALITY_LABEL, connectedText, keyPairText, waitingText } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { confirmersText, logText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

export function RelationsPage() {
  const [state, reload] = useLoad(getRelations, []);
  const mayBuild = canBuild(useAuth().user);
  const relations = state.data ?? [];
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>关系</h1>
        {mayBuild && <div className="head-actions"><a className="button primary" href={hrefFor({ page: "relationnew" })}>新建关系</a></div>}
      </div>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !relations.length && <p className="muted">还没有关系。{mayBuild ? "从两个对象类型新建一个，保存时会按全部数据数出有多少行连得上。" : "建设者确认后会出现在这里。"}</p>}
      {relations.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>关系</th><th>基数</th><th className="num">连上的行</th><th>状态</th><th>确认人</th></tr>
            </thead>
            <tbody>
              {relations.map((r) => (
                <tr key={r.id}>
                  <td><a href={hrefFor({ page: "relation", id: r.id })}>{r.from_name} → {r.to_name}</a> <span className="muted small">{r.name}</span></td>
                  <td>{CARDINALITY_LABEL[r.cardinality]}</td>
                  <td className="num">{connectedText(r.numbers)}</td>
                  <td><State item={r} /></td>
                  <td>{r.confirmed_by ?? <span className="faint">没有</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function RowsTable({ table, markColumn }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i}>{row.map((v, j) => <td key={j} className={table.columns[j] === markColumn ? "warn" : ""}>{v ?? <span className="faint">空</span>}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Check({ r }) {
  const c = r.check;
  if (c.problems.length) return <div className="reason"><strong>现在查不了</strong>{c.problems.map((p, i) => <p key={i}>{p}</p>)}</div>;
  const n = c.numbers;
  const share = n.rows ? (n.matched / n.rows) * 100 : 0;
  return (
    <>
      <div className="connected">
        <span className="big">{connectedText(n)}</span>
        <span className="muted"> 行连上（{c.many.dataset} 第 {c.many.version} 版 → {c.one.dataset} 第 {c.one.version} 版）</span>
      </div>
      <div className="bar" aria-hidden="true"><span style={{ width: `${share}%` }} /></div>
      {r.anchored && r.state === "confirmed" && <p className="muted small">确认时是 {connectedText(r.anchored.numbers)}</p>}
      {n.unmatched > 0 && (
        <>
          <h2 className="section">没连上的行 {n.unmatched} 行</h2>
          <p className="muted small" style={{ marginBottom: 8 }}>
            {c.unmatched_keys} 个“{c.many.column}”在 {c.one.dataset} 里找不到：{c.samples.map((s) => `${s.key}（${s.rows} 行）`).join("、")}
            {c.if_trimmed > 0 && `；其中 ${c.if_trimmed} 行去掉空格、忽略大小写后能对上`}
          </p>
          <RowsTable table={c.unmatched_rows} markColumn={c.many.column} />
          {n.unmatched > c.unmatched_rows.rows.length && <p className="muted small" style={{ marginTop: 4 }}>只列出前 {c.unmatched_rows.rows.length} 行</p>}
        </>
      )}
      {c.empty > 0 && <p className="warn" style={{ marginTop: 12 }}>{c.empty} 行的“{c.many.column}”是空的，没有连任何{c.one.name}</p>}
      {c.fanout.keys > 0 && (
        <>
          <h2 className="section">重复的键 {c.fanout.keys} 个</h2>
          <p className="muted small" style={{ marginBottom: 8 }}>
            {c.one.dataset} 里“{c.one.column}”有这些值重复：{c.fanout.samples.map((s) => `${s.key}（${s.rows} 次）`).join("、")}。
            连上它们的 {c.fanout.source_rows} 行会各多出一行（共多 {c.fanout.extra_rows} 行），按{c.one.name}汇总时会重复算。
          </p>
          <RowsTable table={c.fanout.rows} markColumn={c.one.column} />
        </>
      )}
      {n.many_repeats > 0 && <p className="warn" style={{ marginTop: 12 }}>一对一不成立：{c.many.dataset} 里“{c.many.column}”有 {n.many_repeats} 个值出现了不止一次</p>}
      {n.unmatched === 0 && c.fanout.keys === 0 && n.many_repeats === 0 && <p className="muted" style={{ marginTop: 12 }}>每一行都连上了，{c.one.dataset} 里“{c.one.column}”没有重复。</p>}
    </>
  );
}

export function RelationPage({ route }) {
  const { id } = route;
  const [state, reload] = useLoad(() => getRelation(id), [id]);
  const [log] = useLoad(() => getRelationLog(id), [id, state.data?.version]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const mayBuild = canBuild(useAuth().user);
  const r = state.data;
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmItem(`relation:${id}`, r.version, r.check.signature);
    } catch (e) {
      setError(e.message);
    }
    reload();
    setBusy(false);
  };
  return (
    <main className="page">
      <a className="back" href="#/relations">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        关系
      </a>
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !r && <p className="muted">加载中</p>}
      {r && (
        <>
          <div className="page-head">
            <h1 tabIndex={-1}>{r.from_name} → {r.to_name} <span className="muted id">{r.id}</span> <State item={r} /></h1>
            {mayBuild && (
              <div className="head-actions">
                <a className="button secondary" href={hrefFor({ page: "relationedit", id })}>修改</a>
                {r.can_confirm && <button className="primary" onClick={confirm} disabled={busy}>确认这个关系</button>}
              </div>
            )}
          </div>
          {error && <p className="error">{error}</p>}
          <p className="facts">
            <span>{CARDINALITY_LABEL[r.cardinality]}</span>
            <span>{keyPairText(r)}</span>
            {r.description && <span>{r.description}</span>}
          </p>
          {stateLine(r, "这个关系") && <p className="muted">{stateLine(r, "这个关系")}</p>}
          {waitingText(r) && (
            <p className="warn">
              {waitingText(r)}：{r.waiting_on.map((t, i) => <span key={t.id}>{i > 0 && "、"}<a href={hrefFor({ page: "type", id: t.id, tab: "props" })}>{t.name}</a></span>)}
            </p>
          )}
          {confirmersText(r) && <p className="muted small">{confirmersText(r)}</p>}
          {r.state === "needs_look" && r.reason && (
            <div className="reason">
              <strong>为什么需要再看</strong>
              <p>{r.reason}</p>
            </div>
          )}
          {r.state === "rejected" && r.reason && (
            <div className="reason">
              <strong>退回的理由</strong>
              <p>{r.reason}</p>
            </div>
          )}
          <div style={{ marginTop: 20 }}><Check r={r} /></div>
          <h2 className="section">日志</h2>
          {log.status === "ready" && (
            <div className="table-wrap">
              <table className="log">
                <thead><tr><th>时间</th><th>谁</th><th>发生了什么</th></tr></thead>
                <tbody>
                  {log.data.map((e, i) => {
                    const t = logText(e);
                    return <tr key={i}><td className="keep">{timeText(e.at)}</td><td className="keep">{t.who}</td><td>{t.text}</td></tr>;
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  );
}
