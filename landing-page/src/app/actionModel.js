// The words and payload of the 行为 tab and the approval cards, as plain functions of what the service sends, so they can be tested without a browser.
import { timeText } from "./format.js";
import { t } from "./i18n/index.js";

/** An object whose keys read their words from the dictionary at the moment they are read, so the words follow the language. */
const worded = (keys, prefix) => {
  const o = {};
  for (const k of keys) Object.defineProperty(o, k, { get: () => t(`${prefix}.${k}`), enumerable: true });
  return o;
};

export const RECORD_STATE = worded(["pending", "approved", "rejected", "withdrawn", "expired", "needs_look"], "actions.state");

/** A record's state in words; a pending one whose dataset moved says so, and one that undoes another names it. */
export const recordStateText = (r) =>
  (r.stale && r.state === "pending" ? t("actions.state.stale") : RECORD_STATE[r.state] ?? r.state) + (r.undo_of ? t("actions.state.undoes", { id: r.undo_of }) : "");

/** A fresh form: an edit, no name, nothing ticked, no condition, anyone who may see it may submit it. */
export const emptyActionForm = () => ({ kind: "edit", name: "", description: "", properties: [], conditions: [], choices: {}, submitters: [] });

export const emptyCondition = () => ({ column: "", op: "eq", value: "" });

/** The words of each operator and kind, as the form shows them. */
export const OP_WORD = worded(["eq", "ne", "gt", "ge", "lt", "le", "in", "empty", "not_empty"], "actions.op");
export const KIND_WORD = worded(["edit", "create", "delete"], "actions.kind");
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
  if (!form.name.trim()) return t("actions.problem.name");
  if ((form.kind ?? "edit") === "edit" && !form.properties.length) return t("actions.problem.properties");
  if (form.kind !== "create") {
    for (const c of form.conditions ?? []) {
      if (!c.column) return t("actions.problem.conditionColumn");
      if (!NO_VALUE.includes(c.op) && !String(c.value ?? "").trim()) return t("actions.problem.conditionValue");
    }
  }
  return "";
}

/** One condition as the service takes it: "one of" is a list (split on commas), empty / not empty carry no value. */
const conditionPayload = (c) => {
  if (NO_VALUE.includes(c.op)) return { column: c.column, op: c.op };
  if (c.op === "in") return { column: c.column, op: c.op, value: String(c.value ?? "").split(/[,\uff0c\u3001]/).map((v) => v.trim()).filter(Boolean) };
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
/** A plain number as the service reads one: digits, an optional minus and decimals; a leading zero (007) keeps a code a code, and 1e3 or 0x10 are text. */
const isNumber = (t) => /^-?\d+(\.\d+)?$/.test(t) && !/^-?0\d/.test(t);
/** A value in the form it is matched in: a number by its value (1000.0 is 1000), anything else as written. */
const canonical = (v) => {
  const t = plain(v);
  if (!isNumber(t)) return t;
  const negative = t.startsWith("-");
  const [whole, fraction = ""] = t.replace(/^-/, "").split(".");   // on the digits as written: a long number keeps every digit
  const rest = fraction.replace(/0+$/, "");
  if (whole === "0" && !rest) return "0";
  return (negative ? "-" : "") + whole + (rest ? `.${rest}` : "");
};
const sameValue = (a, b) => canonical(a) === canonical(b);

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
  if (isNumber(y) !== isNumber(x)) return false;   // a number against text is neither more nor less (the service checks the column's type)
  const [a, b] = isNumber(y) ? [Number(x), Number(y)] : [x, y];
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
  if (action.parameters.some((p) => !plain(values[p.column]))) return t("actions.problem.fill");
  if (action.kind === "delete" && !plain(reason)) return t("actions.problem.reason");
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


/** The last record of an action in one cell: who, when, how it stands. "" while the records are not read. */
export function lastRecordText(records) {
  if (!records) return "";
  if (!records.length) return t("actions.last.none");
  const [r] = records;
  return `${r.submitted_by} · ${timeText(r.submitted_at).slice(5)} · ${recordStateText(r)}`;
}

/** An action as one row of the 行为 table. `records` are its records (newest first) or null; `mayBuild` whether this person builds. A create runs from here; an edit and a delete run from the object. */
export function actionRow(action, records, mayBuild) {
  return {
    id: action.id, name: action.name, kind: ["edit", "create", "delete"].includes(action.kind) ? t(`actions.short.${action.kind}`) : action.kind, says: action.says, state: action.state, last: lastRecordText(records),
    canRun: Boolean(mayBuild) && action.kind === "create" && action.state === "confirmed" && action.can_submit !== false,
  };
}

/** Whether the form's save is off, and the sentence that says why (shown beside the button, not only grey). */
export function saveBlock(form, busy) {
  if (busy) return { disabled: true, reason: t("actions.saving") };
  const reason = actionProblem(form);
  return { disabled: Boolean(reason), reason };
}
