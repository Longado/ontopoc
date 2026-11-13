// The words of the relation, 待确认 and permission pages, as plain functions of what the service sends, so they can be tested without a browser.
import { hrefFor } from "./routeModel.js";

export const CARDINALITY_LABEL = { many_to_one: "多对一", one_to_many: "一对多", one_to_one: "一对一" };

/** "157 / 160", or "—" when the check could not run. */
export const connectedText = (numbers) => (numbers ? `${numbers.matched} / ${numbers.rows}` : "—");

/** The sentence a relation's two ends make: "订单.客户编号 = 客户.客户编号". */
export const keyPairText = (r) => `${r.from_name}.${r.from_column} = ${r.to_name}.${r.to_column}`;

/** What stops a relation or a type being confirmed yet, for the reader who would otherwise look for a button; "" when nothing does. */
export function waitingText(r) {
  if (r.waiting_on?.length) return `要先确认${r.waiting_on.map((t) => `对象类型“${t.name}”`).join("、")}，才能确认这个关系`;
  if (r.meanings_blocking?.length) return `要先确认${r.meanings_blocking.map((c) => `“${c}”`).join("、")}的含义，才能确认这个对象类型`;
  return "";
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
