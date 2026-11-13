// The words of the relation, 待确认 and permission pages, as plain functions of what the service sends, so they can be tested without a browser.
import { hrefFor } from "./routeModel.js";

export const CARDINALITY_LABEL = { many_to_one: "多对一", one_to_many: "一对多", one_to_one: "一对一" };

/** "157 / 160", or "—" when the check could not run. */
export const connectedText = (numbers) => (numbers ? `${numbers.matched} / ${numbers.rows}` : "—");

/** The sentence a relation's two ends make: "订单.客户编号 = 客户.客户编号". */
export const keyPairText = (r) => `${r.from_name}.${r.from_column} = ${r.to_name}.${r.to_column}`;

/** What stops a relation being confirmed yet, for the reader who would otherwise look for a button; "" when nothing does. */
export function waitingText(r) {
  if (!r.waiting_on?.length) return "";
  return `要先确认${r.waiting_on.map((t) => `对象类型“${t.name}”`).join("、")}，才能确认这个关系`;
}

/** The payload that creates or changes a relation, from the form. */
export function relationPayload(form) {
  return {
    english_name: form.english.trim(), name: form.name.trim(), description: form.description.trim(), from: form.from, to: form.to,
    cardinality: form.cardinality, from_column: form.fromColumn, to_column: form.toColumn,
  };
}

/** The columns a new relation starts with once both types are picked: the far end's key, and the near end's column of the same name when it has one. */
export function suggestedColumns(fromType, toType) {
  if (!fromType || !toType) return { fromColumn: "", toColumn: "" };
  const toColumn = toType.key[0];
  return { fromColumn: fromType.columns.some((c) => c.name === toColumn) ? toColumn : "", toColumn };
}

/** Whether the form can be sent, and the first thing missing. */
export function relationProblem(form, editing) {
  if (!form.name.trim()) return "要写名称";
  if (!editing && !form.english.trim()) return "要写英文名";
  if (!form.from || !form.to) return "要选两个对象类型";
  if (!form.fromColumn || !form.toColumn) return "两边各要选一列";
  return "";
}

/** The page an item of the queue leads to. */
export function itemHref(item) {
  if (item.kind === "relation") return hrefFor({ page: "relation", id: item.id });
  return hrefFor({ page: "type", id: item.id, tab: "props" });
}

/** What the person can do with a queue item, in one word: confirm it, wait for someone else, put it forward again, or something else first. */
export function itemAction(item) {
  if (item.can_confirm) return "confirm";
  if (item.kind === "meaning" && item.state === "needs_look") return "repropose";
  if (item.waiting_on?.length) return "blocked";
  return "wait";
}

/** The count on the navigation item: nothing when there is nothing to do. */
export const countText = (count) => (count > 0 ? String(count) : "");

/** The people a restricted type names, for the permissions table: ids -> a set, so a checkbox can be tested and changed without touching the list. */
export function toggled(ids, id, on) {
  const rest = ids.filter((i) => i !== id);
  return on ? [...rest, id] : rest;
}
