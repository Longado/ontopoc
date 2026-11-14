import React from "react";
import { timeText } from "./format.js";
import { KIND_LABEL, ageText, confirmedText, edgeLabel, verdictText } from "./graphModel.js";
import { CARDINALITY_LABEL, keyPairText } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { State } from "./TypesPage.jsx";

/** Why a node needs another look, in the cause's own word and the words the service wrote. */
function Cause({ node }) {
  const s = node.stale;
  if (!s) return null;
  return (
    <div className="reason">
      <strong>{s.label}{s.root && `：${s.root}`}</strong>
      <p>{s.text ?? s.text_hidden}</p>
    </div>
  );
}

const List = ({ title, items, empty }) => (
  <section>
    <h3>{title} {items.length}</h3>
    {items.length ? <ul>{items.map((i) => <li key={i.key}>{i.href ? <a href={i.href}>{i.name}</a> : i.name}{i.note && <span className="muted small"> {i.note}</span>}</li>)}</ul> : <p className="muted small">{empty}</p>}
  </section>
);

function TypeBody({ node }) {
  const typePage = (tab) => hrefFor({ page: "type", id: node.key, tab });
  return (
    <>
      <p className="muted">
        {node.rows_limited ? `你能看到 ${node.objects} 个对象，受行规则限制，看不到全部数据的统计` : `${node.objects ?? "—"} 个对象`}
        {" "}<a href={typePage("objects")}>看对象</a>
      </p>
      <p className="muted small">来源 {node.dataset.name} 第 {node.dataset.version} 版</p>
      {confirmedText(node) && <p className="muted small">{confirmedText(node)}</p>}
      <Cause node={node} />
      <List title="属性" empty="没有属性" items={node.properties.map((p) => ({ key: p.column, name: p.name, note: p.key ? "主键" : "" }))} />
      <List title="关系" empty="没有关系" items={node.relations.map((r) => ({ key: r.id, name: r.name, href: hrefFor({ page: "relation", id: r.key }) }))} />
      <List title="视图" empty="没有视图" items={node.views.map((v) => ({ key: v.id, name: v.name, note: v.state === "confirmed" ? "" : v.stale?.label ?? "未确认", href: typePage("views") }))} />
      {node.actions?.length > 0 && <List title="行为" empty="没有行为" items={node.actions.map((a) => ({ key: a.id, name: a.name, note: a.state === "confirmed" ? "" : a.stale?.label ?? "未确认", href: typePage("actions") }))} />}
      <p className="muted small">你存下的回答 {node.answers} 条用到它</p>
      <p><a href={typePage("props")}>进入 {node.name}</a></p>
    </>
  );
}

function DatasetBody({ node }) {
  return (
    <>
      <p className="muted">第 {node.version} 版{node.uploaded_at && `，上传于 ${ageText(node.uploaded_at)}（${timeText(node.uploaded_at)}${node.who ? `，${node.who}` : ""}）`}</p>
      <List title="用于对象类型" empty="还没有对象类型用它" items={node.used_for.map((n) => ({ key: n, name: n }))} />
      {node.link && <p><a href={hrefFor({ page: "dataset", name: node.key, tab: "fields" })}>进入 {node.name}</a></p>}
    </>
  );
}

function ElementBody({ node }) {
  const href = node.kind === "relation" ? hrefFor({ page: "relation", id: node.key }) : node.kind === "answer" ? hrefFor({ page: "qa", id: node.key })
    : hrefFor({ page: "type", id: node.type, tab: node.kind === "view" ? "views" : "actions" });
  return (
    <>
      {node.kind === "relation" && <p className="muted">{node.from_name} → {node.to_name}，{CARDINALITY_LABEL[node.cardinality]}，{edgeLabel(node)}</p>}
      {node.type_name && <p className="muted">在对象类型“{node.type_name}”上</p>}
      {node.kind === "answer" && <p className="muted small">提问于 {timeText(node.asked_at)}</p>}
      <Cause node={node} />
      <p><a href={href}>进入</a></p>
    </>
  );
}

/** The right-hand panel for a picked node of either graph. */
export function NodeDrawer({ node, onClose }) {
  return (
    <aside className="drawer" aria-label={`${node.name}的详情`}>
      <div className="drawer-head">
        <div>
          <p className="muted small">{KIND_LABEL[node.kind]}</p>
          <h2>{node.name}</h2>
        </div>
        <button className="plain" onClick={onClose}>关闭</button>
      </div>
      {node.state && <p><State item={node} /></p>}
      {node.kind === "type" ? <TypeBody node={node} /> : node.kind === "dataset" ? <DatasetBody node={node} /> : <ElementBody node={node} />}
    </aside>
  );
}

/** The right-hand panel for a picked line of the relation graph: each relation between the two types, with its rows and whether its cardinality holds. */
export function EdgeDrawer({ group, onClose }) {
  return (
    <aside className="drawer" aria-label="关系详情">
      <div className="drawer-head">
        <h2>{group.edges[0].from_name} 和 {group.edges[0].to_name}</h2>
        <button className="plain" onClick={onClose}>关闭</button>
      </div>
      {group.edges.map((e) => (
        <section key={e.id}>
          <h3><a href={hrefFor({ page: "relation", id: e.key })}>{e.name}</a> <State item={e} /></h3>
          <p className="muted">{e.from_name} → {e.to_name}，{e.cardinality_label}</p>
          <p className="muted small">{keyPairText(e)}</p>
          <p>{edgeLabel(e)}</p>
          {verdictText(e) && <p className={e.cardinality_ok === false ? "warn" : "muted small"}>{verdictText(e)}</p>}
          <Cause node={e} />
        </section>
      ))}
    </aside>
  );
}
