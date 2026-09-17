// Acceptance questions: the few questions a person fixes for a file, so the next run is judged on the same questions.
import { STATUS_LABELS } from "./ontologyStudioModel.js";

export const MAX_ACCEPTANCE = 3;
export const ACCEPTANCE_LABELS = { ...STATUS_LABELS, broken: "查询失效" };
const UNMET = ["query_limit", "ontology_gap"];   // asked, and no query could be written

// An unmet question has no query to run again, so why it is unmet has to travel with it.
const kept = ({ question, query, note, status, reason }) => (query ? { question, query, note } : { question, query: null, note, status, reason });

export const savedAcceptance = (run) => (run.evaluation.acceptance?.items || []).map(kept);

/** "" when this question can be fixed as an acceptance question, else why not. A question nothing can answer yet
 *  can be fixed too: otherwise the ones that pass hide the one the client actually asked for. */
export function canAccept(run, item) {
  if (!run.saved_as) return "这是示例结果，上传自己的文件后可以存";
  const unmet = !item.query && UNMET.includes(item.status) && Boolean(item.reason);
  if (!unmet && (item.status !== "answered" || !item.query)) return "只能把已经答出来的问题存为验收问题";
  const saved = savedAcceptance(run);
  const same = saved.find((s) => s.question === item.question);
  if (same && (same.query || unmet)) return "这道已经是验收问题了";
  if (!same && saved.length >= MAX_ACCEPTANCE) return `验收问题最多 ${MAX_ACCEPTANCE} 道，先去掉一道`;
  return "";
}

/** The list to save once this question is fixed; an answer a person agrees with takes the place of the same question unmet. */
export const acceptItem = (saved, item, note) =>
  [...saved.filter((s) => s.question !== item.question), kept({ ...item, note: note.trim() })];

export function acceptanceSummary(acceptance) {
  const changed = acceptance.items.filter((i) => i.changed).length;
  const unmet = acceptance.items.filter((i) => !i.query).length;
  const since = acceptance.items.some((i) => i.changed !== null) ? `${changed} 道和上次不一样` : "第一次执行";
  return `${acceptance.total} 道里能答 ${acceptance.answered} 道，${unmet ? `${unmet} 道现在还答不了，` : ""}${since}`;
}

/** A confirmation is a judgement made for one purpose; prefilled under another, it is a starting point and no more. */
export function purposeNote(run) {
  const was = run.evaluation?.reference?.purpose;
  return was && was !== run.purpose ? `上次确认时的建模目的是“${was}”，和这次的不一样。上次的判断只是预先填好，不代表对这次的目的也成立，请逐项再看。` : "";
}
