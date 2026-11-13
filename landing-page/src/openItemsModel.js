// The list of things to settle with the client: the service writes it, the page finds the question behind an item.
import { reviewPoints } from "./answerModel.js";

/** A question as the service reads it: the fixed one first, else the last time it was asked. */
export function askedItem(run, question) {
  const fixed = run.evaluation.acceptance?.items.find((i) => i.question === question);
  if (fixed) return fixed;
  for (const round of [...(run.evaluation.asked || [])].reverse()) {
    const hit = [...(round.items || [])].reverse().find((i) => i.question === question);
    if (hit) return hit;
  }
  return null;
}

/** The entry of the question's own query that a model-filter item is about, in the words the service looks it up by.
 *  None once it was dropped and worked out again: what is left to look at is the new answer. */
export function dropFor(run, open) {
  if (open.kind !== "model_filter" || !open.question || !open.filter || open.requeried) return null;
  const item = askedItem(run, open.question);
  if (!item) return null;
  const point = reviewPoints(item, run.ontology).find((p) => p.kind === "filter" && p.field === open.filter.field && p.equals === open.filter.equals);
  return point?.drop ?? null;
}

/** What an empty list means: nothing found, the client has answered all of it (`answered` things, listed below), or nothing
 *  looked for because the ontology never passed verification. */
export const openItemsEmpty = (run, answered = 0) => {
  if (run.ontology.status !== "auto_built_verified") return "本体还没通过核验，代码先不列要确认的事。";
  return answered > 0 ? `要确认的事都已有客户答复（${answered} 件，见下方）。` : "代码没有找到要和客户确认的事。";
};

// A code column's item: one row per value, each with what the data says about it and a place to write what it means.

/** The form as it starts: a confirmed meaning, else one that waits for a second look (the words stay in the box to be kept or changed), else the guess the data backs (pre-selected), else empty. A guess the data
 *  does not back stays out of the box: it is shown beside the value (codeGuess) for a person to take or ignore. */
export function codeStart(item) {
  return Object.fromEntries(item.column.values.map((v) => {
    const start = v.confirmed || v.waiting || (v.preselected ? v.recommendation : null);
    return [v.value, { label: start?.label ?? "", description: start?.description ?? "" }];
  }));
}

/** The model's guess for a value when it is shown but not selected; null when there is none or it is already in the box. */
export const codeGuess = (v) => (v.recommendation && !v.preselected && !v.confirmed ? v.recommendation : null);

/** What is posted: every value with the words written for it (blank ones stay unconfirmed on the service). */
export const codeBody = (item, form) => item.column.values.map((v) => ({
  value: v.value, label: (form[v.value]?.label ?? "").trim(), description: (form[v.value]?.description ?? "").trim() }));

export function codeProblem(item, form) {
  const entries = codeBody(item, form);
  const long = entries.find((e) => e.label.length > 40);
  if (long) return `取值 ${long.value} 的含义最多 40 个字`;
  // all blank on a column that has meanings confirmed is taking them back
  return entries.some((e) => e.label) || item.column.values.some((v) => v.confirmed) ? "" : "至少给一个取值写上含义";
}

/** Why a guess the data does not back was not put in the box, in the words the page shows. */
export const codeWhyWeak = (rec, rows) => rec.why_weak === "few_rows"
  ? `这个取值有 ${rows} 行，它或其余取值的行数不到 20，太少，没有替你选上`
  : "表里没有别的列能把它和其他取值分开，没有替你选上";

/** Who confirmed a definition that now waits for a second look, and when, in the words under its title. */
export function reviewStamp(r) {
  const day = r.confirmed_at ? String(r.confirmed_at).slice(0, 10) : "";
  return `${r.confirmed_by || "有人"}${day ? ` ${day}` : ""} 确认过，换了新数据后对不上`;
}

// A repeated key's item: the three ways the rows can be read, and what is needed to post one.
export const REPEAT_CHOICES = [
  ["keep_both", "每一行都留", "它们是同一个对象的几条记录，每一行都算数"],
  ["keep_latest", "只留最新的一行", "按表里的一列定哪一行最新，其余几行不再列出"],
  ["data_error", "当作数据错误", "这个编号不该重复，等客户改了数据再用"],
];

export function repeatProblem(form) {
  if (!form.rule) return "先选一种处理办法";
  return form.rule === "keep_latest" && !form.column ? "选一列，按它的大小定哪一行最新" : "";
}

export const repeatBody = (form) => (form.rule === "keep_latest" ? { rule: "keep_latest", column: form.column } : { rule: form.rule });

const UNCONFIRMED = "（含义未确认）";

/** A code as people read it: "2 = 已取消" once confirmed, "2（含义未确认）" until then; anything not a code is left as written. */
export function shownCode(meanings, field, value) {
  const code = meanings?.[field];
  if (!code) return value;
  const label = code.labels[value];
  return label ? `${value} = ${label}` : `${value}${UNCONFIRMED}`;
}

/** The meanings entry a query's field names ("订单.状态码", "状态码"): the one key, or null when none or several match. */
function codeField(meanings, name) {
  if (!meanings || typeof name !== "string") return null;
  if (meanings[name]) return name;
  const hits = Object.keys(meanings).filter((k) => k.endsWith(`.${name.split(".").pop()}`));
  return hits.length === 1 ? hits[0] : null;
}

/** The groups of a stored answer with the codes in their keys read as their meanings, so an answer worked out before the
 *  codes were confirmed shows them too. Keys are the dimensions' values joined by " · ", in the query's order; a part the
 *  service already wrote as "2 = 已取消" or "2（含义未确认）" is read again from its code, so it follows what is confirmed now. */
export function relabelGroups(item, groups, meanings) {
  const dims = item.query?.group_by;
  const list = Array.isArray(dims) ? dims : typeof dims === "string" ? [dims] : [];
  const fields = list.map((d) => codeField(meanings, typeof d === "string" ? d : d?.field));
  if (!groups || !fields.some(Boolean)) return groups;
  return groups.map(([key, ...rest]) => {
    const parts = key.split(" · ");
    if (parts.length !== fields.length) return [key, ...rest];
    const code = (part) => (part.endsWith(UNCONFIRMED) ? part.slice(0, -UNCONFIRMED.length) : part.split(" = ")[0]);   // back to the code the answer was worked out with
    const shown = parts.map((part, i) => (fields[i] ? shownCode(meanings, fields[i], code(part)) : part));
    return [shown.join(" · "), ...rest];
  });
}

/** What to write beside an attribute that is a code column: its confirmed meanings, or that nobody has confirmed them. */
export function meaningNote(meanings, source, path) {
  const code = meanings?.[`${source}.${path}`];
  if (!code) return "";
  const labels = Object.entries(code.labels);
  return labels.length ? labels.map(([v, l]) => `${v} = ${l}`).join("、") : "含义未确认";
}
