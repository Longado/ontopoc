// The words and the payload of the 派生 tab of a type page, as plain functions of what the service sends, so they can be tested without a browser.

export const OP_LABEL = { is: "是", is_not: "不是" };
export const KIND_LABEL = { statistic: "统计", function: "函数" };
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
  if (!form.name.trim()) return "要写名称";
  if (!ENGLISH.test(form.english_name.trim())) return "英文名只能用字母、数字和下划线，字母开头";
  if (form.kind === "function") return form.expression.trim() ? "" : "要写算式";
  if (!form.path.length) return "要选一条路径：从哪个关系走到要统计的对象";
  if (!shape?.measured) return "";
  if (shape.many && !form.fn) return "路径经过“多”的一边，要选统计方式";
  if (form.fn === "latest" && !form.latest.order) return "“取最新”要选比先后的列";
  if (!form.column && !(shape.many && form.fn === "count")) return "要选统计哪一列";
  return "";
}

/** The relations a path can go on with from the type it has reached: confirmed ones that touch it, the path's own last relation not taken straight back. */
export function nextRelations(relations, owner, hops) {
  const here = hops.length ? hops[hops.length - 1].to_type : owner;
  return relations.filter((r) => (r.from === here || r.to === here) && r.key !== hops[hops.length - 1]?.relation);
}

/** The words of one hop: 订单属于客户 → 客户 (多对一方向走到“一”的一边: 每个订单只有一个客户). */
export const hopText = (hop) => `${hop.name}，${hop.toward === "many" ? "到“多”的一边：每个对象有好几行" : "到“一”的一边：每个对象只有一个"}`;

/** The aggregations a column may have, in the service's own order, as {id, label}. */
export const fnOptions = (column, aggregations) => (column?.fns ?? []).map((id) => ({ id, label: aggregations[id] ?? id }));

/** "用于 2 个回答 / 0 个视图 / 0 个行为". */
export const usedByText = (used) => `用于 ${used.answers} 个回答 / ${used.views} 个视图 / ${used.actions} 个行为`;

/** What stops a property being confirmed yet, for the reader who would otherwise look for a button; "" when nothing does. */
export const waitingText = (item) => (item.waiting_on?.length ? `要先确认${item.waiting_on.map((w) => `“${w.name}”`).join("、")}，才能确认这个派生属性` : "");

/** A button for what the service offered instead of a refused aggregation: {fn, order?, column?} → its label and the form changes it makes. */
export function offerChange(form, offer, aggregations) {
  const label = offer.fn === "latest" && offer.order ? `改成“取最新”，按“${offer.order}”比先后` : `改成“${aggregations[offer.fn] ?? offer.fn}”${offer.column ? `“${offer.column}”` : ""}`;
  const apply = () => ({
    ...form, fn: offer.fn, column: offer.column ?? form.column,
    latest: offer.fn === "latest" ? { order: offer.order ?? form.latest.order, tie: form.latest.tie } : form.latest,
  });
  return { label, apply };
}

/** The sample a formula was tried on: "样本：金额 = 2520，结果 2847.6". */
export const sampleText = (sample) => (sample ? `${sample.label}：${sample.inputs.map((i) => `${i.column} = ${i.value}`).join("，")}，结果 ${sample.result ?? "空"}` : "");
