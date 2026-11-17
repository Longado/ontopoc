// The words of the Q&A page, as plain functions of what the service sends, so they can be tested without a browser.
import { graphNote } from "./objectGraphModel.js";
import { STATE_LABEL } from "./typeModel.js";

const count = (n) => Number(n).toLocaleString("en-US");
const SHOWN_GROUPS = 20;

/** An answer from the engine (a count, a share, a total, or groups) as what the card shows: {big, note, table: {head, rows, total} | null}. */
export function answerView(record) {
  const a = record.answer;
  if (!a) return record.status === "no_data" ? { big: "没有数据", note: record.reason ?? "", table: null } : null;   // a query that found nothing has no answer, only why
  const unit = a.relation_gap?.many ?? record.types?.[0]?.name ?? "";
  if (a.graph) return { big: `${count(a.graph.starts)} 个${unit}`, note: graphNote(a.graph), table: null, graph: a.graph };   // SELECT GRAPH: the objects, drawn
  if (a.groups) {
    const shape = a.measure ? null : a.share ? "share" : a.groups[0]?.length === 3 ? "measure" : "count";
    const head = shape === "share" ? ["分组", `${a.share.field} = ${a.share.equals}`, "总数"] : shape === "measure" ? ["分组", "合计或平均", "取到数的对象"] : ["分组", `${unit}数`];
    const rows = a.groups.slice(0, SHOWN_GROUPS).map((g) => g.map((v, i) => (i && typeof v === "number" ? count(v) : String(v))));
    return { big: `${count(a.total_groups)} 组`, note: a.without_value ? `${count(a.without_value)} 个${unit}没有可分的值` : "", table: { head, rows, total: a.total_groups } };
  }
  if (a.measure) {
    const m = a.measure;
    if (m.value == null) return { big: "没有能读成数字的值", note: `${m.skipped} 个不是数字或为空`, table: null };
    return { big: `${m.field}${m.op === "sum" ? "合计" : "平均"} ${count(m.value)}`, note: `${count(m.counted)} 个值参与${m.skipped ? `，${count(m.skipped)} 个读不出` : ""}`, table: null };
  }
  if (a.share) return { big: `${count(a.matched)} / ${count(a.total)}`, note: `${a.share.field} = ${a.share.equals} 的${unit}占 ${a.total ? Math.round((a.matched / a.total) * 1000) / 10 : 0}%`, table: null };
  return { big: unit ? `${count(a.total)} 个${unit}` : count(a.total), note: record.status === "no_data" ? record.reason ?? "" : "", table: null };
}

/** The answer, or the refusal, in one word for the history list. */
export const statusText = (status) => (status === "answered" ? "已回答" : status === "no_data" ? "没有数据" : "没回答");
export const isAnswer = (record) => record.status === "answered" || record.status === "no_data";

/** What an answer read: "订单 第 1 版". */
export const readText = (datasets) => Object.entries(datasets ?? {}).map(([name, v]) => `${name} 第 ${v} 版`);

/** The banner lines of a saved answer that is no longer as it was: a newer dataset version, a definition that is not as confirmed then. */
export function staleLines(record) {
  const data = (record.stale ?? []).map((s) => (s.now == null ? `${s.dataset} 已经不在了，这条回答读的是第 ${s.read} 版` : `${s.dataset} 有新版本：这条回答读的是第 ${s.read} 版，现在是第 ${s.now} 版`));
  const defs = (record.changed ?? []).map((c) => (!c.state ? `${c.name} 已经不在了` : c.state !== "confirmed" ? `${c.name} 现在${STATE_LABEL[c.state]}` : `${c.name} 在回答之后重新确认过`));
  return [...data, ...defs];
}

/** The heading over a saved answer's notes, by what changed: a definition that needs another look (the answer is only what was said then), a definition
 * confirmed again, or only newer data. Empty when nothing changed. */
export function staleHeading(record) {
  const changed = record.changed ?? [];
  if (changed.some((c) => c.state !== "confirmed")) return "依据的定义现在需要再看，下面是当时的答案";
  if (changed.length) return "依据的定义在回答之后重新确认过，下面是当时的答案";
  return (record.stale ?? []).length ? "数据有新版本，这条回答是旧的" : "";
}

/** The answer's figure is greyed ("当时的答案") when a definition it stood on is no longer confirmed as it was. */
export const isThenAnswer = (record) => (record.changed ?? []).length > 0;

/** Where a definition's own page is: a type or its meanings, or a relation. */
export function definitionHref(id, type = null) {
  if (id.startsWith("objview:")) return `#/types/${encodeURIComponent(type ?? "")}/views`;   // a view is shown on its type's page
  if (id.startsWith("derived:")) return `#/types/${encodeURIComponent(type ?? id.slice("derived:".length).split(":")[0])}/derived`;   // so is a derived property
  if (id.startsWith("relation:")) return `#/relations/${encodeURIComponent(id.slice("relation:".length))}`;
  const name = id.startsWith("enum:") ? id.slice("enum:".length).split(":")[0] : id.slice("objtype:".length);
  return `#/types/${encodeURIComponent(name)}`;
}

/** The line that says what a person may ask about. */
export const scopeText = (scope) => `范围：${scope.types.length} 个已确认的对象类型`;

/** Why a definition cannot be used, in the words of its state: the reason when there is one, else where it stands. */
export function standingText(d) {
  if (d.reason) return d.reason;
  if (d.state === "proposed") return "模型提出了，还没有人确认";
  if (d.state === "checked") return `${d.proposed_by ? `${d.proposed_by} 提出，` : ""}还没有另一位确认`;
  return STATE_LABEL[d.state] ?? d.state;
}

/** What the query box starts from: a count of the first type in scope, which runs as written; empty when nothing is in scope. */
export function queryExample(scope) {
  const first = scope?.types?.[0];
  return first ? `SELECT count(x) AS 数量\nFROM (x:${first.name})` : "";
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
  const eg = (list) => (list?.length ? `（例如 ${list.join("、")}）` : "");
  const ranges = (record.evidence?.filters ?? []).filter((f) => f.range && f.unreadable).map((f) => `${f.range}：${f.unreadable} 个值读不成数字或日期，没有算进去${eg(f.unreadable_examples)}`);
  const u = record.answer?.unreadable;
  return u ? [...ranges, `${u.field}：${u.count} 个值读不成日期，没有分到哪个月或哪一年${eg(u.unreadable_examples)}`] : ranges;
}

const TIME_WORD = /(本月|上个?月|这个月|今年|去年|今天|昨天|前天|本周|这周|上个?周|本季度|上季度|(?:最近|近|过去)\s*\d+\s*(?:天|日|个月|月|周|年)|\d{4}\s*年(?:\s*\d{1,2}\s*月)?|\d{1,2}\s*月份?|[一二三四五六七八九十]{1,2}月份?)/;
/** The time word in a question ("本月", "最近30天", "2026年3月"), or null. */
export function timeWord(question) {
  const m = TIME_WORD.exec(String(question ?? ""));
  return m ? m[1].replace(/\s+/g, "") : null;
}

const DATEISH = /日期|时间|创建|下单|发生|\bdate|time|\d{4}-\d{1,2}|\d{4}\/\d{1,2}|月份|年份/i;
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
  return word && !usesTime(record) ? `问题里的「${word}」没有用上：这个数是全部时间的` : null;
}

/** The one-line caliber under an answer: what was counted by which definitions, and the data as of when. Empty when the answer carries no written query. */
export function criteriaLine(record, asOf) {
  const text = String(record.query_text ?? "");
  const aliases = [...text.matchAll(/\(\s*(\w+)\s*:\s*([^)\s]+)\s*\)/g)];
  if (!aliases.length) return "";
  const alias = new Map(aliases.map((m) => [m[1], m[2]]));
  const where = /\bWHERE\b([\s\S]*?)(?:\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)/i.exec(text)?.[1]?.trim();
  const cond = where ? where.replace(/\b(\w+)\.(?=[^\s.])/g, (s, a) => (alias.has(a) ? `${alias.get(a)}.` : s)).replace(/'((?:[^']|'')*)'/g, "$1").replace(/\s+/g, " ") : `全部${aliases[0][2]}`;
  return `按已确认的定义：${cond}${asOf ? `，数据截至 ${asOf}` : ""}`;
}

/** A row of "我问过的": the question and one grey line (when, and how it went). */
export const historyView = (h, whenText) => ({ id: h.id, question: h.question, meta: `${whenText} ${statusText(h.status)}`.trim() });
