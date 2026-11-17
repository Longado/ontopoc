import React, { useState } from "react";
import { confirmItem, getRelation, getRelationGraph, getRelationLog, getRelations } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText } from "./format.js";
import { t } from "./i18n/index.js";
import { RelationGraph } from "./RelationGraph.jsx";
import { CARDINALITY_LABEL, connectedText, groupByType, healthOf, keyPairText, matchLine, sentBackLine, sentenceParts, sortProblemsFirst, summarise, waitingText } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";
import { confirmersText, joinList, logText, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

/** List / Map: two addresses of the same page, so a reload or a shared link keeps the view. */
function ViewToggle({ map }) {
  return (
    <div className="seg" role="group" aria-label={t("relations.page.viewAria")}>
      <a href={hrefFor({ page: "relations" })} aria-current={map ? undefined : "true"} className={map ? "" : "on"}>{t("relations.page.viewList")}</a>
      <a href={hrefFor({ page: "relations", map: true })} aria-current={map ? "true" : undefined} className={map ? "on" : ""}>{t("relations.page.viewMap")}</a>
    </div>
  );
}

export function RelationsPage({ route }) {
  const map = Boolean(route?.map);
  const mayBuild = canBuild(useAuth().user);
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("relations.page.crumbGroup") }, { label: t("relations.page.title") }]} title={t("relations.page.title")} sub={t("relations.page.sub")}
        actions={(
          <>
            <ViewToggle map={map} />
            {mayBuild && <a className="button primary" href={hrefFor({ page: "relationnew" })}>{t("relations.page.new")}</a>}
          </>
        )} />
      {map ? <RelationGraph /> : <RelationList mayBuild={mayBuild} />}
    </main>
  );
}

/** The sentence a relation makes, the two types in bold. */
function Sentence({ r }) {
  const [each, from, mid, to] = sentenceParts(r);
  return <>{each}<strong>{from}</strong>{mid}<strong>{to}</strong></>;
}

/** The bar and the line that say how well a relation matches the data, coloured by health (and always worded, never colour alone). */
function Health({ r, samples }) {
  const health = healthOf(r);
  const n = r.numbers;
  const share = n?.rows ? (n.matched / n.rows) * 100 : 0;
  return (
    <div className={`rel-health rel-health-${health}`}>
      <div className="rel-bar" aria-hidden="true"><span style={{ width: `${share}%` }} /></div>
      <p className="rel-match">{matchLine(r, samples)}</p>
    </div>
  );
}

function RelationCard({ r, keys, samples, mayBuild }) {
  const more = waitingText(r);
  const back = sentBackLine(r);
  const review = mayBuild && r.can_confirm;
  return (
    <article className={`rel-card rel-card-${healthOf(r)}`}>
      <header className="rel-card-head">
        <h3 className="rel-sentence"><a href={hrefFor({ page: "relation", id: r.id })}><Sentence r={r} /></a></h3>
        <State item={r} />
      </header>
      <p className="rel-keys">
        {keys && <code>{r.from_name}.{keys.from_column} → {r.to_name}.{keys.to_column}</code>}
        <span>{CARDINALITY_LABEL[r.cardinality]}</span>
        <span>{r.name}</span>
      </p>
      <Health r={r} samples={samples} />
      {back && <p className="warn small">{back}</p>}
      {more && <p className="warn small">{more}</p>}
      <footer className="rel-card-foot">
        <span className="rel-uses">
          {t("relations.list.appearsOn")} <a href={hrefFor({ page: "type", id: r.from, tab: "props" })}>{r.from_name}</a>{t("types.sep")}<a href={hrefFor({ page: "type", id: r.to, tab: "props" })}>{r.to_name}</a>
          {r.confirmed_by && <span className="muted">{t("relations.list.confirmedByWho", { who: r.confirmed_by })}</span>}
        </span>
        <span className="rel-actions">
          {mayBuild && <a className="button secondary" href={hrefFor({ page: "relationedit", id: r.id })}>{t("relations.detail.edit")}</a>}
          <a className={`button ${review ? "primary" : "secondary"}`} href={hrefFor({ page: "relation", id: r.id })}>{review ? t("relations.graph.review") : t("relations.list.open")}</a>
        </span>
      </footer>
    </article>
  );
}

/** Everything the cards show: the relations, the key columns (the map's data has them), and the unmatched keys of the relations that have some (their own page has them). */
const loadCards = async () => {
  const relations = await getRelations();
  const graph = await getRelationGraph().catch(() => null);
  const keys = Object.fromEntries((graph?.edges ?? []).map((e) => [e.key, { from_column: e.from_column, to_column: e.to_column }]));
  const samples = {};
  await Promise.all(relations.filter((r) => r.numbers?.unmatched > 0).map((r) => getRelation(r.id).then((d) => { samples[r.id] = d.check?.samples ?? []; }, () => {})));
  return { relations, keys, samples };
};

function RelationList({ mayBuild }) {
  const [state, reload] = useLoad(loadCards, []);
  const [by, setBy] = useState("problems");
  const relations = state.data?.relations ?? [];
  const card = (r) => <RelationCard key={r.id} r={r} keys={state.data.keys[r.id]} samples={state.data.samples[r.id] ?? []} mayBuild={mayBuild} />;
  const sum = summarise(relations);
  return (
    <>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">{t("common.loading")}</p>}
      {state.data && !relations.length && (
        <EmptyState icon="link" title={t("relations.list.emptyTitle")} text={mayBuild ? t("relations.list.emptyBuild") : t("relations.list.emptyView")}
          action={mayBuild ? { label: t("relations.page.new"), href: hrefFor({ page: "relationnew" }) } : undefined} />
      )}
      {relations.length > 0 && (
        <>
          <div className="rel-bar-top">
            <p className="rel-summary">
              <strong>{t("relations.list.total", { count: sum.total })}</strong>
              <span className="rel-dot rel-dot-ok" />{t("relations.list.healthy", { count: sum.healthy })}
              <span className={`rel-dot ${sum.attention ? "rel-dot-warn" : "rel-dot-none"}`} />{t("relations.list.attention", { count: sum.attention })}
            </p>
            <div className="seg" role="group" aria-label={t("relations.list.arrangeAria")}>
              <button type="button" className={by === "problems" ? "on" : ""} aria-pressed={by === "problems"} onClick={() => setBy("problems")}>{t("relations.list.byProblems")}</button>
              <button type="button" className={by === "type" ? "on" : ""} aria-pressed={by === "type"} onClick={() => setBy("type")}>{t("relations.list.byType")}</button>
            </div>
          </div>
          {by === "problems" ? <div className="rel-cards">{sortProblemsFirst(relations).map(card)}</div> : groupByType(relations).map((g) => (
            <section key={g.id} className="rel-group">
              <h2 className="rel-group-title"><a href={hrefFor({ page: "type", id: g.id, tab: "props" })}>{g.name}</a> <span className="muted">{t("relations.list.groupCount", { count: g.items.length })}</span></h2>
              <div className="rel-cards">{g.items.map(card)}</div>
            </section>
          ))}
        </>
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

function Check({ r, part }) {
  const c = r.check;
  if (c.problems.length) return <div className="reason"><strong>{t("relations.check.cannot")}</strong>{c.problems.map((p, i) => <p key={i}>{p}</p>)}</div>;
  const n = c.numbers;
  const share = n.rows ? (n.matched / n.rows) * 100 : 0;
  const holds = c.fanout.keys === 0 && n.many_repeats === 0;
  if (part === "cardinality") {
    return (
      <>
        <p className={`rel-verdict ${holds ? "rel-verdict-ok" : "rel-verdict-bad"}`}>{holds ? t("relations.detail.cardHolds", { cardinality: CARDINALITY_LABEL[r.cardinality] }) : t("relations.detail.cardFails", { cardinality: CARDINALITY_LABEL[r.cardinality] })}</p>
        {c.fanout.keys > 0 && (
          <>
            <h2 className="section">{t("relations.check.fanTitle", { count: c.fanout.keys })}</h2>
            <p className="muted small" style={{ marginBottom: 8 }}>
              {t("relations.check.fanText", { count: c.fanout.keys, dataset: c.one.dataset, column: c.one.column, samples: !c.counts_only ? t("relations.check.fanSamples", { list: joinList(c.fanout.samples.map((s) => t("relations.check.fanSample", { key: s.key, rows: s.rows }))) }) : "" })}
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
          <section className={`rel-hero rel-card-${healthOf({ numbers: r.check.numbers })}`}>
            <p className="rel-hero-sentence"><Sentence r={r} /></p>
            <p className="facts">
              <span>{CARDINALITY_LABEL[r.cardinality]}</span>
              <span><code>{keyPairText(r)}</code></span>
              {r.description && <span>{r.description}</span>}
            </p>
            <Health r={{ ...r, numbers: r.check.numbers }} samples={r.check.samples ?? []} />
          </section>
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
          <h2 className="section">{t("relations.detail.match")}</h2>
          <Check r={r} part="match" />
          {!r.check.problems.length && (
            <>
              <h2 className="section">{t("relations.detail.cardinality")}</h2>
              <Check r={r} part="cardinality" />
            </>
          )}
          <h2 className="section">{t("relations.detail.usedTitle")}</h2>
          <p className="rel-uses-detail">
            {t("relations.detail.usedLead")}
            <a href={hrefFor({ page: "type", id: r.from, tab: "props" })}>{r.from_name}</a>{t("types.sep")}<a href={hrefFor({ page: "type", id: r.to, tab: "props" })}>{r.to_name}</a>{t("relations.detail.usedTail")}
          </p>
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
