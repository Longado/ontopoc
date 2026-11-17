// The words and the payload of the Derived tab of a type page, as plain functions of what the service sends, so they can be tested without a browser.
import { t } from "./i18n/index.js";
import { joinList } from "./typeModel.js";

/** {is: "is", is_not: "is not"} in the current language (read it when rendering). */
export const OP_LABEL = {};
for (const k of ["is", "is_not"]) Object.defineProperty(OP_LABEL, k, { get: () => t(`types.derived.op.${k}`), enumerable: true });
export const KIND_LABEL = {};
for (const k of ["statistic", "function"]) Object.defineProperty(KIND_LABEL, k, { get: () => t(`types.derived.kind.${k}`), enumerable: true });
const ENGLISH = /^[A-Za-z][A-Za-z0-9_]{0,39}$/;

/** A fresh form: a statistic with no path yet. */
export const emptyDerivedForm = (kind = "statistic") => ({
  kind, name: "", english_name: "", description: "", expression: "",
  path: [], column: "", fn: "", latest: { order: "", tie: "" }, conditions: [{ column: "", op: "is", label: "" }],
});

/** The form of a property that is already saved, from the definition the service sent with it. */
export function formFromLine(line) {
  const d = line.definition;
  return {
    kind: d.kind, name: d.name, english_name: d.english_name, description: d.description ?? "", expression: d.expression ?? "",
    path: d.path ?? [], column: d.measure?.column ?? "", fn: d.fn && d.fn !== "value" ? d.fn : "",
    latest: { order: d.latest?.order ?? "", tie: d.latest?.tie ?? "" },
    conditions: d.conditions?.length ? d.conditions.map(({ column, op, label }) => ({ column, op, label })) : [{ column: "", op: "is", label: "" }],
  };
}

/** The payload that makes (or changes) a property, from the form. A condition row left without a meaning is not a condition. */
export function derivedPayload(type, form) {
  const base = { type, kind: form.kind, english_name: form.english_name.trim(), name: form.name.trim(), description: form.description.trim() };
  if (form.kind === "function") return { ...base, expression: form.expression.trim() };
  return {
    ...base, path: form.path, measure: { column: form.column || null }, fn: form.fn || null,
    latest: form.fn === "latest" ? { order: form.latest.order, tie: form.latest.tie || null } : null,
    conditions: form.conditions.filter((c) => c.column && c.label).map(({ column, op, label }) => ({ column, op, label })),
  };
}

/** The first thing missing before the form can be tried; "" when nothing is. `shape` is what the service said of the path chosen so far. */
export function derivedProblem(form, shape) {
  if (!form.name.trim()) return t("types.derived.needName");
  if (!ENGLISH.test(form.english_name.trim())) return t("types.derived.badEnglish");
  if (form.kind === "function") return form.expression.trim() ? "" : t("types.derived.needExpression");
  if (!form.path.length) return t("types.derived.needPath");
  if (!shape?.measured) return "";
  if (shape.many && !form.fn) return t("types.derived.needAggregation");
  if (form.fn === "latest" && !form.latest.order) return t("types.derived.needLatestOrder");
  if (!form.column && !(shape.many && form.fn === "count")) return t("types.derived.needColumn");
  return "";
}

/** The relations a path can go on with from the type it has reached: confirmed ones that touch it, the path's own last relation not taken straight back. */
export function nextRelations(relations, owner, hops) {
  const here = hops.length ? hops[hops.length - 1].to_type : owner;
  return relations.filter((r) => (r.from === here || r.to === here) && r.key !== hops[hops.length - 1]?.relation);
}

/** The words of one hop: going to the "many" side means each object has several rows, to the "one" side just one. */
export const hopText = (hop) => t(hop.toward === "many" ? "types.derived.hopMany" : "types.derived.hopOne", { name: hop.name });

/** The aggregations a column may have, in the service's own order, as {id, label}. */
export const fnOptions = (column, aggregations) => (column?.fns ?? []).map((id) => ({ id, label: aggregations[id] ?? id }));

/** "Used by 2 answers / 0 views / 0 actions". */
export const usedByText = (used) => t("types.derived.usedBy", { answers: used.answers, views: used.views, actions: used.actions });

/** What stops a property being confirmed yet, for the reader who would otherwise look for a button; "" when nothing does. */
export const waitingText = (item) => (item.waiting_on?.length ? t("types.derived.waiting", { names: joinList(item.waiting_on.map((w) => `“${w.name}”`)) }) : "");

/** A button for what the service offered instead of a refused aggregation: {fn, order?, column?} → its label and the form changes it makes. */
export function offerChange(form, offer, aggregations) {
  const label = offer.fn === "latest" && offer.order
    ? t("types.derived.offerLatest", { order: offer.order })
    : t("types.derived.offer", { fn: aggregations[offer.fn] ?? offer.fn, column: offer.column ? ` “${offer.column}”` : "" });
  const apply = () => ({
    ...form, fn: offer.fn, column: offer.column ?? form.column,
    latest: offer.fn === "latest" ? { order: offer.order ?? form.latest.order, tie: form.latest.tie } : form.latest,
  });
  return { label, apply };
}

/** The sample a formula was tried on: "Sample: Amount = 2520, result 2847.6". */
export const sampleText = (sample) => (sample ? t("types.derived.sample", { label: sample.label, inputs: sample.inputs.map((i) => `${i.column} = ${i.value}`).join(t("types.comma")), result: sample.result ?? t("types.derived.sampleEmpty") }) : "");
