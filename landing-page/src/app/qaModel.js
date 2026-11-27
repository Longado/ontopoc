// The words of the Q&A page, as plain functions of what the service sends, so they can be tested without a browser.
import { t } from "./i18n/index.js";
import { graphNote } from "./objectGraphModel.js";
import { STATE_LABEL } from "./typeModel.js";

const count = (n) => Number(n).toLocaleString("en-US");
const SHOWN_GROUPS = 20;
const countText = (n, unit) => t("ask.count", { n: count(n), unit });

/** An answer from the engine (a count, a share, a total, or groups) as what the card shows: {big, note, table: {head, rows, total} | null}. */
export function answerView(record) {
  const a = record.answer;
  if (!a) return record.status === "no_data" ? { big: t("ask.noData"), note: record.reason ?? "", table: null } : null;   // a query that found nothing has no answer, only why
  const unit = a.relation_gap?.many ?? record.types?.[0]?.name ?? "";
  if (a.graph) return { big: countText(a.graph.starts, unit), note: graphNote(a.graph), table: null, graph: a.graph };   // SELECT GRAPH: the objects, drawn
  if (a.objects) return { big: a.lookup ? t("ask.objects.found", { unit }) : countText(a.total, unit), note: "", table: null, objects: objectsView(a) };   // a list, or one object by its key
  if (a.groups) {
    const shape = a.measure ? null : a.share ? "share" : a.groups[0]?.length === 3 ? "measure" : "count";
    const m = a.measure;   // a total per group: [group, the total, how many were added up]
    const head = m ? [t("ask.head.group"), t("ask.head.measure", { field: m.field, op: t(m.op === "sum" ? "ask.op.sum" : "ask.op.avg") }), t("ask.head.count", { unit })]
      : shape === "share" ? [t("ask.head.group"), `${a.share.field} = ${a.share.equals}`, t("ask.head.total")] : shape === "measure" ? [t("ask.head.group"), t("ask.head.sumOrAvg"), t("ask.head.withValue")] : [t("ask.head.group"), t("ask.head.count", { unit })];
    const rows = a.groups.slice(0, SHOWN_GROUPS).map((g) => g.map((v, i) => (i && typeof v === "number" ? count(v) : String(v))));
    return { big: t("ask.groups", { count: a.total_groups, n: count(a.total_groups) }), note: a.without_value ? t("ask.withoutValue", { count: a.without_value, n: countText(a.without_value, unit) }) : "", table: { head, rows, total: a.total_groups } };
  }
  if (a.measure) {
    const m = a.measure;
    if (m.value == null) return { big: t("ask.measure.none"), note: t("ask.measure.noneNote", { count: m.skipped }), table: null };
    return { big: t("ask.measure.big", { field: m.field, op: t(m.op === "sum" ? "ask.op.sum" : "ask.op.avg"), value: count(m.value) }), note: t("ask.measure.counted", { count: m.counted, n: count(m.counted) }) + (m.skipped ? t("ask.measure.skipped", { count: m.skipped, n: count(m.skipped) }) : ""), table: null };
  }
  if (a.share) return { big: `${count(a.matched)} / ${count(a.total)}`, note: t("ask.share.note", { unit, field: a.share.field, equals: a.share.equals, pct: a.total ? Math.round((a.matched / a.total) * 1000) / 10 : 0 }), table: null };
  return { big: unit ? countText(a.total, unit) : count(a.total), note: record.status === "no_data" ? record.reason ?? "" : "", table: null };
}

/** A cell of a list as it is read: a code by its confirmed meaning, with the code beside it; an empty value as a dash. */
export function cellText(column, value) {
  if (value == null || value === "") return t("ask.objects.empty");
  const label = column?.meanings?.[String(value)];
  return label ? t("ask.objects.coded", { label, code: String(value) }) : String(value);
}

/** A list or one object (answer.objects) as the card's table: {head, rows, keys (which columns are the key), page, pages, pageText, hasPrev, hasNext}. The service
 * orders the objects by their key and pages them; the total is the reader's own count. */
export function objectsView(answer) {
  const o = answer?.objects;
  if (!o) return null;
  const columns = o.columns ?? [];
  return {
    head: columns.map((c) => c.name ?? c.column), keys: columns.map((c) => Boolean(c.key)),
    rows: (o.rows ?? []).map((r) => r.map((v, i) => cellText(columns[i], v))),
    page: o.page, pages: o.pages, hasPrev: o.page > 1, hasNext: o.page < o.pages,
    pageText: o.pages > 1 ? t("ask.objects.page", { page: o.page, pages: o.pages, size: o.page_size, total: count(answer.total) }) : "",
    order: (o.order_by ?? []).length ? t("ask.objects.order", { key: o.order_by.join(t("ask.sep")) }) : "",
  };
}

/** The date `today` was taken as, when the answer's query used it, else "". */
export const todayNote = (record) => (record.today ? t("ask.today", { date: record.today.date, zone: record.today.time_zone }) : "");

/** The same question worked out on other rows, beside an answer (the service adds it when the answer covers every row of a type, or exactly one confirmed view):
 * {title, lines: [{key, name, text, of, by}], more, hint}, or null when there is none. Every row is the first line when the answer read one view. */
export function besideView(record) {
  const views = record.beside?.views ?? [];
  if (!views.length) return null;
  const unit = record.types?.[0]?.name ?? "";
  const all = views.find((v) => v.all_rows);
  const total = all ? all.answer?.total : record.answer?.total;   // what "107 of 150" counts against: every row
  const lines = views.map((v) => ({
    key: v.all_rows ? "all-rows" : v.id ?? v.name, name: v.all_rows ? t("ask.beside.all", { unit }) : v.name,
    text: v.answer ? answerView({ ...record, status: "answered", answer: v.answer }).big : v.no_data ? t("ask.noData") : "",
    of: !v.all_rows && v.answer?.total != null && total != null ? t("ask.beside.of", { n: count(v.answer.total), total: count(total), unit }) : "",
    by: v.confirmed_by ? t("ask.beside.by", { by: v.confirmed_by }) : "",
  }));
  const more = record.beside.more ?? [];
  return { title: t("ask.beside.title"), lines, more: more.length ? t("ask.beside.more", { n: more.length, names: more.join(t("ask.sep")) }) : "", hint: t(all ? "ask.beside.hintView" : "ask.beside.hint") };
}

/** Which part of the refusal card a record fills: a kind the card has its own lines for ("unsettled", "not_in_scope", "definition_unmet"), or, for any other
 * kind and for none, the service's own sentence (it comes in the asker's language), so a refusal of a kind the page does not know yet still says why. */
const REFUSAL_BRANCHES = ["unsettled", "not_in_scope", "definition_unmet"];
export function refusalBranch(record) {
  const kind = record.refusal?.kind;
  return REFUSAL_BRANCHES.includes(kind) ? { kind } : { kind: "reason", text: record.reason ?? "" };
}

/** The answer, or the refusal, in one word for the history list. */
export const statusText = (status) => t(status === "answered" ? "ask.status.answered" : status === "no_data" ? "ask.status.noData" : status === "draft" ? "ask.status.draft" : "ask.status.refused");
export const isAnswer = (record) => record.status === "answered" || record.status === "no_data";

/** What an answer read: "orders v1". */
export const readText = (datasets) => Object.entries(datasets ?? {}).map(([name, v]) => t("ask.read", { name, version: v }));

/** The banner lines of a saved answer that is no longer as it was: a newer dataset version, a definition that is not as confirmed then. */
export function staleLines(record) {
  const data = (record.stale ?? []).map((s) => (s.now == null ? t("ask.stale.gone", { dataset: s.dataset, read: s.read }) : t("ask.stale.newer", { dataset: s.dataset, read: s.read, now: s.now })));
  const defs = (record.changed ?? []).map((c) => (!c.state ? t("ask.changed.gone", { name: c.name }) : c.state !== "confirmed" ? t("ask.changed.state", { name: c.name, state: STATE_LABEL[c.state] }) : t("ask.changed.reconfirmed", { name: c.name })));
  return [...data, ...defs];
}

/** The heading over a saved answer's notes, by what changed: a definition that needs another look (the answer is only what was said then), a definition
 * confirmed again, or only newer data. Empty when nothing changed. */
export function staleHeading(record) {
  const changed = record.changed ?? [];
  if (changed.some((c) => c.state !== "confirmed")) return t("ask.heading.needsLook");
  if (changed.length) return t("ask.heading.reconfirmed");
  return (record.stale ?? []).length ? t("ask.heading.newerData") : "";
}

/** The answer's figure is greyed ("当时的答案") when a definition it stood on is no longer confirmed as it was. */
export const isThenAnswer = (record) => (record.changed ?? []).length > 0;

/** Where a definition's own page is: a type or its meanings, or a relation. null for a line that names no definition. */
export function definitionHref(id, type = null) {
  if (typeof id !== "string") return null;
  if (id.startsWith("objview:")) return `#/types/${encodeURIComponent(type ?? "")}/views`;   // a view is shown on its type's page
  if (id.startsWith("derived:")) return `#/types/${encodeURIComponent(type ?? id.slice("derived:".length).split(":")[0])}/derived`;   // so is a derived property
  if (id.startsWith("objaction:")) return `#/types/${encodeURIComponent(type ?? "")}/actions`;   // an action is on its type's actions tab
  if (id.startsWith("relation:")) return `#/relations/${encodeURIComponent(id.slice("relation:".length))}`;
  const name = id.startsWith("enum:") ? id.slice("enum:".length).split(":")[0] : id.slice("objtype:".length);
  return `#/types/${encodeURIComponent(name)}`;
}

/** A refusal's list as lines to show: a definition it names, with its page; or a line that names none (a viewer is told only that something waits), its text alone. */
export const namedLines = (list) => (list ?? []).map((d, i) => (typeof d.id === "string" ? { ...d, key: d.id, href: definitionHref(d.id, d.type) } : { key: `line-${i}`, plain: true, text: d.text ?? "" }));

/** The line that says what a person may ask about. */
export const scopeText = (scope) => t("ask.scope", { count: scope.types.length });

/** Why a definition cannot be used, in the words of its state: the reason when there is one, else where it stands. */
export function standingText(d) {
  if (d.reason) return d.reason;
  if (d.state === "proposed") return t("ask.standing.proposed");
  if (d.state === "checked") return d.proposed_by ? t("ask.standing.checkedBy", { by: d.proposed_by }) : t("ask.standing.checked");
  return STATE_LABEL[d.state] ?? d.state;
}

/** What the query box starts from: a count of the first type in scope, which runs as written; empty when nothing is in scope. */
export function queryExample(scope) {
  const first = scope?.types?.[0];
  return first ? `SELECT count(x) AS ${t("ask.query.alias")}\nFROM (x:${first.name})` : "";
}

/** The $names a query uses, each once, in order; one inside a quoted value, a `name` or a -- comment is not a parameter (as the service reads it). */
export function paramsIn(text) {
  const names = [];
  for (const m of String(text ?? "").matchAll(/'(?:[^']|'')*'|`[^`]*`|--[^\n]*|\$([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)/g)) {
    if (m[1] && !names.includes(m[1])) names.push(m[1]);
  }
  return names;
}

/** The parameters a query box sends: a value for each $name its text uses (empty when not typed yet), or undefined when it uses none. */
export function queryParams(text, values) {
  const names = paramsIn(text);
  return names.length ? Object.fromEntries(names.map((n) => [n, values?.[n] ?? ""])) : undefined;
}

/** A query's result as the record the answer and refusal cards read (a refusal before anything ran has no definitions, steps or datasets). */
export const queryRecord = (body) => ({ definitions: [], steps: [], datasets: {}, ...body });

/** The values a range could not read as numbers or dates, one line per range, and the dates a month or year grouping could not read: they are not counted,
 * and the answer says so. */
export function rangeNotes(record) {
  const eg = (list) => (list?.length ? t("ask.eg", { list: list.join(t("ask.sep")) }) : "");
  const ranges = (record.evidence?.filters ?? []).filter((f) => f.range && f.unreadable).map((f) => t("ask.range.unreadable", { count: f.unreadable, range: f.range, eg: eg(f.unreadable_examples) }));
  const u = record.answer?.unreadable;
  return u ? [...ranges, t("ask.range.undated", { count: u.count, field: u.field, eg: eg(u.unreadable_examples) })] : ranges;
}

// The Chinese time words (this month, last month, this year, today, yesterday, this week, last N days, 2026-03 ...) are written as \u escapes so this file holds no Chinese literals.
const TIME_WORD = /(\b(?:this|last)\s+(?:month|year|week|quarter)\b|\btoday\b|\byesterday\b|\b(?:last|past)\s+\d+\s+(?:days?|weeks?|months?|years?)\b|\u672c\u6708|\u4e0a\u4e2a?\u6708|\u8fd9\u4e2a\u6708|\u4eca\u5e74|\u53bb\u5e74|\u4eca\u5929|\u6628\u5929|\u524d\u5929|\u672c\u5468|\u8fd9\u5468|\u4e0a\u4e2a?\u5468|\u672c\u5b63\u5ea6|\u4e0a\u5b63\u5ea6|(?:\u6700\u8fd1|\u8fd1|\u8fc7\u53bb)\s*\d+\s*(?:\u5929|\u65e5|\u4e2a\u6708|\u6708|\u5468|\u5e74)|\d{4}\s*\u5e74(?:\s*\d{1,2}\s*\u6708)?|\d{1,2}\s*\u6708\u4efd?|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]{1,2}\u6708\u4efd?)/i;
/** The time word in a question ("this month", "last 30 days", "本月", "2026年3月"), or null. */
export function timeWord(question) {
  const m = TIME_WORD.exec(String(question ?? ""));
  if (!m) return null;
  const word = m[1].replace(/\s+/g, " ").trim();
  return /[^\x00-\x7f]/.test(word) ? word.replace(/\s+/g, "") : word.toLowerCase();
}

const DATEISH = /\u65e5\u671f|\u65f6\u95f4|\u521b\u5efa|\u4e0b\u5355|\u53d1\u751f|\bdate|time|created|month|year|\bday|\d{4}-\d{1,2}|\d{4}\/\d{1,2}|\u6708\u4efd|\u5e74\u4efd/i;
/** True when the answered query has a condition on a date or time (in its filters, or in the written query's WHERE/GROUP BY part). */
function usesTime(record) {
  const filters = [...(record.query?.filters ?? []), ...(record.evidence?.filters ?? [])];
  if (filters.some((f) => DATEISH.test(`${f.field ?? ""} ${f.range ?? ""} ${f.value ?? ""}`))) return true;
  const text = String(record.query_text ?? "");
  const i = text.search(/\bWHERE\b|\bGROUP BY\b/i);
  return i >= 0 && DATEISH.test(text.slice(i));
}

/** The warning on an answer whose question carried a time word the query did not use, else null. */
export function timeWarning(record) {
  if (!isAnswer(record)) return null;
  const word = timeWord(record.question);
  return word && !usesTime(record) ? t("ask.timeWarn", { word }) : null;
}

/** The one-line caliber under an answer: what was counted by which definitions (the views that chose its rows, then its conditions), and the data as of
 * when. Names are shown without the query's `quoting`. Empty when the answer carries no written query. In a question's answer (`record.model`: the model wrote
 * the query) the conditions are the model's filter, not a confirmed definition: they are said as its reading of the confirmed code meanings (when they read a
 * code column) and never as a confirmed view. In a query a person wrote they are that person's, said as before. */
export function criteriaLine(record, asOf) {
  const text = String(record.query_text ?? "");
  const aliases = [...text.matchAll(/\(\s*(\w+)\s*:\s*(`[^`]*`|[^)\s]+)\s*\)/g)];
  if (!aliases.length) return "";
  const plain = (s) => s.replace(/`([^`]*)`/g, "$1");
  const alias = new Map(aliases.map((m) => [m[1], plain(m[2])]));
  const where = /\bWHERE\b([\s\S]*?)(?:\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)/i.exec(text)?.[1]?.trim();
  const views = [...(record.evidence?.views ?? []).map((v) => t("ask.criteria.view", { name: v.name })),
    ...(record.definitions ?? []).filter((d) => d.kind === "derived").map((d) => t("ask.criteria.derived", { name: d.name }))];   // the views that chose its rows, the derived properties it read values from
  const conds = where ? [plain(where.replace(/\b(\w+)\.(?=[^\s.])/g, (s, a) => (alias.has(a) ? `${alias.get(a)}.` : s)).replace(/'((?:[^']|'')*)'/g, "$1").replace(/\s+/g, " "))] : [];
  const all = t("ask.criteria.all", { type: alias.get(aliases[0][1]) });
  const when = asOf ? t("ask.criteria.asOf", { when: asOf }) : "";
  if (record.model && conds.length) {
    const coded = (record.definitions ?? []).some((d) => d.kind === "meaning" && conds[0].includes(d.name));
    const filter = t(coded ? "ask.criteria.modelMeanings" : "ask.criteria.modelFilter", { cond: conds[0] });
    return t("ask.criteria", { cond: `${views.join(t("ask.criteria.sep")) || all}${t("ask.criteria.then")}${filter}`, asOf: when });
  }
  const cond = [...views, ...conds].join(t("ask.criteria.sep")) || all;
  return t("ask.criteria", { cond, asOf: when });
}

/** "数据截至" of an answer: each dataset it read by its version and when that version came (`when` formats the time), "" when the answer does not say (one kept
 * before this was noted): never the time the question was asked. */
export const dataAsOf = (record, when) => (record.data_as_of ?? []).map((d) => t("ask.criteria.version", { name: d.dataset, version: d.version, when: d.imported_at ? when(d.imported_at) : "" })).join(t("ask.criteria.and"));

/** A row of the history list: the question and one grey line (when, and how it went). */
export const historyView = (h, whenText) => ({ id: h.id, question: h.question, meta: `${whenText} ${statusText(h.status)}`.trim() });
