// The command palette's matching and ranking, as plain functions so they can be tested without a browser.
import { navFor } from "./routeModel.js";

const KIND_ORDER = ["页面", "数据集", "对象类型", "关系", "管道", "看板", "行为"];
const norm = (text) => String(text ?? "").toLowerCase().replace(/\s+/g, "");

/** How well `text` matches the query: 0 none, then contains < starts with < equal. */
export function matchScore(text, query) {
  const t = norm(text);
  const q = norm(query);
  if (!q || !t) return 0;
  if (t === q) return 100;
  if (t.startsWith(q)) return 80;
  if (t.includes(q)) return 60;
  return 0;
}

const href = (path) => `#/${path}`;
const enc = encodeURIComponent;

/** The lists the service gave, as palette entries {kind, label, sub, href, keys}. A list that is missing is skipped. */
export function buildEntries({ datasets, types, relations, pipelines, boards, actions } = {}) {
  const out = [];
  for (const d of datasets ?? []) out.push({ kind: "数据集", label: d.name, sub: d.rows != null ? `${d.rows} 行` : "", href: href(`datasets/${enc(d.name)}/fields`), keys: [] });
  for (const t of types ?? []) out.push({ kind: "对象类型", label: t.name, sub: t.id, href: href(`types/${enc(t.id)}/props`), keys: [t.id] });
  for (const r of relations ?? []) out.push({ kind: "关系", label: r.name, sub: r.from_name && r.to_name ? `${r.from_name} → ${r.to_name}` : "", href: href(`relations/${enc(r.id)}`), keys: [r.id] });
  for (const p of pipelines ?? []) out.push({ kind: "管道", label: p.name, sub: "", href: href(`pipelines/${enc(p.id)}`), keys: [p.id] });
  for (const b of boards ?? []) out.push({ kind: "看板", label: b.name, sub: "", href: href(`boards/${b.id}`), keys: [] });
  for (const a of actions ?? []) out.push({ kind: "行为", label: a.name, sub: a.type ?? "", href: href(`types/${enc(a.type)}/actions`), keys: [] });
  return out;
}

/** The pages this person's navigation offers (and their account page), as "跳转到页面" entries. */
export function pageEntries(user) {
  const pages = navFor(user).flatMap((g) => g.items.map((i) => ({ kind: "页面", label: i.label, sub: g.label ?? "", href: i.href, keys: [], icon: i.icon })));
  return [...pages, { kind: "页面", label: "我的账号", sub: "", href: "#/account", keys: [], icon: "user" }];
}

/** The entries that match, best first: by score, then by kind order, then by the order they came in. At most `limit`. */
export function search(entries, query, limit = 12) {
  return entries
    .map((entry, i) => ({ entry, i, score: Math.max(matchScore(entry.label, query), ...entry.keys.map((k) => matchScore(k, query) - 5), matchScore(entry.sub, query) - 30) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || KIND_ORDER.indexOf(a.entry.kind) - KIND_ORDER.indexOf(b.entry.kind) || a.i - b.i)
    .slice(0, limit)
    .map((x) => x.entry);
}

/** The places visited, newest first, one per address, at most eight. The home page and a visit with no name are not kept. */
export function recordVisit(list, visit, max = 8) {
  if (!visit.label || visit.href === "#/home" || visit.href === "#/") return list;
  return [{ href: visit.href, label: visit.label }, ...list.filter((v) => v.href !== visit.href)].slice(0, max);
}
