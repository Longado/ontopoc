// The review stack on 要确认的事: the card in front, the replies it offers (the service declares them per kind, in key order),
// and what a reply sends. Which replies a kind offers is the service's (review_stack.py); the words here only say them.
import { itemChoices } from "./cardModel.js";

export const MODE_SAYS = { single: "逐件判断", bulk: "批量确认" };

/** "还剩 7 件，已定 4 件"; when nothing is left, how many were decided. Empty when there was nothing to decide. */
export function stackLine(open, decided) {
  if (open) return `还剩 ${open} 件，已定 ${decided} 件`;
  return decided ? `都定了，共 ${decided} 件` : "";
}

/** The reply a key picks on this card (1 to 4, in the order the service lists them); null for a key with no reply. */
export const replyForKey = (item, key) => (/^[1-4]$/.test(key) ? item.replies?.[Number(key) - 1] ?? null : null);

/** Where J (next) and K (previous) go from `index` in a stack of `length`; they stop at the ends. */
export function movedIndex(index, key, length) {
  const to = key === "j" ? index + 1 : key === "k" ? index - 1 : index;
  return Math.max(0, Math.min(length - 1, to));
}

/** A key typed into a box is the box's. */
export const isTyping = (target) => Boolean(target) && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable === true);

// the kinds that are answered where their own definition is made (the labels of a code column, the rule of a repeated key)
const OWN_ENDPOINT = { code_meaning: ["confirm", "not_applicable"], repeated_key: ["keep_both", "keep_latest", "data_error"] };

/** Where a reply goes: "code" (meanings, or "not a code"), "repeat" (a rule), or "card" (kept with the file's answers). */
export function replyRoute(item, reply) {
  if (!OWN_ENDPOINT[item.kind]?.includes(reply.id)) return "card";
  return item.kind === "code_meaning" ? "code" : "repeat";
}

/** The words a reply asks for, and whether they are required; null when it asks for none. */
export function replyAsks(item, reply) {
  if (reply.id === "exception") return { label: "原因", required: true };
  if (reply.id === "wrong") return { label: "对的是什么", required: true };
  if (reply.needs_text) return { label: "客户怎么答的", required: true };
  return replyRoute(item, reply) === "card" ? { label: "补充说明（选填）", required: false } : null;
}

/** What stops a reply from being sent, in words; "" when it can go. `form` is { text, basis, column }. */
export function replyProblem(item, reply, form, by) {
  if (!by.trim()) return "先填确认人";
  if (by.trim().length > 40) return "确认人最多 40 个字";
  const asks = replyAsks(item, reply);
  if (asks?.required && !form.text.trim()) return `先写${asks.label}`;
  if (reply.id === "keep_latest" && !form.column) return "选一列，按它的大小定哪一行最新";
  return "";
}

/** The entry for the card endpoint: a kind's own choice goes as `choice`, a general reply as `reply`. */
export function cardEntry(item, reply, form) {
  const [text, basis] = [form.text.trim(), form.basis.trim()];
  const own = itemChoices(item).some(([value]) => value === reply.id);
  return { id: item.id, ...(own ? { choice: reply.id } : { reply: reply.id }), ...(text ? { text } : {}), ...(basis ? { basis } : {}) };
}

/** What a reply says it did, for the list of decisions: who, how it was decided, and the reason. */
export const decidedHow = (answer) => MODE_SAYS[answer?.mode] || "";

/** An old decision brought back by a change in the data, in the words under the card's title. */
export function reopenedLine(reopened) {
  const said = `${reopened.by} 上次记为“${reopened.says}”${reopened.text ? `（${reopened.text}）` : ""}`;
  return `${said}，现在数据变了：${reopened.changes.join("；")}。`;
}

// The clean band: what can be approved together once the list is shown. The service works the band out; the page only lists it.
export const BULK_KIND = { relation: "关系" };
export const bulkSummary = (band) => `有 ${band.length} 件数据全部核对过了，可以一起通过`;
export const bulkLabel = (count) => `一起通过 ${count} 件`;

/** What stops a bulk approval, in words; "" when it can go. */
export function bulkProblem(ids, by) {
  if (!ids.length) return "先勾上要通过的";
  if (!by.trim()) return "先填确认人";
  return by.trim().length > 40 ? "确认人最多 40 个字" : "";
}
