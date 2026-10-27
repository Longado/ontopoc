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

/** What an empty list means: nothing found, or nothing looked for because the ontology never passed verification. */
export const openItemsEmpty = (run) => (run.ontology.status === "auto_built_verified"
  ? "代码没有找到要和客户确认的事。" : "本体还没通过核验，代码先不列要确认的事。");
