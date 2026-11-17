import React, { useState } from "react";
import { actionFits, rowKey } from "./actionModel.js";
import { Standing } from "./ChartView.jsx";
import { getActions, getExploreObject } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { queryToParam } from "./explorerModel.js";
import { objectName, relatedCard, unconfirmedNote } from "./objectModel.js";
import { hrefFor } from "./routeModel.js";
import { RunAction } from "./TypeActions.jsx";
import { OUTSIDE_NOTE, codeCell } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";

/** One object: its values, what is related to it (with the way across to the whole set), and the actions that may be run on it. */
export function ObjectPage({ route }) {
  const { id, n } = route;
  const mayBuild = canBuild(useAuth().user);
  const [state, reload] = useLoad(() => getExploreObject(id, n), [id, n]);
  const [actions] = useLoad(() => (mayBuild ? getActions(id) : Promise.resolve({ actions: [] })), [id, mayBuild]);
  const [running, setRunning] = useState(null);
  const o = state.data;
  const back = hrefFor({ page: "type", id, tab: "objects", pageNo: 1 });
  const name = o ? objectName(o.columns, o.row) : "";
  const heading = o ? (o.text || `第 ${o.n} 行`) + (name ? ` · ${name}` : "") : "";
  const runnable = o ? (actions.data?.actions ?? []).filter((a) => a.state === "confirmed" && a.can_submit !== false && actionFits(a, o.columns, o.row)) : [];
  return (
    <main className="page">
      {state.status === "error" && <p className="error">{state.error}</p>}
      {!o && state.status !== "error" && <p className="muted">加载中</p>}
      {o && (
        <>
          <PageHeader crumbs={[{ label: "业务对象" }, { label: "对象类型", href: "#/types" }, { label: o.type.name, href: back }, { label: o.text || `第 ${o.n} 行` }]} title={heading}
            sub={`${o.type.name}，来自 ${o.dataset} 第 ${o.dataset_version} 版`}
            actions={runnable.map((a) => <button key={a.id} className="secondary" onClick={() => setRunning(a)}>{a.name}</button>)} />
          {unconfirmedNote(o.related) && <p className="notice-line">{unconfirmedNote(o.related)} <a href="#/confirm">去待确认</a></p>}
          <Standing standing={o.standing} />
          {running && <RunAction key={running.id} action={running} objectKey={rowKey(o.columns, o.row).key} objectText={o.text} onDone={reload} onCancel={() => setRunning(null)} />}
          <div className="object-layout">
          <div>
          <h2 className="section">属性</h2>
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
          </div>
          <div>
          <h2 className="section">关联的对象</h2>
          {o.related.length === 0 && <p className="muted">这个对象类型还没有可看的关系。</p>}
          {o.related.map((r) => {
            const card = relatedCard(r);
            return (
              <section key={`${r.id}-${r.side}`} className="related">
                <h3 className="section-title">{r.other_name} {r.count} <span className="muted small">{r.name}</span></h3>
                {r.count === 0 ? <p className="muted">没有关联的{r.other_name}</p> : (
                  <>
                    <ul className="related-list">
                      {card.objects.map((x) => <li key={x.n}><a href={hrefFor({ page: "object", id: r.other, n: x.n })}>{x.label}</a></li>)}
                      {card.more && <li className="muted">{card.more}</li>}
                    </ul>
                    <a href={hrefFor({ page: "type", id: r.other, tab: "objects", pageNo: 1, q: queryToParam(r.query) })}>转到关联的{r.other_name}（{r.count}）</a>
                  </>
                )}
              </section>
            );
          })}
          </div>
          </div>
        </>
      )}
    </main>
  );
}
