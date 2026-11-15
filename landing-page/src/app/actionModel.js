// The words and payload of the 行为 tab and the approval cards, as plain functions of what the service sends, so they can be tested without a browser.

export const RECORD_STATE = { pending: "等批准", approved: "已批准", rejected: "已驳回", withdrawn: "已撤回", expired: "已过期", needs_look: "需再看" };

/** A record's state in words; a pending one whose dataset moved says so, and one that undoes another names it. */
export const recordStateText = (r) =>
  (r.stale && r.state === "pending" ? "等批准（数据已变）" : RECORD_STATE[r.state] ?? r.state) + (r.undo_of ? `（撤销 #${r.undo_of}）` : "");

/** A fresh form: no name, nothing ticked, no condition. */
export const emptyActionForm = () => ({ name: "", description: "", properties: [], condition: { column: "", value: "" }, choices: {} });

/** The choices the service is sent: only those of a written property with both a type and a column. */
export const choicesPayload = (form) =>
  Object.fromEntries(Object.entries(form.choices ?? {}).filter(([c, s]) => form.properties.includes(c) && s.type && s.column.trim()).map(([c, s]) => [c, { type: s.type, column: s.column.trim() }]));

/** The first thing missing before the form can be sent; "" when it can. */
export function actionProblem(form) {
  if (!form.name.trim()) return "要写行为的名字";
  if (!form.properties.length) return "要选至少一个要改的属性";
  if (form.condition.column && !form.condition.value.trim()) return "条件要写取值，或者不设条件";
  return "";
}

export const actionPayload = (type, form) => ({
  name: form.name.trim(), type, description: form.description.trim(), properties: form.properties,
  condition: form.condition.column ? { column: form.condition.column, value: form.condition.value.trim() } : null,
  ...(Object.keys(choicesPayload(form)).length ? { choices: choicesPayload(form) } : {}),
});

/** The object an objects-tab row stands for: its key {column: value} from the row and the columns the service sent, and a name for it. */
export function rowKey(columns, row) {
  const keys = columns.map((c, i) => [c, row[i]]).filter(([c]) => c.key);
  return { key: Object.fromEntries(keys.map(([c, v]) => [c.column, v])), text: keys.map(([, v]) => v).join(" + ") };
}

/** Whether an object row meets the action's condition, so its button is offered only where it would be allowed (the service checks again). */
export const actionFits = (action, columns, row) => {
  if (!action.condition) return true;
  const i = columns.findIndex((c) => c.column === action.condition.column);
  return i < 0 || String(row[i] ?? "") === action.condition.value;
};

/** One recipient of "批准后通知" from the form, or null while it is not complete: {kind: "attr", column, user_attr} or {kind: "via", relation, column, user_attr}. */
export function notifyRecipient({ kind, column, relation, attr }) {
  const name = (attr ?? "").trim();
  const col = (column ?? "").trim();
  if (!name || !col) return null;
  if (kind === "attr") return { kind, column: col, user_attr: name };
  if (kind === "via" && relation) return { kind, relation, column: col, user_attr: name };
  return null;
}
