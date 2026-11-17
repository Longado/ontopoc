// The words and the payload of the screen that confirms what one upload moved together, as plain functions of what the service sends, so they can be tested without a browser.
import { t } from "./i18n/index.js";
import { joinList } from "./typeModel.js";
import { newValueChoices } from "./viewModel.js";

const worded = (keys, prefix) => {
  const o = {};
  for (const k of keys) Object.defineProperty(o, k, { get: () => t(`${prefix}.${k}`), enumerable: true });
  return o;
};


export const KIND = worded(["type", "meaning", "relation", "view", "derived", "action", "approval", "pipeline"], "review.kind");

/** The heading of a group, on the queue and on its own screen: which version of which dataset, and how many things it moved. */
export const groupTitle = (dataset, version, count) => t("review.group.title", { dataset, version, count });

/** What marks an item as seen: the version and the data it showed, so a mark does not outlive a change to either. */
export const markKey = (item) => `${item.element}@${item.version}@${JSON.stringify(item.seen ?? null)}`;

/** The marks with this item's set or cleared. */
export const withMark = (marks, item, on) => (on ? [...marks.filter((k) => k !== markKey(item)), markKey(item)] : marks.filter((k) => k !== markKey(item)));

/** The items the person is offered to confirm, in the order they are confirmed in. */
export const offered = (group) => group.items.filter((i) => i.ready);

/** What is still missing before "Confirm together", in words; "" when nothing is. `picked`: {element: {"status|3": "in" | "out"}}. */
export function missing(group, marks, picked) {
  const todo = offered(group);
  if (!todo.length) return t("review.batch.missingAll");
  const unseen = todo.filter((i) => !marks.includes(markKey(i)));
  if (unseen.length) return t("review.batch.unseen", { count: unseen.length });
  const open = todo.find((i) => i.new_values?.length && !newValueChoices(i.new_values, picked[i.element] ?? {}));
  return open ? t("review.batch.newValues", { title: open.title }) : "";
}

/** The request body's items: what the person looked at, for each item they are offered. */
export const requestItems = (group, picked) =>
  offered(group).map((i) => ({ element: i.element, version: i.version, seen: i.seen, ...(i.new_values?.length ? { new_values: newValueChoices(i.new_values, picked[i.element] ?? {}) } : {}) }));

/** What the service did, as sentences: what was confirmed, what became the other builder's to confirm, what was left out and why. */
export function resultLines(result) {
  const lines = [];
  if (result.confirmed.length) lines.push(t("review.batch.confirmed", { count: result.confirmed.length, titles: joinList(result.confirmed.map((c) => c.title)) }));
  for (const s of result.sent_on) lines.push(t("review.batch.sentOn", { title: s.title }));
  for (const l of result.left_out) lines.push(t("review.batch.leftOut", { title: l.title, why: l.why }));
  return lines;
}
