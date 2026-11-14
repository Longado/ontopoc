import React, { useEffect, useState } from "react";
import { ChartResult, Standing } from "./ChartView.jsx";
import { deleteBoard, getBoard, getBoardData, getBoards } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { SCOPE_LABEL, expiryText, refreshText, scopeText, shareLink, unavailableText } from "./boardModel.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

/** The components of a board as cards: each with its title, its number or chart (grey with the reason when what it stands on is not confirmed) and its caliber. */
export function BoardCards({ data }) {
  return (
    <div className="board-grid">
      {data.components.map((c) => (
        <section key={c.id} className={`board-card kind-${c.chart.kind}`}>
          <h2 className="item-title">{c.title}</h2>
          {c.status !== "ok" ? <p className="muted">{unavailableText(c)}</p> : (
            <>
              <ChartResult result={c.result} withStanding={false} />
              {c.result.standing.lines.length ? <Standing standing={c.result.standing} /> : (
                <div className="standing">
                  <p className="muted small">口径：全部行{c.result.query.filters.length ? `，加 ${c.result.query.filters.length} 个条件` : ""}</p>
                  {!c.result.standing.confirmed && <Standing standing={{ ...c.result.standing, lines: [] }} />}
                </div>
              )}
            </>
          )}
        </section>
      ))}
    </div>
  );
}

function BarPicks({ bar, picked, setPicked }) {
  if (!bar.length) return null;
  return (
    <div className="inline wide board-bar" role="group" aria-label="筛选">
      {bar.map((f) => (
        <label key={f.field} className="field">
          <span className="caption">{f.label}</span>
          {f.options ? (
            <Select label={f.label} value={picked[f.field] ?? ""} onChange={(v) => setPicked({ ...picked, [f.field]: v })}>
              <option value="">全部</option>
              {f.options.map((o) => <option key={o.value} value={o.value}>{o.label ? `${o.value} ${o.label}` : o.value}</option>)}
            </Select>
          ) : <input type="text" aria-label={f.label} value={picked[f.field] ?? ""} onChange={(e) => setPicked({ ...picked, [f.field]: e.target.value })} />}
        </label>
      ))}
    </div>
  );
}

export function BoardPage({ route }) {
  const { id } = route;
  const { user } = useAuth();
  const [picked, setPicked] = useState({});
  const [tick, setTick] = useState(0);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [board] = useLoad(() => getBoard(id), [id]);
  const [data] = useLoad(() => getBoardData(id, picked), [id, JSON.stringify(picked), tick]);
  const seconds = board.data?.refresh_seconds ?? 0;
  useEffect(() => {
    if (!seconds) return undefined;
    const timer = setInterval(() => setTick((n) => n + 1), seconds * 1000);
    return () => clearInterval(timer);
  }, [seconds]);
  const b = board.data;
  const remove = async () => {
    if (!window.confirm(`删除看板「${b.name}」？`)) return;
    try {
      await deleteBoard(id);
      window.location.hash = "#/boards";
    } catch (e) {
      setError(e.message);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareLink(window.location.origin, id));
      setCopied(true);
    } catch {
      setError("复制没成功，请手动复制地址栏里的链接");
    }
  };
  return (
    <main className="page">
      <a className="back" href="#/boards">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        看板
      </a>
      {board.status === "error" && <p className="error">{board.error}</p>}
      {b && (
        <>
          <div className="page-head">
            <h1 tabIndex={-1}>{b.name}</h1>
            <div className="head-actions">
              <button className="secondary" onClick={copy}>{copied ? "已复制链接" : "复制分享链接"}</button>
              <button className="secondary" onClick={() => setTick((n) => n + 1)}>刷新</button>
              {b.may_change && canBuild(user) && <a className="button secondary" href={`#/boards/${id}/edit`}>修改</a>}
              {b.may_change && canBuild(user) && <button className="plain" onClick={remove}>删除</button>}
            </div>
          </div>
          <p className="facts">
            <span>主人 {b.owner}</span>
            <span>发布给 {scopeText(b)}</span>
            <span>{expiryText(b)}</span>
            <span>{refreshText(b.refresh_seconds)}</span>
          </p>
          <p className="muted small">{b.sign_in_note}</p>
          {error && <p className="error">{error}</p>}
        </>
      )}
      {data.status === "error" && <p className="error">{data.error}</p>}
      {data.data && (
        <>
          <p className={data.data.headline.grey.length ? "grey-banner" : "muted small"}>{data.data.headline.text}</p>
          <BarPicks bar={data.data.bar} picked={picked} setPicked={setPicked} />
          <BoardCards data={data.data} />
          <p className="muted small">读于 {timeText(data.data.read_at)}，数字是按你能看到的行算的</p>
        </>
      )}
      {!data.data && data.status === "loading" && <p className="muted">加载中</p>}
    </main>
  );
}

export function BoardsPage() {
  const { user } = useAuth();
  const [state, reload] = useLoad(() => getBoards(), []);
  const boards = state.data?.dashboards ?? [];
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>看板</h1>
        {canBuild(user) && <a className="button primary" href="#/boards/new">新建看板</a>}
      </div>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.data && boards.length === 0 && <p className="muted">{canBuild(user) ? "还没有看板。新建一个，指标和图都从已确认的定义算。" : "还没有人给你发布看板。"}</p>}
      {boards.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>名称</th><th>主人</th><th>发布给</th><th>有效期</th><th className="num">组件</th><th>更新</th></tr></thead>
            <tbody>
              {boards.map((b) => (
                <tr key={b.id}>
                  <td><a href={`#/boards/${b.id}`}>{b.name}</a></td>
                  <td>{b.owner}{b.mine && <span className="muted small"> 我</span>}</td>
                  <td>{SCOPE_LABEL[b.scope]}</td>
                  <td>{expiryText(b)}</td>
                  <td className="num">{b.components}</td>
                  <td>{timeText(b.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
