// The words of the relation, review queue and permission pages, as plain functions of what the service sends, so they can be tested without a browser.
import { t } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { joinList } from "./typeModel.js";

export const CARDINALITY_LABEL = {};
for (const k of ["many_to_one", "one_to_many", "one_to_one"]) Object.defineProperty(CARDINALITY_LABEL, k, { get: () => t(`relations.card.${k}`), enumerable: true });

/** "157 / 160", or "—" when the check could not run. */
export const connectedText = (numbers) => (numbers ? `${numbers.matched} / ${numbers.rows}` : "—");

/** The sentence a relation's two ends make: "Order.customer_id = Customer.customer_id". */
export const keyPairText = (r) => `${r.from_name}.${r.from_column} = ${r.to_name}.${r.to_column}`;

/** What stops a relation or a type being confirmed yet, for the reader who would otherwise look for a button; "" when nothing does. */
export function waitingText(r) {
  if (r.waiting_on?.length) return t("relations.waiting.types", { names: joinList(r.waiting_on.map((x) => t("relations.waiting.type", { name: x.name }))) });
  if (r.meanings_blocking?.length) return t("relations.waiting.meanings", { names: joinList(r.meanings_blocking.map((c) => `“${c}”`)) });
  return "";
}

/** What a relation's line says: its own short name, or how many relations the line stands for. The match rate is in the drawer, not on the line. */
export function lineLabel(group) {
  if (group.edges.length > 1) return t("relations.line.count", { count: group.edges.length });
  const name = [...(group.edges[0].name ?? "")];
  return name.length > 12 ? `${name.slice(0, 11).join("")}…` : name.join("");
}

/** The match rate of a relation as the drawer says it: "157 / 160 rows connected (98%)". */
export function matchRateText(edge) {
  if (edge.connected == null) return t("relations.match.none");
  const share = edge.of ? t("relations.match.share", { percent: Math.round((edge.connected / edge.of) * 100) }) : "";
  return t("relations.match.rate", { yours: edge.rows_limited ? t("relations.match.yours") : "", connected: edge.connected, of: edge.of, share });
}

/** The preview a new relation shows before it is saved, in a sentence; "" until there is one. `p` is what /relations/preview sends. */
export function previewText(p) {
  if (!p) return "";
  const rest = p.rows - p.matched;
  if (rest <= 0) return t("relations.preview.all", { rows: p.rows });
  const parts = [t("relations.preview.matched", { matched: p.matched, rows: p.rows })];
  if (p.unmatched > 0) parts.push(t("relations.preview.unmatched", { count: p.unmatched, samples: p.samples?.length ? t("relations.preview.samples", { keys: joinList(p.samples.slice(0, 3).map((s) => s.key)) }) : "" }));
  if (p.empty > 0) parts.push(t("relations.preview.empty", { count: p.empty }));
  return parts.join(t("types.comma"));
}

/** What the preview is asked with, or null while a type or a column is not picked yet. */
export function previewPayload(form) {
  if (!form.from || !form.to || !form.fromColumn || !form.toColumn) return null;
  return { from: form.from, to: form.to, cardinality: form.cardinality, from_column: form.fromColumn, to_column: form.toColumn };
}

/** The line for a definition that was sent back: "Sent back" and the reason when there is one; "" for anything else. */
export function sentBackLine(item) {
  if (item.state !== "rejected") return "";
  return item.reason ? t("relations.sentBackWhy", { reason: item.reason }) : t("relations.sentBack");
}

/** The payload that creates or changes a relation, from the form. */
export function relationPayload(form) {
  return {
    english_name: form.english.trim(), name: form.name.trim(), description: form.description.trim(), from: form.from, to: form.to,
    cardinality: form.cardinality, from_column: form.fromColumn, to_column: form.toColumn,
  };
}

/** The columns a new relation starts with once both types are picked: the key of the one side (the end that is not "many"), and the many side's column of the
 * same name when it has one. A join on the one side's key is what keeps it from repeating. */
export function suggestedColumns(fromType, toType, cardinality = "many_to_one") {
  if (!fromType || !toType) return { fromColumn: "", toColumn: "" };
  const [one, many] = cardinality === "one_to_many" ? [fromType, toType] : [toType, fromType];
  const oneColumn = one.key[0];
  const manyColumn = many.columns.some((c) => c.name === oneColumn) ? oneColumn : "";
  return cardinality === "one_to_many" ? { fromColumn: oneColumn, toColumn: manyColumn } : { fromColumn: manyColumn, toColumn: oneColumn };
}

/** Whether the form can be sent, and the first thing missing. */
export function relationProblem(form, editing) {
  if (!form.name.trim()) return t("relations.problem.name");
  if (!editing && !form.english.trim()) return t("relations.problem.english");
  if (!form.from || !form.to) return t("relations.problem.types");
  if (!form.fromColumn || !form.toColumn) return t("relations.problem.columns");
  return "";
}

/** The page an item of the queue leads to. */
export function itemHref(item) {
  if (item.kind === "relation") return hrefFor({ page: "relation", id: item.id });
  if (item.kind === "pipeline") return hrefFor({ page: "pipeline", name: item.id, view: "confirm" });   // a pipeline is confirmed on its own screen, after reading what changed
  if (item.kind === "view") return hrefFor({ page: "type", id: item.id, tab: "views" });
  if (item.kind === "derived") return hrefFor({ page: "type", id: item.id, tab: "derived" });
  if (item.kind === "action" || item.kind === "approval") return hrefFor({ page: "type", id: item.id, tab: "actions" });
  return hrefFor({ page: "type", id: item.id, tab: "props" });
}

/** What the person can do with a queue item, in one word: confirm it, wait for someone else, put it forward again, or something else first. */
export function itemAction(item) {
  if (item.can_confirm) return "confirm";
  if (item.kind === "meaning" && item.state === "needs_look") return "repropose";
  if (item.waiting_on?.length || item.meanings_blocking?.length) return "blocked";
  return "wait";
}

/** The count on the navigation item: nothing when there is nothing to do. */
export const countText = (count) => (count > 0 ? String(count) : "");

/** The people a restricted type names, for the permissions table: ids -> a set, so a checkbox can be tested and changed without touching the list. */
export function toggled(ids, id, on) {
  const rest = ids.filter((i) => i !== id);
  return on ? [...rest, id] : rest;
}
