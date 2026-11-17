import React, { useEffect, useRef } from "react";
import { timeText } from "./format.js";
import { KIND_LABEL, KIND_STYLE, ageText, cameFromText, datedText, confirmedText, edgeLabel, verdictText } from "./graphModel.js";
import { useT } from "./i18n/index.js";
import { CARDINALITY_LABEL, keyPairText } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";

/** Keyboard use of a drawer: it takes focus when it opens (so a keyboard user does not tab through every node to reach it), Escape or the close button shut it, and focus goes
 * back to what was focused before (the node that was picked). The drawer is mounted again for each pick (a `key` on it), so this runs once per pick. */
function useDrawer(onClose) {
  const ref = useRef(null);
  const opener = useRef(document.activeElement);
  useEffect(() => { ref.current?.querySelector("h2")?.focus(); }, []);
  const close = () => {
    onClose();
    const back = opener.current;
    if (back?.isConnected && back !== document.body) setTimeout(() => back.focus(), 0);   // after the drawer has gone and the canvas has settled
  };
  return { ref, close, onKeyDown: (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } } };
}

/** The kind's chip: its colour and icon, as on the card. */
export function KindChip({ kind, size = 28 }) {
  const style = KIND_STYLE[kind] ?? KIND_STYLE.view;
  return (
    <span className="kind-chip" style={{ background: style.colour, width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 24 24" width={Math.round(size * 0.58)} height={Math.round(size * 0.58)}><path d={style.icon} /></svg>
    </span>
  );
}

/** Why a node needs another look, in the cause's own word and the words the service wrote. */
function Cause({ node }) {
  const t = useT();
  const s = node.stale;
  if (!s) return null;
  return (
    <div className="reason" role="note">
      <strong>{s.root ? t("lineage.cause", { label: s.label, root: s.root }) : s.label}</strong>
      <p>{s.text ?? s.text_hidden}</p>
    </div>
  );
}

/** A titled block of the panel. */
const Section = ({ title, count, children }) => (
  <section className="dr-section">
    <h3>{title}{count != null && <span className="dr-count">{count}</span>}</h3>
    {children}
  </section>
);

const List = ({ title, items, empty }) => (
  <Section title={title} count={items.length}>
    {items.length ? <ul className="dr-list">{items.map((i) => <li key={i.key}>{i.href ? <a href={i.href}>{i.name}</a> : <span>{i.name}</span>}{i.note && <span className="dr-note">{i.note}</span>}</li>)}</ul> : <p className="muted small">{empty}</p>}
  </Section>
);

/** Rows of label and value. A row whose value is empty is left out. */
const Facts = ({ rows }) => (
  <dl className="dr-facts">
    {rows.filter(([, v]) => v).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
  </dl>
);

const OpenLink = ({ href, children }) => <p className="dr-open"><a className="button secondary" href={href}>{children}</a></p>;

function TypeBody({ node }) {
  const t = useT();
  const typePage = (tab) => hrefFor({ page: "type", id: node.key, tab });
  const note = (item) => (item.state === "confirmed" ? "" : item.stale?.label ?? t("lineage.drawer.unconfirmed"));
  return (
    <>
      <Section title={t("lineage.drawer.summary")}>
        <Facts rows={[
          [t("lineage.drawer.objects"), node.rows_limited ? t("lineage.drawer.objects_limited", { count: node.objects }) : String(node.objects ?? "—")],
          [t("lineage.drawer.source"), t("lineage.drawer.source_value", { name: node.dataset.name, version: node.dataset.version })],
          [t("lineage.drawer.confirmation"), confirmedText(node)],
          [t("lineage.drawer.answers"), t("lineage.drawer.answers_value", { count: node.answers })],
        ]} />
        <p className="dr-links"><a href={typePage("objects")}>{t("lineage.drawer.view_objects")}</a></p>
      </Section>
      <Cause node={node} />
      {node.derived?.length > 0 && <List title={t("lineage.drawer.derived")} empty={t("lineage.drawer.derived_empty")} items={node.derived.map((d) => ({ key: d.id, name: d.name, note: d.state === "confirmed" ? t("lineage.drawer.derived_note") : t("lineage.drawer.derived_note_state", { state: d.stale?.label ?? t("lineage.drawer.unconfirmed") }), href: typePage("derived") }))} />}
      <List title={t("lineage.drawer.properties")} empty={t("lineage.drawer.properties_empty")} items={node.properties.map((p) => ({ key: p.column, name: p.name, note: p.key ? t("lineage.drawer.key") : "" }))} />
      <List title={t("lineage.drawer.relations")} empty={t("lineage.drawer.relations_empty")} items={node.relations.map((r) => ({ key: r.id, name: r.name, href: hrefFor({ page: "relation", id: r.key }) }))} />
      <List title={t("lineage.drawer.views")} empty={t("lineage.drawer.views_empty")} items={node.views.map((v) => ({ key: v.id, name: v.name, note: note(v), href: typePage("views") }))} />
      {node.actions?.length > 0 && <List title={t("lineage.drawer.actions")} empty={t("lineage.drawer.actions_empty")} items={node.actions.map((a) => ({ key: a.id, name: a.name, note: note(a), href: typePage("actions") }))} />}
      <OpenLink href={typePage("props")}>{t("lineage.drawer.open", { name: node.name })}</OpenLink>
    </>
  );
}

function SourceBody({ node }) {
  const t = useT();
  return (
    <>
      <Section title={t("lineage.drawer.summary")}>
        <Facts rows={[[t("lineage.drawer.kind"), node.kind_label], [t("lineage.drawer.status"), `${node.status_label}${node.status_at ? ` (${timeText(node.status_at)})` : ""}`]]} />
      </Section>
      <List title={t("lineage.drawer.tables")} empty={t("lineage.drawer.tables_empty")} items={node.tables.map((tb) => ({ key: tb.table, name: `${tb.table} → ${tb.dataset}`, href: hrefFor({ page: "dataset", name: tb.dataset, tab: "fields" }) }))} />
      <OpenLink href={hrefFor({ page: "source", name: node.key })}>{t("lineage.drawer.open", { name: node.name })}</OpenLink>
    </>
  );
}

function DatasetBody({ node }) {
  const t = useT();
  const came = cameFromText(node.came_from, true);
  return (
    <>
      <Section title={t("lineage.drawer.summary")}>
        <Facts rows={[
          [t("lineage.drawer.version"), t("lineage.node.version", { version: node.version })],
          [t("lineage.drawer.origin"), came],
          [datedText(node.came_from), node.uploaded_at ? `${ageText(node.uploaded_at)} (${timeText(node.uploaded_at)}${node.who ? `, ${node.who}` : ""})` : ""],
        ]} />
      </Section>
      <List title={t("lineage.drawer.used_for")} empty={t("lineage.drawer.used_for_empty")} items={node.used_for.map((n) => ({ key: n, name: n }))} />
      {node.link && <OpenLink href={hrefFor({ page: "dataset", name: node.key, tab: "fields" })}>{t("lineage.drawer.open", { name: node.name })}</OpenLink>}
    </>
  );
}

function ElementBody({ node }) {
  const t = useT();
  const href = node.kind === "relation" ? hrefFor({ page: "relation", id: node.key }) : node.kind === "answer" ? hrefFor({ page: "qa", id: node.key })
    : node.kind === "pipeline" ? hrefFor({ page: "pipeline", name: node.key })
    : hrefFor({ page: "type", id: node.type, tab: node.kind === "view" ? "views" : node.kind === "derived" ? "derived" : "actions" });
  return (
    <>
      <Section title={t("lineage.drawer.summary")}>
        <Facts rows={[
          [t("lineage.drawer.relation"), node.kind === "relation" ? t("lineage.drawer.relation_value", { from: node.from_name, to: node.to_name, cardinality: CARDINALITY_LABEL[node.cardinality], rows: edgeLabel(node) }) : ""],
          [t("lineage.drawer.on_type"), node.type_name ?? ""],
          [t("lineage.drawer.asked"), node.kind === "answer" ? timeText(node.asked_at) : ""],
        ]} />
      </Section>
      <Cause node={node} />
      <OpenLink href={href}>{t("lineage.drawer.open_it")}</OpenLink>
    </>
  );
}

/** The right-hand panel for a picked node of either graph: the kind's chip, the name and the state, then what the service knows about it in sections, and the way to its page. */
export function NodeDrawer({ node, onClose }) {
  const t = useT();
  const { ref, close, onKeyDown } = useDrawer(onClose);
  return (
    <aside className="drawer" ref={ref} onKeyDown={onKeyDown} aria-label={t("lineage.drawer.aria", { name: node.name })}>
      <div className="drawer-head">
        <KindChip kind={node.kind} />
        <div className="drawer-title">
          <p className="muted small">{KIND_LABEL[node.kind]}</p>
          <h2 tabIndex={-1}>{node.name}</h2>
          {node.state && <State item={node} />}
        </div>
        <button type="button" className="plain drawer-close" onClick={close} aria-label={t("lineage.drawer.close")} title={t("lineage.drawer.close")}>
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
      <div className="drawer-body">
        {node.kind === "type" ? <TypeBody node={node} /> : node.kind === "dataset" ? <DatasetBody node={node} /> : node.kind === "source" ? <SourceBody node={node} /> : <ElementBody node={node} />}
      </div>
    </aside>
  );
}

/** The right-hand panel for a picked line of the relation graph: each relation between the two types, with its rows and whether its cardinality holds. */
export function EdgeDrawer({ group, onClose }) {
  const t = useT();
  const { ref, close, onKeyDown } = useDrawer(onClose);
  return (
    <aside className="drawer" ref={ref} onKeyDown={onKeyDown} aria-label={t("lineage.edge.aria")}>
      <div className="drawer-head">
        <div className="drawer-title"><h2 tabIndex={-1}>{t("lineage.edge.title", { from: group.edges[0].from_name, to: group.edges[0].to_name })}</h2></div>
        <button type="button" className="plain drawer-close" onClick={close} aria-label={t("lineage.drawer.close")} title={t("lineage.drawer.close")}>
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
      <div className="drawer-body">
        {group.edges.map((e) => (
          <section key={e.id} className="dr-section">
            <h3><a href={hrefFor({ page: "relation", id: e.key })}>{e.name}</a> <State item={e} /></h3>
            <p className="muted">{t("lineage.edge.line", { from: e.from_name, to: e.to_name, cardinality: e.cardinality_label })}</p>
            <p className="muted small">{keyPairText(e)}</p>
            <p>{edgeLabel(e)}</p>
            {verdictText(e) && <p className={e.cardinality_ok === false ? "warn" : "muted small"}>{verdictText(e)}</p>}
            <Cause node={e} />
          </section>
        ))}
      </div>
    </aside>
  );
}
