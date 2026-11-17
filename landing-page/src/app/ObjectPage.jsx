import React, { useState } from "react";
import { actionFits, rowKey } from "./actionModel.js";
import { Standing } from "./ChartView.jsx";
import { getActions, getExploreObject } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { queryToParam } from "./explorerModel.js";
import { hrefFor } from "./routeModel.js";
import { RunAction } from "./TypeActions.jsx";
import { OUTSIDE_NOTE, codeCell } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

/** One object: its values, what is related to it (with the way across to the whole set), and the actions that may be run on it. */
export function ObjectPage({ route }) {
  const { id, n } = route;
  const mayBuild = canBuild(useAuth().user);
  const [state, reload] = useLoad(() => getExploreObject(id, n), [id, n]);
  const [actions] = useLoad(() => (mayBuild ? getActions(id) : Promise.resolve({ actions: [] })), [id, mayBuild]);
  const [running, setRunning] = useState(null);
  const o = state.data;
  const back = hrefFor({ page: "type", id, tab: "objects", pageNo: 1 });
  const runnable = o ? (actions.data?.actions ?? []).filter((a) => a.state === "confirmed" && a.can_submit !== false && actionFits(a, o.columns, o.row)) : [];
  return (
    <main className="page">
      <a className="back" href={back}>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        {o?.type.name ?? "对象"}
      </a>
      {state.status === "error" && <p className="error">{state.error}</p>}
      {!o && state.status !== "error" && <p className="muted">加载中</p>}
      {o && (
        <>
          <div className="page-head">
            <h1 tabIndex={-1}>{o.text || `第 ${o.n} 行`}</h1>
            {runnable.length > 0 && <div className="head-actions">{runnable.map((a) => <button key={a.id} className="secondary" onClick={() => setRunning(a)}>{a.name}</button>)}</div>}
          </div>
          <p className="facts"><span>{o.type.name}，来自 {o.dataset} 第 {o.dataset_version} 版</span></p>
          <Standing standing={o.standing} />
          {running && <RunAction key={running.id} action={running} objectKey={rowKey(o.columns, o.row).key} objectText={o.text} onDone={reload} onCancel={() => setRunning(null)} />}
          <dl className="defs wide-defs">
            {o.columns.map((c, i) => {
              const cell = codeCell(o.row[i], o.enums[c.column]);
              return (
                <React.Fragment key={c.column}>
                  <dt>{c.name}{c.derived && <span className={c.confirmed ? " small" : " muted small"}>{c.confirmed ? "（派生）" : "（派生，未确认）"}</span>}</dt>
                  <dd>{o.row[i] == null || o.row[i] === "" ? <span className="faint" title={o.outside?.includes(i) ? OUTSIDE_NOTE : undefined}>—{o.outside?.includes(i) && <span className="small"> {OUTSIDE_NOTE}</span>}</span> : <>{cell.value}{o.enums[c.column] && cell.note && <span className="muted small"> {cell.note}</span>}</>}</dd>
                </React.Fragment>
              );
            })}
          </dl>
          <h2 className="section">关联的对象</h2>
          {o.related.length === 0 && <p className="muted">这个对象类型还没有可看的关系。</p>}
          {o.related.map((r) => (
            <section key={`${r.id}-${r.side}`} className="related">
              <h3 className="section-title">{r.other_name} {r.count} <span className="muted small">{r.name}{r.confirmed ? "" : "，关系未确认"}</span></h3>
              {r.count === 0 ? <p className="muted">没有关联的{r.other_name}</p> : (
                <>
                  <p className="related-list">
                    {r.objects.map((x) => <a key={x.n} href={hrefFor({ page: "object", id: r.other, n: x.n })}>{x.text}</a>)}
                    {r.count > r.objects.length && <span className="muted">等 {r.count} 个</span>}
                  </p>
                  <a href={hrefFor({ page: "type", id: r.other, tab: "objects", pageNo: 1, q: queryToParam(r.query) })}>转到关联的{r.other_name}（{r.count}）</a>
                </>
              )}
            </section>
          ))}
        </>
      )}
    </main>
  );
}
