import React, { useState } from "react";
import { confirmItem, getRelation, getRelationLog, getRelations } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText } from "./format.js";
import { t } from "./i18n/index.js";
import { RelationGraph } from "./RelationGraph.jsx";
import { CARDINALITY_LABEL, connectedText, keyPairText, waitingText } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { confirmersText, joinList, logText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

/** Graph / List: two addresses of the same page, so a reload or a shared link keeps the view. */
function ViewToggle({ list }) {
  return (
    <div className="seg" role="group" aria-label={t("relations.page.viewAria")}>
      <a href={hrefFor({ page: "relations" })} aria-current={list ? undefined : "true"} className={list ? "" : "on"}>{t("relations.page.viewGraph")}</a>
      <a href={hrefFor({ page: "relations", list: true })} aria-current={list ? "true" : undefined} className={list ? "on" : ""}>{t("relations.page.viewList")}</a>
    </div>
  );
}

export function RelationsPage({ route }) {
  const list = Boolean(route?.list);
  const mayBuild = canBuild(useAuth().user);
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("relations.page.crumbGroup") }, { label: t("relations.page.title") }]} title={t("relations.page.title")} sub={t("relations.page.sub")}
        actions={(
          <>
            <ViewToggle list={list} />
            {mayBuild && <a className="button primary" href={hrefFor({ page: "relationnew" })}>{t("relations.page.new")}</a>}
          </>
        )} />
      {list ? <RelationList mayBuild={mayBuild} /> : <RelationGraph />}
    </main>
  );
}

function RelationList({ mayBuild }) {
  const [state, reload] = useLoad(getRelations, []);
  const relations = state.data ?? [];
  return (
    <>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">{t("common.loading")}</p>}
      {state.data && !relations.length && (
        <EmptyState icon="link" title={t("relations.list.emptyTitle")} text={mayBuild ? t("relations.list.emptyBuild") : t("relations.list.emptyView")}
          action={mayBuild ? { label: t("relations.page.new"), href: hrefFor({ page: "relationnew" }) } : undefined} />
      )}
      {relations.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>{t("relations.list.relation")}</th><th>{t("relations.list.cardinality")}</th><th className="num">{t("relations.list.connected")}</th><th>{t("relations.list.state")}</th><th>{t("relations.list.confirmedBy")}</th></tr>
            </thead>
            <tbody>
              {relations.map((r) => (
                <tr key={r.id}>
                  <td><a href={hrefFor({ page: "relation", id: r.id })}>{r.from_name} → {r.to_name}</a> <span className="muted small">{r.name}</span></td>
                  <td>{CARDINALITY_LABEL[r.cardinality]}</td>
                  <td className="num">{connectedText(r.numbers)}</td>
                  <td><State item={r} /></td>
                  <td>{r.confirmed_by ?? <span className="faint">{t("types.none")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function RowsTable({ table, markColumn }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i}>{row.map((v, j) => <td key={j} className={table.columns[j] === markColumn ? "warn" : ""}>{v ?? <span className="faint">{t("relations.empty")}</span>}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Check({ r }) {
  const c = r.check;
  if (c.problems.length) return <div className="reason"><strong>{t("relations.check.cannot")}</strong>{c.problems.map((p, i) => <p key={i}>{p}</p>)}</div>;
  const n = c.numbers;
  const share = n.rows ? (n.matched / n.rows) * 100 : 0;
  return (
    <>
      <div className="connected">
        <span className="big">{connectedText(n)}</span>
        <span className="muted">{t("relations.check.connected", { manyDataset: c.many.dataset, manyVersion: c.many.version, oneDataset: c.one.dataset, oneVersion: c.one.version })}</span>
      </div>
      <div className="bar" aria-hidden="true"><span style={{ width: `${share}%` }} /></div>
      {r.anchored && r.state === "confirmed" && <p className="muted small">{t("relations.check.atConfirm", { numbers: connectedText(r.anchored.numbers) })}</p>}
      {n.unmatched > 0 && (
        <>
          <h2 className="section">{t("relations.check.unmatchedTitle", { count: n.unmatched })}</h2>
          <p className="warn strong" style={{ marginBottom: 8 }}>
            {t("relations.check.unmatched", { count: n.unmatched, many: c.many.name, one: c.one.name })}{!c.counts_only && `${t("relations.check.unmatchedKeys", { keys: joinList(c.samples.map((s) => s.key)) })}${c.unmatched_keys > c.samples.length ? t("relations.check.unmatchedMore", { count: c.unmatched_keys }) : ""}`}
            {c.if_trimmed > 0 && t("relations.check.trimmed", { count: c.if_trimmed })}
          </p>
          {!c.counts_only && <RowsTable table={c.unmatched_rows} markColumn={c.many.column} />}
          {!c.counts_only && n.unmatched > c.unmatched_rows.rows.length && <p className="muted small" style={{ marginTop: 4 }}>{t("relations.check.firstRows", { count: c.unmatched_rows.rows.length })}</p>}
        </>
      )}
      {c.empty > 0 && <p className="warn" style={{ marginTop: 12 }}>{t("relations.check.emptyKey", { count: c.empty, column: c.many.column, one: c.one.name })}</p>}
      {c.fanout.keys > 0 && (
        <>
          <h2 className="section">{t("relations.check.fanTitle", { count: c.fanout.keys })}</h2>
          <p className="muted small" style={{ marginBottom: 8 }}>
            {t("relations.check.fanText", { dataset: c.one.dataset, column: c.one.column, count: c.fanout.keys, samples: !c.counts_only ? t("relations.check.fanSamples", { list: joinList(c.fanout.samples.map((s) => t("relations.check.fanSample", { key: s.key, rows: s.rows }))) }) : "" })}
            {c.fanout.extra_rows > 0 ? t("relations.check.fanExtra", { source: c.fanout.source_rows, extra: c.fanout.extra_rows, one: c.one.name }) : t("relations.check.fanNone")}
          </p>
          {!c.counts_only && <RowsTable table={c.fanout.rows} markColumn={c.one.column} />}
        </>
      )}
      {n.many_repeats > 0 && <p className="warn" style={{ marginTop: 12 }}>{t("relations.check.oneToOne", { dataset: c.many.dataset, column: c.many.column, count: n.many_repeats })}</p>}
      {n.unmatched === 0 && c.fanout.keys === 0 && n.many_repeats === 0 && <p className="muted" style={{ marginTop: 12 }}>{t("relations.check.allGood", { dataset: c.one.dataset, column: c.one.column })}</p>}
      {(c.warnings ?? []).map((w, i) => <p key={i} className="warn" style={{ marginTop: 12 }}>{w}</p>)}
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
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !r && <p className="muted">{t("common.loading")}</p>}
      {r && (
        <>
          <PageHeader crumbs={[{ label: t("relations.page.crumbGroup") }, { label: t("relations.page.title"), href: "#/relations" }, { label: `${r.from_name} → ${r.to_name}` }]} title={`${r.from_name} → ${r.to_name}`} status={<State item={r} />}
            sub={r.name}
            actions={mayBuild && (
              <>
                <a className="button secondary" href={hrefFor({ page: "relationedit", id })}>{t("relations.detail.edit")}</a>
                {r.can_confirm && <button className="primary" onClick={confirm} disabled={busy}>{t("relations.detail.confirm")}</button>}
              </>
            )} />
          {error && <p className="error">{error}</p>}
          <p className="facts">
            <span>{CARDINALITY_LABEL[r.cardinality]}</span>
            <span>{keyPairText(r)}</span>
            {r.description && <span>{r.description}</span>}
          </p>
          {stateLine(r, t("relations.detail.noun")) && <p className="muted">{stateLine(r, t("relations.detail.noun"))}</p>}
          {waitingText(r) && (
            <p className="warn">
              {waitingText(r)}{t("types.colon")} {r.waiting_on.map((w, i) => <span key={w.id}>{i > 0 && t("types.sep")}<a href={hrefFor({ page: "type", id: w.id, tab: "props" })}>{w.name}</a></span>)}
            </p>
          )}
          {confirmersText(r) && <p className="muted small">{confirmersText(r)}</p>}
          {r.state === "needs_look" && r.reason && (
            <div className="reason">
              <strong>{t("types.page.whyLook")}</strong>
              <p>{r.reason}</p>
            </div>
          )}
          {r.state === "rejected" && r.reason && (
            <div className="reason">
              <strong>{t("relations.detail.rejectedReason")}</strong>
              <p>{r.reason}</p>
            </div>
          )}
          <div style={{ marginTop: 20 }}><Check r={r} /></div>
          <h2 className="section">{t("relations.detail.log")}</h2>
          {log.status === "ready" && (
            <div className="table-wrap">
              <table className="log">
                <thead><tr><th>{t("types.log.when")}</th><th>{t("types.log.who")}</th><th>{t("types.log.what")}</th></tr></thead>
                <tbody>
                  {log.data.map((e, i) => {
                    const line = logText(e);
                    return <tr key={i}><td className="keep">{timeText(e.at)}</td><td className="keep">{line.who}</td><td>{line.text}</td></tr>;
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
