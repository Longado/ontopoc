// The home page's words and decisions, as plain functions of what the service sends, so they can be tested without a browser.
import { timeText } from "./format.js";

const confirmed = (list) => (list ?? []).filter((x) => x.state === "confirmed");

/** Whether the workspace cannot answer anything yet: no dataset, or no confirmed object type. */
export const needsSetup = ({ datasets, types }) => !(datasets ?? []).length || !confirmed(types).length;

/** The four steps of 开始使用: [{key, title, text, state: "done" | "next" | "todo", button: {label, href} | null}].
 * `users` and `sources` are null when this person may not read them (a builder cannot list users). */
export function setupSteps({ datasets, types, users, role }) {
  const admin = role === "admin";
  const done = {
    data: (datasets ?? []).length > 0,
    type: (types ?? []).length > 0,
    confirm: confirmed(types).length > 0,
    invite: (users ?? []).length > 1,
  };
  const steps = [
    { key: "data", title: "接入数据", text: admin ? "上传 Excel、CSV，或连一个数据库，把表读进来。" : "上传 Excel 或 CSV 表格。数据库由管理员接入。", button: { label: "去传数据", href: "#/datasets" } },
    { key: "type", title: "建对象类型", text: "把表变成业务里的东西，比如“订单”“客户”，并写清每一列的含义。", button: { label: "新建对象类型", href: "#/types/new" } },
    { key: "confirm", title: "请另一位建设者确认", text: "确认过的定义才能拿来回答问题。", button: { label: "去待确认", href: "#/confirm" } },
    admin
      ? { key: "invite", title: "邀请同事", text: "建设者能改数据和定义，查看者只提问、看看板。", button: { label: "去用户页", href: "#/users" } }
      : { key: "invite", title: "邀请同事", text: "新用户由管理员在“设置 · 用户”里添加，请联系管理员。", button: null },
  ];
  let nextFound = false;
  return steps.map((s) => {
    if (done[s.key]) return { ...s, state: "done" };
    if (!nextFound) {
      nextFound = true;
      return { ...s, state: "next" };
    }
    return { ...s, state: "todo" };
  });
}

/** Up to six questions to try, from what is confirmed: "订单 一共有多少" for each type, then "按客户统计订单" for each confirmed relation between confirmed types. */
export function exampleQuestions(types, relations, max = 6) {
  const known = confirmed(types);
  const names = new Set(known.map((t) => t.name));
  const counts = known.slice(0, 3).map((t) => `${t.name} 一共有多少`);
  const by = confirmed(relations).filter((r) => names.has(r.from_name) && names.has(r.to_name)).map((r) => `按${r.to_name}统计${r.from_name}`);
  const rest = known.slice(3).map((t) => `${t.name} 一共有多少`);
  return [...counts, ...by, ...rest].slice(0, max);
}

/** "陈总，早上好" by the hour (before noon morning, before 18:00 afternoon, else evening). */
export function greeting(date, name) {
  const h = date.getHours();
  const word = h >= 5 && h < 12 ? "早上好" : h >= 12 && h < 18 ? "下午好" : "晚上好";
  return name ? `${name}，${word}` : word;
}

/** "数据更新于 2026-11-16 18:30": the newest dataset's time; empty with no dataset. */
export function updatedText(datasets) {
  const times = (datasets ?? []).map((d) => d.updated_at).filter(Boolean).sort();
  return times.length ? `数据更新于 ${timeText(times[times.length - 1])}` : "";
}

/** What waits for this person, most urgent first: [{key, count, text, href}]. Only builders see the confirm queue and failed runs. */
export function todoItems({ unread = 0, queue = 0, failedRuns = 0, mayBuild = false }) {
  const items = [];
  if (mayBuild && queue > 0) items.push({ key: "queue", count: queue, text: `${queue} 项等你确认`, href: "#/confirm" });
  if (mayBuild && failedRuns > 0) items.push({ key: "failed", count: failedRuns, text: `${failedRuns} 次运行失败`, href: "#/tasks" });
  if (unread > 0) items.push({ key: "notices", count: unread, text: `${unread} 条未读消息`, href: "#/notices" });
  return items;
}
