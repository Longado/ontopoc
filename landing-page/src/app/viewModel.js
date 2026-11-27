// The words and the payload of the Views section of a type page, as plain functions of what the service sends, so they can be tested without a browser.
import { t } from "./i18n/index.js";
import { joinList, otherNamesFrom } from "./typeModel.js";

/** {is: "is", is_not: "is not"} in the current language (read it when rendering). */
export const OP_LABEL = {};
for (const k of ["is", "is_not"]) Object.defineProperty(OP_LABEL, k, { get: () => t(`types.view.op.${k}`), enumerable: true });

/** How a per-row formula is compared with a number: the service's names and the signs shown for them. */
export const FORMULA_OP = { equals: "=", more_than: ">", at_least: ">=", less_than: "<", at_most: "<=" };

/** The formula rows of the form that are whole: a derived property, how it is compared, and a number. */
const formulasOf = (form) => (form.derived ?? []).filter((d) => d.property && d.op && String(d.value).trim() !== "" && Number.isFinite(Number(d.value)));

/** The payload that makes a view, from the form: `form.filters` [{column, op, label}] (a row left without a meaning is not a condition), `form.latest` {on, key: [], order}. */
export function viewPayload(type, form) {
  const filters = form.filters.filter((f) => f.column && f.label).map(({ column, op, label }) => ({ column, op, label }));
  const derived = formulasOf(form).map(({ property, op, value }) => ({ property, op, value: Number(value) }));
  return {
    name: form.name.trim(), ...(form.otherNames === undefined ? {} : { other_names: otherNamesFrom(form.otherNames) }), type, description: form.description.trim(), filters,
    latest: form.latest.on ? { key: form.latest.key, order: form.latest.order } : null,
    ...(derived.length ? { derived } : {}),   // a per-row formula, compared with a number
  };
}

/** The first thing missing before the form can be sent; "" when it can. */
export function viewProblem(form) {
  if (!form.name.trim()) return t("types.view.needName");
  const conditions = form.filters.some((f) => f.column && f.label) || formulasOf(form).length > 0;
  if (!conditions && !form.latest.on) return t("types.view.needCondition");
  if (form.latest.on && !form.latest.key.length) return t("types.view.needKey");
  if (form.latest.on && !form.latest.order) return t("types.view.needOrder");
  if (form.latest.on && form.latest.key.includes(form.latest.order)) return t("types.view.orderIsKey");
  return "";
}

/** "144 / 160 rows" for a view whose rows could be counted, "Can't be read" otherwise. */
export const rowsText = (view) => (view.rows == null ? t("types.view.unreadable") : t("types.view.rows", { rows: view.rows, of: view.of }));

/** What stops a view being confirmed yet, for the reader who would otherwise look for a button; "" when nothing does. */
export const viewWaitingText = (view) => (view.waiting_on?.length ? t("types.view.waiting", { names: joinList(view.waiting_on.map((w) => `“${w.name}”`)) }) : "");

/** A fresh form: one empty condition row, "latest" off. */
export const emptyViewForm = () => ({ name: "", description: "", filters: [{ column: "", op: "is_not", label: "" }], latest: { on: false, key: [], order: "" }, derived: [] });

/** One formula the form offers, as its option reads: its name, and that it is not confirmed yet when it is not (the view then waits for it). */
export const formulaOption = (f) => (f.state === "confirmed" ? f.name : t("types.view.formulaWaits", { name: f.name }));

/** One new value a view has to be told about: the question as the card puts it. */
export const newValueText = (v) => t("types.view.newValue", { column: v.column, value: v.value, label: v.label ? t("types.view.labelParen", { label: v.label }) : "", rows: v.rows });

/** The choices as the service takes them, from {"status|3": "in" | "out"}; null until every new value has one. */
export function newValueChoices(newValues, picked) {
  const all = (newValues ?? []).map((v) => ({ column: v.column, value: v.value, choice: picked[`${v.column}|${v.value}`] }));
  return all.every((c) => c.choice === "in" || c.choice === "out") ? all : null;
}

/** The confirm button's words: "Exclude" changes the definition, so it goes to the other builder instead of being confirmed. */
export const confirmWords = (choices) => (choices?.some((c) => c.choice === "out") ? t("types.view.confirmOut") : t("types.view.confirm"));
