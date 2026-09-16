// Acceptance questions: the few questions a person fixes for a file, so the next run is judged on the same questions.
import { STATUS_LABELS } from "./ontologyStudioModel.js";

export const MAX_ACCEPTANCE = 3;
export const ACCEPTANCE_LABELS = { ...STATUS_LABELS, broken: "查询失效" };

export const savedAcceptance = (run) =>
  (run.evaluation.acceptance?.items || []).map(({ question, query, note }) => ({ question, query, note }));

/** "" when this answered question can be fixed as an acceptance question, else why not. */
export function canAccept(run, item) {
  if (!run.saved_as) return "这是示例结果，上传自己的文件后可以存";
  if (item.status !== "answered" || !item.query) return "只能把已经答出来的问题存为验收问题";
  const saved = savedAcceptance(run);
  if (saved.some((s) => s.question === item.question)) return "这道已经是验收问题了";
  if (saved.length >= MAX_ACCEPTANCE) return `验收问题最多 ${MAX_ACCEPTANCE} 道，先去掉一道`;
  return "";
}

export function acceptanceSummary(acceptance) {
  const changed = acceptance.items.filter((i) => i.changed).length;
  const since = acceptance.items.some((i) => i.changed !== null) ? `${changed} 道和上次不一样` : "第一次执行";
  return `${acceptance.total} 道里能答 ${acceptance.answered} 道，${since}`;
}
