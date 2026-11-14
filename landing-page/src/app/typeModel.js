// The words of the object type pages, as plain functions of what the service sends, so they can be tested without a browser.
import { timeText } from "./format.js";

export const STATE_LABEL = { proposed: "已提出", checked: "已检查", confirmed: "已确认", needs_look: "需再看", rejected: "已退回" };

/** The state chip's word. A model's draft says so; a code column nobody gave meanings to has no state. */
export function stateText(item) {
  if (item.model_draft) return "模型草稿";
  return item.state ? STATE_LABEL[item.state] : "还没有含义";
}

const versionsText = (on) => Object.entries(on ?? {}).map(([name, v]) => `${name} 第 ${v} 版`).join("、");

/** One sentence under the title: who stands behind it, or what it is waiting for. `noun` is what the item is ("这个对象类型", "这组含义"). */
export function stateLine(item, noun) {
  const confirmed = item.confirmed_by ? `${item.confirmed_by} 于 ${timeText(item.confirmed_at)} 确认，依据 ${versionsText(item.confirmed_on)}` : "";
  if (item.state === "confirmed") return confirmed;
  if (item.state === "rejected") return `${item.proposed_by ? `${item.proposed_by} 提出的，` : ""}被退回了；改好重新保存，再由另一位确认`;
  if (item.state === "needs_look") return confirmed ? `原来是 ${confirmed}；之后数据变了，要再看一次` : `${noun}需要再看一次`;
  if (item.model_draft) return `模型写的草稿，还没有人看过，确认前问答和智能体不会用它`;
  if (item.state === "proposed" || item.state === "checked") {
    const by = item.proposed_by ? `${item.proposed_by} 提出，` : "";
    return item.can_confirm ? `${by}等你或另一位构建者确认` : `${by}需要另一位构建者确认`;
  }
  return "";
}

/** Who could confirm, when it is waiting for someone and the reader is not one of them. */
export const confirmersText = (item) => (item.confirmers?.length && !item.can_confirm ? `可以确认的人：${item.confirmers.join("、")}` : "");

const DATASET_LINE = [
  [/^import v(\d+)/, (m) => `上传了第 ${m[1]} 版`],
  [/^v(\d+) is current again/, (m) => `第 ${m[1]} 版重新成为当前版本`],
  [/^no change/, () => "上传了，内容没有变化"],
];

/** One line of the log as a sentence: {who, text}. */
export function logText(e) {
  const what = e.element === "meaning" ? `“${e.column}”的含义` : e.element === "pipeline" ? "管道" : e.element === "relation" ? "关系" : e.element === "view" ? "视图" : e.element === "action" ? "行为" : "对象类型";
  if (e.element === "dataset") {
    const hit = DATASET_LINE.map(([re, say]) => [re.exec(e.change), say]).find(([m]) => m);
    return { who: e.who, text: hit ? hit[1](hit[0]) : e.change };
  }
  if (e.change.startsWith("action_") || e.change === "row_rules_changed" || e.change === "run" || e.change === "run_failed") return { who: e.who, text: e.text };   // the service writes these lines as sentences
  if (e.change === "needs_look") return { who: "系统", text: `${what}需再看：${e.reason}${e.caused_by ? `（${e.caused_by} 的上传）` : ""}` };
  if (e.change === "confirmed") return { who: e.who, text: `确认了${what}${e.self_confirmed ? "（自己提的；只有一位构建者，两人确认没有生效）" : ""}` };
  if (e.change === "sent_back") return { who: e.who, text: `退回了${what}：${e.reason}` };
  if (e.change === "access_changed") return { who: e.who, text: `改了可见范围：${e.visible_to === "everyone" ? "所有人" : e.visible_to?.length ? e.visible_to.join("、") : "只有管理员"}` };
  if (e.change === "meanings_retired") return { who: e.who, text: `去掉了这些列的含义（${e.reason}）：${e.text}` };
  if (e.change === "edited") return { who: e.who, text: `改了名称或说明：${e.text}` };
  if (e.change === "checked" || e.change === "proposed") return { who: e.who, text: `提出了${what}` };
  return { who: e.who, text: `${what}：${e.change}` };
}

/** A code cell on the objects tab: the value, and next to it what it means when that is confirmed, else why it is not shown as meaning. */
export function codeCell(value, enumState) {
  if (value == null) return { value: "", note: "" };
  const label = enumState?.labels?.[value];
  if (enumState?.state === "confirmed" && label) return { value, note: label };
  if (enumState?.state === "needs_look") return { value, note: "含义需再看" };
  return { value, note: "含义未确认" };
}

/** What a column of the dataset may be declared as, the first being what it is now. */
export const TYPE_CHOICES = {
  integer: ["integer", "decimal", "text"], decimal: ["decimal", "text"], text: ["text"], date: ["date", "datetime", "text"],
  month: ["month", "text"], datetime: ["datetime", "text"], boolean: ["boolean", "text"],
};

/** A key column the service would refuse, and why, before anything is sent; "" when it is fine. */
export function keyProblem(column) {
  if (column.type === "decimal") return `“${column.name}”是小数列，不能做主键`;
  if (column.type === "boolean") return `“${column.name}”是是/否列，不能做主键`;
  return "";
}

/** The payload that creates or changes a type, from the form. `form.columns`: {name, type, include, label, declared, enum, meanings: {value: label}} per dataset column. */
export function typePayload(form) {
  const columns = form.columns.filter((c) => c.include || form.key.includes(c.name));
  const enums = Object.fromEntries(columns.filter((c) => c.enum).map((c) => [c.name, Object.entries(c.meanings ?? {}).filter(([, label]) => label.trim()).map(([value, label]) => ({ value, label: label.trim() }))]).filter(([, v]) => v.length));
  return {
    english_name: form.english.trim(), name: form.name.trim(), description: form.description.trim(), dataset: form.dataset, key: form.key,
    properties: columns.map((c) => ({ column: c.name, name: c.label.trim() || c.name, type: c.declared, enum: c.enum })), enums,
  };
}
