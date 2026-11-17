// The command palette's matching and ranking, as plain functions so they can be tested without a browser.
import { t } from "./i18n/index.js";
import { navFor } from "./routeModel.js";

const KIND_ORDER = ["page", "dataset", "type", "relation", "pipeline", "board", "action"];
const kind = (key) => t(`ui.kind.${key}`);
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
  for (const d of datasets ?? []) out.push({ kind: kind("dataset"), label: d.name, sub: d.rows != null ? t("ui.rows", { count: d.rows }) : "", href: href(`datasets/${enc(d.name)}/fields`), keys: [], icon: "table" });
  for (const x of types ?? []) out.push({ kind: kind("type"), label: x.name, sub: x.id, href: href(`types/${enc(x.id)}/props`), keys: [x.id], icon: "cube" });
  for (const r of relations ?? []) out.push({ kind: kind("relation"), label: r.name, sub: r.from_name && r.to_name ? `${r.from_name} → ${r.to_name}` : "", href: href(`relations/${enc(r.id)}`), keys: [r.id], icon: "link" });
  for (const p of pipelines ?? []) out.push({ kind: kind("pipeline"), label: p.name, sub: "", href: href(`pipelines/${enc(p.id)}`), keys: [p.id], icon: "pipeline" });
  for (const b of boards ?? []) out.push({ kind: kind("board"), label: b.name, sub: "", href: href(`boards/${b.id}`), keys: [], icon: "board" });
  for (const a of actions ?? []) out.push({ kind: kind("action"), label: a.name, sub: a.type ?? "", href: href(`types/${enc(a.type)}/actions`), keys: [], icon: "play" });
  return out;
}

/** The pages this person's navigation offers (and their account page), as page entries. */
export function pageEntries(user) {
  const pages = navFor(user).flatMap((g) => g.items.map((i) => ({ kind: kind("page"), label: i.label, sub: g.label ?? "", href: i.href, keys: [], icon: i.icon })));
  return [...pages, { kind: kind("page"), label: t("nav.account"), sub: "", href: "#/account", keys: [], icon: "user" }];
}

/** The entries that match, best first: by score, then by kind order, then by the order they came in. At most `limit`. */
export function search(entries, query, limit = 12) {
  const order = KIND_ORDER.map(kind);
  return entries
    .map((entry, i) => ({ entry, i, score: Math.max(matchScore(entry.label, query), ...entry.keys.map((k) => matchScore(k, query) - 5), matchScore(entry.sub, query) - 30) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || order.indexOf(a.entry.kind) - order.indexOf(b.entry.kind) || a.i - b.i)
    .slice(0, limit)
    .map((x) => x.entry);
}

/** The places visited, newest first, one per address, at most eight. The home page and a visit with no name are not kept. */
export function recordVisit(list, visit, max = 8) {
  if (!visit.label || visit.href === "#/home" || visit.href === "#/") return list;
  return [{ href: visit.href, label: visit.label }, ...list.filter((v) => v.href !== visit.href)].slice(0, max);
}
