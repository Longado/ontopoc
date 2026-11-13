// The words and the payload of the 视图 section of a type page, as plain functions of what the service sends, so they can be tested without a browser.

export const OP_LABEL = { is: "是", is_not: "不是" };

/** The payload that makes a view, from the form: `form.filters` [{column, op, label}] (a row left without a meaning is not a condition), `form.latest` {on, key: [], order}. */
export function viewPayload(type, form) {
  const filters = form.filters.filter((f) => f.column && f.label).map(({ column, op, label }) => ({ column, op, label }));
  return {
    name: form.name.trim(), type, description: form.description.trim(), filters,
    latest: form.latest.on ? { key: form.latest.key, order: form.latest.order } : null,
  };
}

/** The first thing missing before the form can be sent; "" when it can. */
export function viewProblem(form) {
  if (!form.name.trim()) return "要写视图的名字";
  const conditions = form.filters.some((f) => f.column && f.label);
  if (!conditions && !form.latest.on) return "要写至少一个条件，或者选“每个编号只留最新的一行”";
  if (form.latest.on && !form.latest.key.length) return "“只留最新”要选编号的列";
  if (form.latest.on && !form.latest.order) return "“只留最新”要选比先后的列";
  if (form.latest.on && form.latest.key.includes(form.latest.order)) return "比先后的列不能是编号列";
  return "";
}

/** "144 / 160 行" for a view whose rows could be counted, "读不出来" otherwise. */
export const rowsText = (view) => (view.rows == null ? "读不出来" : `${view.rows} / ${view.of} 行`);

/** What stops a view being confirmed yet, for the reader who would otherwise look for a button; "" when nothing does. */
export const viewWaitingText = (view) => (view.waiting_on?.length ? `要先确认${view.waiting_on.map((w) => `“${w.name}”`).join("、")}，才能确认这个视图` : "");

/** A fresh form: one empty condition row, "latest" off. */
export const emptyViewForm = () => ({ name: "", description: "", filters: [{ column: "", op: "is_not", label: "" }], latest: { on: false, key: [], order: "" } });
