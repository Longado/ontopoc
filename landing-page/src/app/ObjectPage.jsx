import React, { useState } from "react";
import { SourceValue } from "./SourceValue.jsx";
import { actionFits, rowKey } from "./actionModel.js";
import { Standing } from "./ChartView.jsx";
import { getActions, getExploreObject } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { queryToParam } from "./explorerModel.js";
import { t } from "./i18n/index.js";
import { objectName, relatedCard, unconfirmedNote } from "./objectModel.js";
import { hrefFor } from "./routeModel.js";
import { RunAction } from "./TypeActions.jsx";
import { codeCell, outsideNote } from "./typeModel.js";
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
  const heading = o ? (o.text || t("objects.page.row", { n: o.n })) + (name ? ` · ${name}` : "") : "";
  const runnable = o ? (actions.data?.actions ?? []).filter((a) => a.state === "confirmed" && a.can_submit !== false && actionFits(a, o.columns, o.row)) : [];
  return (
    <main className="page">
      {state.status === "error" && <p className="error">{state.error}</p>}
      {!o && state.status !== "error" && <p className="muted">{t("common.loading")}</p>}
      {o && (
        <>
          <PageHeader crumbs={[{ label: t("objects.page.crumbGroup") }, { label: t("objects.page.crumbTypes"), href: "#/types" }, { label: o.type.name, href: back }, { label: o.text || t("objects.page.row", { n: o.n }) }]} title={heading}
            sub={t("objects.page.sub", { type: o.type.name, dataset: o.dataset, version: o.dataset_version })}
            actions={runnable.map((a) => <button key={a.id} className="secondary" onClick={() => setRunning(a)}>{a.name}</button>)} />
          {unconfirmedNote(o.related) && <p className="notice-line">{unconfirmedNote(o.related)} <a href="#/confirm">{t("objects.page.toQueue")}</a></p>}
          <Standing standing={o.standing} />
          {running && <RunAction key={running.id} action={running} objectKey={rowKey(o.columns, o.row).key} objectText={o.text} onDone={reload} onCancel={() => setRunning(null)} />}
          <div className="object-layout">
          <div>
          <h2 className="section">{t("objects.page.properties")}</h2>
          <dl className="defs wide-defs">
            {o.columns.map((c, i) => {
              const cell = codeCell(o.row[i], o.enums[c.column]);
              return (
                <React.Fragment key={c.column}>
                  <dt>{c.name}{c.derived && <span className={c.confirmed ? " small" : " muted small"}>{c.confirmed ? t("objects.page.derived") : t("objects.page.derivedUnconfirmed")}</span>}</dt>
                  <dd>{o.row[i] == null || o.row[i] === "" ? <span className="faint" title={o.outside?.includes(i) ? outsideNote() : undefined}>—{o.outside?.includes(i) && <span className="small"> {outsideNote()}</span>}</span> : <><SourceValue value={cell.value} />{o.enums[c.column] && cell.note && <span className="muted small"> {cell.note}</span>}</>}</dd>
                </React.Fragment>
              );
            })}
          </dl>
          </div>
          <div>
          <h2 className="section">{t("objects.page.related")}</h2>
          {o.related.length === 0 && <p className="muted">{t("objects.page.noRelations")}</p>}
          {o.related.map((r) => {
            const card = relatedCard(r);
            return (
              <section key={`${r.id}-${r.side}`} className="related">
                <h3 className="section-title">{r.other_name} {r.count} <span className="muted small">{r.name}</span></h3>
                {r.count === 0 ? <p className="muted">{t("objects.page.noneRelated", { other: r.other_name })}</p> : (
                  <>
                    <ul className="related-list">
                      {card.objects.map((x) => <li key={x.n}><a href={hrefFor({ page: "object", id: r.other, n: x.n })}>{x.label}</a></li>)}
                      {card.more && <li className="muted">{card.more}</li>}
                    </ul>
                    <a href={hrefFor({ page: "type", id: r.other, tab: "objects", pageNo: 1, q: queryToParam(r.query) })}>{t("objects.page.gotoRelated", { other: r.other_name, count: r.count })}</a>
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
