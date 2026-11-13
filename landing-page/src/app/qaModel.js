// The words of the Q&A page, as plain functions of what the service sends, so they can be tested without a browser.
import { STATE_LABEL } from "./typeModel.js";

const count = (n) => Number(n).toLocaleString("en-US");
const SHOWN_GROUPS = 20;

/** An answer from the engine (a count, a share, a total, or groups) as what the card shows: {big, note, table: {head, rows, total} | null}. */
export function answerView(record) {
  const a = record.answer;
  if (!a) return null;
  const unit = a.relation_gap?.many ?? record.types?.[0]?.name ?? "";
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
  const defs = (record.changed ?? []).map((c) => (c.state && c.state !== "confirmed" ? `${c.name} 现在${STATE_LABEL[c.state]}` : `${c.name} 在回答之后重新确认过`));
  return [...data, ...defs];
}

/** Where a definition's own page is: a type or its meanings, or a relation. */
export function definitionHref(id, type = null) {
  if (id.startsWith("objview:")) return `#/types/${encodeURIComponent(type ?? "")}/views`;   // a view is shown on its type's page
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
