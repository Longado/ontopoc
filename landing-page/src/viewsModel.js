// The 视图 card on the 数据接入 page: what each confirmed definition became in the workspace, and the form for naming a new one.
const NUMBER = new Intl.NumberFormat("zh-CN");
export const KIND_CHOICES = [["filter", "按含义筛行"], ["latest", "每个编号只留最新一行"]];
export const OP_CHOICES = [["is_not", "不是"], ["is", "是"]];

/** The code columns of one table that have a confirmed meaning, each with the meanings (a column nobody confirmed is not offered). */
export const codedColumns = (meanings, table) => Object.entries(meanings || {})
  .filter(([field, m]) => field.startsWith(`${table}.`) && Object.keys(m.labels).length)
  .map(([field, m]) => ({ column: field.slice(table.length + 1), labels: [...new Set(Object.values(m.labels))] }));

export const blankView = (tables) => ({ name: "", kind: "filter", base: tables[0]?.name || "", column: "", op: "is_not", label: "", key: "", order: "" });

/** The form after one choice: what depended on the table or column chosen before is cleared. */
export function setViewChoice(form, part) {
  const next = { ...form, ...part };
  if (part.base !== undefined || part.kind !== undefined) return { ...next, column: "", label: "", key: "", order: "" };
  return part.column !== undefined ? { ...next, label: "" } : next;
}

export function viewProblem(form) {
  if (!form.name.trim()) return "给视图起个名字";
  if (!form.base) return "选一张表";
  if (form.kind === "filter") return !form.column ? "选一个有已确认含义的代码列" : !form.label ? "选一个含义" : "";
  return !form.key ? "选用来认出同一个对象的列" : !form.order ? "选用来比先后的列" : form.key === form.order ? "编号列和比先后的列要不同" : "";
}

/** The request the form says; a view is plain data. */
export const viewBody = (form) => (form.kind === "filter"
  ? { name: form.name.trim(), kind: "filter", base: form.base, column: form.column, op: form.op, label: form.label }
  : { name: form.name.trim(), kind: "latest", base: form.base, key: [form.key], order: form.order });

/** One view as the card shows it: its name, rows and state, where it comes from, and its SQL. */
export const viewLine = (v) => ({
  name: v.name, from: v.source ? `视图，建在表 ${v.source} 上：${v.from}` : v.from, sql: `CREATE VIEW "${v.sql_name}" AS\n${v.sql}`, named: v.definition !== null,
  rows: v.rows === null || v.rows === undefined ? "" : `${NUMBER.format(v.rows)} 行`, usable: v.state === "confirmed",
  state: v.state === "confirmed" ? `已确认${v.confirmed_by ? `（${v.confirmed_by}）` : ""}` : `不可用：${v.why}`,
});
