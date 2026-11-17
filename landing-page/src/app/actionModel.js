// The words and payload of the 行为 tab and the approval cards, as plain functions of what the service sends, so they can be tested without a browser.

export const RECORD_STATE = { pending: "等批准", approved: "已批准", rejected: "已驳回", withdrawn: "已撤回", expired: "已过期", needs_look: "需再看" };

/** A record's state in words; a pending one whose dataset moved says so, and one that undoes another names it. */
export const recordStateText = (r) =>
  (r.stale && r.state === "pending" ? "等批准（数据已变）" : RECORD_STATE[r.state] ?? r.state) + (r.undo_of ? `（撤销 #${r.undo_of}）` : "");

/** A fresh form: an edit, no name, nothing ticked, no condition, anyone who may see it may submit it. */
export const emptyActionForm = () => ({ kind: "edit", name: "", description: "", properties: [], conditions: [], choices: {}, submitters: [] });

export const emptyCondition = () => ({ column: "", op: "eq", value: "" });

/** The words of each operator and kind, as the form shows them. */
export const OP_WORD = { eq: "等于", ne: "不等于", gt: "大于", ge: "大于等于", lt: "小于", le: "小于等于", in: "是其中之一", empty: "为空", not_empty: "不为空" };
export const KIND_WORD = { edit: "改对象", create: "新建对象", delete: "删除对象" };
const NO_VALUE = ["empty", "not_empty"];
const ORDERED = ["gt", "ge", "lt", "le"];

/** The operators a property offers: numbers and dates can be compared in order; a code column is a meaning, so it cannot. */
export const opsFor = (p) =>
  !p?.enum && ["integer", "decimal", "date", "datetime", "month"].includes(p?.type) ? ["eq", "ne", ...ORDERED, "in", ...NO_VALUE] : ["eq", "ne", "in", ...NO_VALUE];

/** The choices the service is sent: only those of a written property with both a type and a column. */
export const choicesPayload = (form) =>
  Object.fromEntries(Object.entries(form.choices ?? {}).filter(([c, s]) => form.properties.includes(c) && s.type && s.column.trim()).map(([c, s]) => [c, { type: s.type, column: s.column.trim() }]));

/** The first thing missing before the form can be sent; "" when it can. */
export function actionProblem(form) {
  if (!form.name.trim()) return "要写行为的名字";
  if ((form.kind ?? "edit") === "edit" && !form.properties.length) return "要选至少一个要改的属性";
  if (form.kind !== "create") {
    for (const c of form.conditions ?? []) {
      if (!c.column) return "每个条件要选属性";
      if (!NO_VALUE.includes(c.op) && !String(c.value ?? "").trim()) return "条件要写取值，或者去掉这个条件";
    }
  }
  return "";
}

/** One condition as the service takes it: "one of" is a list (split on commas or 、), empty / not empty carry no value. */
const conditionPayload = (c) => {
  if (NO_VALUE.includes(c.op)) return { column: c.column, op: c.op };
  if (c.op === "in") return { column: c.column, op: c.op, value: String(c.value ?? "").split(/[,，、]/).map((v) => v.trim()).filter(Boolean) };
  return { column: c.column, op: c.op, value: String(c.value ?? "").trim() };
};

export const actionPayload = (type, form) => {
  const kind = form.kind ?? "edit";
  return {
    name: form.name.trim(), type, kind, description: form.description.trim(), properties: kind === "delete" ? [] : form.properties,
    conditions: kind === "create" ? [] : (form.conditions ?? []).map(conditionPayload),
    ...(kind !== "delete" && Object.keys(choicesPayload(form)).length ? { choices: choicesPayload(form) } : {}),
    ...(form.submitters?.length ? { submitters: form.submitters } : {}),
  };
};

/** The object an objects-tab row stands for: its key {column: value} from the row and the columns the service sent, and a name for it. */
export function rowKey(columns, row) {
  const keys = columns.map((c, i) => [c, row[i]]).filter(([c]) => c.key);
  return { key: Object.fromEntries(keys.map(([c, v]) => [c.column, v])), text: keys.map(([, v]) => v).join(" + ") };
}

const plain = (v) => (v === null || v === undefined ? "" : String(v).trim());
const sameValue = (a, b) => {
  const [x, y] = [plain(a), plain(b)];
  return x === y || (x !== "" && y !== "" && !Number.isNaN(Number(x)) && !Number.isNaN(Number(y)) && Number(x) === Number(y) && !/^0\d/.test(x) && !/^0\d/.test(y));
};

/** Whether one condition holds for a value of the object, as the service decides it (the service checks again at submit). */
export function holds(cond, value) {
  const empty = plain(value) === "";
  if (cond.op === "empty") return empty;
  if (cond.op === "not_empty") return !empty;
  if (cond.op === "ne") return empty || !sameValue(value, cond.value);
  if (empty) return false;
  if (cond.op === "eq") return sameValue(value, cond.value);
  if (cond.op === "in") return (cond.value ?? []).some((v) => sameValue(value, v));
  const [x, y] = [plain(value), plain(cond.value)];
  const numbers = x !== "" && y !== "" && !Number.isNaN(Number(x)) && !Number.isNaN(Number(y));
  const [a, b] = numbers ? [Number(x), Number(y)] : [x, y];
  return { gt: a > b, ge: a >= b, lt: a < b, le: a <= b }[cond.op] ?? false;
}

/** Whether an object row meets all of the action's conditions, so its button is offered only where it would be allowed. A create is never run on a row. */
export const actionFits = (action, columns, row) => {
  if (action.kind === "create") return false;
  return (action.conditions ?? []).every((c) => {
    const i = columns.findIndex((col) => col.column === c.column);
    return i < 0 || holds(c, row[i]);
  });
};

/** What a run of the action sends besides its name and reason: a create's key apart from its values, a delete's no values. */
export function runPayload(action, values) {
  if (action.kind === "delete") return { params: {} };
  const trimmed = Object.fromEntries(action.parameters.map((p) => [p.column, plain(values[p.column])]));
  if (action.kind !== "create") return { params: trimmed };
  const key = action.parameters.filter((p) => p.key);
  return { key: Object.fromEntries(key.map((p) => [p.column, trimmed[p.column]])), params: Object.fromEntries(action.parameters.filter((p) => !p.key).map((p) => [p.column, trimmed[p.column]])) };
}

/** The first thing missing before a run can be sent; "" when it can. */
export function runProblem(action, values, reason) {
  if (action.parameters.some((p) => !plain(values[p.column]))) return "每一项都要填";
  if (action.kind === "delete" && !plain(reason)) return "删除要写理由";
  return "";
}

/** A record's change in one line: a create or a delete says what it does, an edit reads before → after. */
export const recordChangeText = (r) => (r.kind === "create" || r.kind === "delete" ? r.change_text : `${r.before_text} → ${r.after_text}`);

/** One recipient of "批准后通知" from the form, or null while it is not complete: {kind: "attr", column, user_attr} or {kind: "via", relation, column, user_attr}. */
export function notifyRecipient({ kind, column, relation, attr }) {
  const name = (attr ?? "").trim();
  const col = (column ?? "").trim();
  if (!name || !col) return null;
  if (kind === "attr") return { kind, column: col, user_attr: name };
  if (kind === "via" && relation) return { kind, relation, column: col, user_attr: name };
  return null;
}
