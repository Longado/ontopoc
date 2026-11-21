// The 待确认 queue as plain functions of what the service sends: one compact row for each item, what can be done with it in the row, the counts, and the calls a batch makes.
import { KIND } from "./batchModel.js";
import { t } from "./i18n/index.js";
import { joinList } from "./typeModel.js";
import { itemAction } from "./relationModel.js";

/** A queue item as a row: its kind in words, one summary line, the problems apart from it (an error is a line the service marks strong: rows that belong to nobody), and the one
 * thing a person may do in the row: "confirm" (a definition), "approve" (a submitted change), "withdraw" (their own submission), "open" (it is confirmed on its own screen),
 * "repropose" (the meanings are written again), "blocked" (something else first) or "wait" (someone else confirms). */
export const TAG = {};
for (const k of ["approval", "pipeline", "definition"]) Object.defineProperty(TAG, k, { get: () => t(`review.tag.${k}`), enumerable: true });

/** The legend at the top of the queue: which verb is for what. */
export const queueLegend = () => t("review.legend");

/** What to say before Approve on a submitted change, which writes a new version of its dataset: the definitions reading that dataset are checked again and may need another
 * look. "" for anything else. `item.readers`: how many confirmed definitions read it (null when not known). */
export function approveWarning(item) {
  if (item.kind !== "approval") return "";
  const data = item.dataset ? t("review.warn.named", { name: item.dataset }) : t("review.warn.generic");
  if (item.readers === 0) return t("review.warn.none", { data });
  if (item.readers == null) return t("review.warn.unknown", { data });
  return t("review.warn.readers", { data, count: item.readers });
}

export function queueRow(item) {
  const lines = item.lines ?? [];
  const [first] = lines;
  let mode;
  if (item.kind === "approval") mode = item.can_confirm ? "approve" : item.can_withdraw ? "withdraw" : "wait";
  else if (item.kind === "pipeline") mode = item.can_confirm ? "open" : "wait";
  else if ((item.kind === "view" || item.kind === "derived") && item.can_confirm && item.new_values?.length) mode = "open";   // the new values are picked on the view's (or derived property's) own page first
  else mode = itemAction(item);
  return {
    kind: KIND[item.kind] ?? item.kind, verb: item.kind === "approval" ? t("review.row.approve") : t("review.row.confirm"), tag: TAG[item.kind] ?? TAG.definition, title: item.title, summary: first?.text ?? "", summaryLevel: !first || first.ok ? "ok" : first.strong ? "error" : "warn",
    problems: lines.slice(1).filter((l) => !l.ok).map((l) => ({ text: l.text, level: l.strong ? "error" : "warn" })),
    hasError: lines.some((l) => l.strong), mode,
    canReject: mode === "confirm" || mode === "approve" || (item.kind === "approval" && item.state === "needs_look" && mode !== "withdraw"),
  };
}

/** A sending back, and a rejection of a submission, both say what is wrong; "" when they do. */
export const rejectProblem = (reason) => (String(reason ?? "").trim() ? "" : t("review.reject.reason"));

/** How many items, and how many of them this person can confirm now: the same number the navigation shows. */
export function queueCounts(data) {
  const all = data.items.length;
  const mine = data.items.filter((i) => i.can_confirm).length;
  return { mine, all, text: all ? t("review.counts.some", { count: all, mine }) : t("review.counts.none") };
}

/** Items with a real problem first, the rest in the order the service gave them. */
export const sortByProblem = (items) => [...items.filter((i) => queueRow(i).hasError), ...items.filter((i) => !queueRow(i).hasError)];

/** The calls a batch makes: for each picked item that can be confirmed or approved in its row, in the order shown. */
export function batchPlan(items, picked) {
  const plan = [];
  for (const item of items) {
    if (!picked.has(item.element)) continue;
    const { mode } = queueRow(item);
    if (mode === "confirm") plan.push({ key: item.element, title: item.title, call: "confirm", element: item.element, version: item.version, seen: item.seen });
    else if (mode === "approve") plan.push({ key: item.element, title: item.title, call: "approve", record: item.record });
  }
  return plan;
}

/** What a batch did: how many went through, and each that did not with the service's words. */
export function batchSummary(results) {
  if (!results.length) return "";
  const done = results.filter((r) => r.ok);
  const failed = results.filter((r) => !r.ok);
  return t("review.batch.done", { count: done.length }) + (failed.length ? t("review.batch.failed", { count: failed.length, list: joinList(failed.map((f) => t("review.batch.failedItem", { title: f.title, error: f.error }))) }) : "");
}
