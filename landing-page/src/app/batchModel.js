// The words and the payload of the screen that confirms what one upload moved together, as plain functions of what the service sends, so they can be tested without a browser.
import { newValueChoices } from "./viewModel.js";

export const KIND = { type: "对象类型", meaning: "取值含义", relation: "关系", view: "视图", derived: "派生属性", action: "行为", approval: "行为提交", pipeline: "管道" };

/** The heading of a group, on the queue and on its own screen: which version of which dataset, and how many things it moved. */
export const groupTitle = (dataset, version, count) => `${dataset} 第 ${version} 版 让这 ${count} 项需要再看`;

/** What marks an item as seen: the version and the data it showed, so a mark does not outlive a change to either. */
export const markKey = (item) => `${item.element}@${item.version}@${JSON.stringify(item.seen ?? null)}`;

/** The marks with this item's set or cleared. */
export const withMark = (marks, item, on) => (on ? [...marks.filter((k) => k !== markKey(item)), markKey(item)] : marks.filter((k) => k !== markKey(item)));

/** The items the person is offered to confirm, in the order they are confirmed in. */
export const offered = (group) => group.items.filter((i) => i.ready);

/** What is still missing before "一起确认", in words; "" when nothing is. `picked`: {element: {"状态码|3": "in" | "out"}}. */
export function missing(group, marks, picked) {
  const todo = offered(group);
  if (!todo.length) return "这一组里没有你现在能确认的";
  const unseen = todo.filter((i) => !marks.includes(markKey(i)));
  if (unseen.length) return `还有 ${unseen.length} 项没有标“已看过”`;
  const open = todo.find((i) => i.new_values?.length && !newValueChoices(i.new_values, picked[i.element] ?? {}));
  return open ? `“${open.title}”的新值还没有选算不算进来` : "";
}

/** The request body's items: what the person looked at, for each item they are offered. */
export const requestItems = (group, picked) =>
  offered(group).map((i) => ({ element: i.element, version: i.version, seen: i.seen, ...(i.new_values?.length ? { new_values: newValueChoices(i.new_values, picked[i.element] ?? {}) } : {}) }));

/** What the service did, as sentences: what was confirmed, what became the other builder's to confirm, what was left out and why. */
export function resultLines(result) {
  const lines = [];
  if (result.confirmed.length) lines.push(`确认了 ${result.confirmed.length} 项：${result.confirmed.map((c) => c.title).join("、")}`);
  for (const s of result.sent_on) lines.push(`${s.title}：新值不算进来，视图的条件改了，要另一位建设者确认`);
  for (const l of result.left_out) lines.push(`${l.title}：没有确认，${l.why}`);
  return lines;
}
