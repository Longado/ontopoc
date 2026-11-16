// Boards (看板): the words of the list and the page, and the form's draft as plain functions, so they can be tested without a browser.
import { chartSpec, readyFilters } from "./explorerModel.js";
import { paramsIn } from "./qaModel.js";

export { paramsIn };

export const SCOPE_LABEL = { private: "只有我", named: "指定的人", everyone: "所有登录的人" };
export const REFRESH_OPTIONS = [[0, "只在打开时读"], [60, "每分钟"], [300, "每 5 分钟"], [900, "每 15 分钟"], [3600, "每小时"]];
export const COMPONENT_KINDS = [["number", "指标卡"], ["bar", "柱状图"], ["pie", "饼图"], ["histogram", "直方图"], ["table", "统计表"], ["rows", "明细表"], ["query", "本体查询"]];

/** Who may open a board, in words; the people are named when the scope names them. */
/** Who a board is published to. The names come only to its author and an admin; a reader is told it is for named people. */
export const scopeText = (board) => (board.scope === "named" ? (board.visible_names ? `指定的人：${board.visible_names.join("、") || "没有人"}` : "指定的人") : SCOPE_LABEL[board.scope] ?? board.scope);

export const expiryText = (board) => (!board.expires_at ? "不过期" : board.expired ? `${board.expires_at} 已过期，只有主人和管理员打得开` : `到 ${board.expires_at}`);

export const refreshText = (seconds) => (REFRESH_OPTIONS.find(([s]) => s === seconds) ?? [0, `每 ${seconds} 秒`])[1];

/** The link a person copies: the board's own address in the app. Opening it asks for a sign-in first. */
export const shareLink = (origin, id) => `${origin}/#/boards/${id}`;

export const emptyComponent = (type, n) => ({ id: `c${n}`, title: "", type, view: "", kind: "number", group: "", measure: "", fn: "count", bins: 10, top: "", order: "", text: "" });

export const emptyDraft = () => ({ name: "", components: [], filters: [], params: [], scope: "private", visible_to: [], expires_at: "", refresh_seconds: 0 });

/** The values a board is worked out with: what the reader typed for each parameter the board has; an empty one is left out, so the board's default is used. */
export const paramValues = (params, typed) => Object.fromEntries((params ?? []).filter((p) => String(typed?.[p.name] ?? "").trim()).map((p) => [p.name, String(typed[p.name]).trim()]));

/** The form's draft from a saved board. */
export const draftOf = (board) => ({
  name: board.name, scope: board.scope, visible_to: board.visible_to, expires_at: board.expires_at ?? "", refresh_seconds: board.refresh_seconds, filters: board.spec.filters.map((f) => ({ ...f })),
  params: (board.spec.params ?? []).map((p) => ({ ...p })),
  components: board.spec.components.map((c) => (c.text !== undefined ? { ...emptyComponent("", 0), id: c.id, title: c.title, kind: "query", text: c.text } : {
    id: c.id, title: c.title, type: c.query.type, view: c.query.view ?? "", kind: c.chart.kind, group: c.chart.group ?? "", measure: c.chart.measure ?? "", fn: c.chart.fn ?? "count", bins: c.chart.bins ?? 10, top: c.chart.top ? String(c.chart.top) : "", order: c.chart.order ?? "",
    filters: c.query.filters ?? [],
  })),
});

const cleanParam = (p) => ({ name: p.name.trim(), label: (p.label ?? "").trim() || p.name.trim(), default: String(p.default ?? "").trim() });

/** The spec the service reads, from the form's draft. A component keeps the conditions it was saved with; the form does not edit them (the filter bar does that for the reader). */
export const specOf = (draft) => ({
  components: draft.components.map((c) => (c.kind === "query" ? { id: c.id, title: c.title.trim(), text: c.text, chart: { kind: "query" } } : {
    id: c.id, title: c.title.trim(), query: { type: c.type, view: c.view || null, filters: readyFilters(c.filters ?? []), rows: null, pivot: null },
    chart: c.kind === "rows" ? { kind: "rows" } : chartSpec(c),
  })),
  filters: draft.filters.filter((f) => f.field).map((f) => ({ field: f.field, label: (f.label || f.field).trim() })),
  params: (draft.params ?? []).map(cleanParam),
});

/** The payload of a save. */
export const payloadOf = (draft) => ({ name: draft.name.trim(), spec: specOf(draft), scope: draft.scope, visible_to: draft.scope === "named" ? draft.visible_to : [], expires_at: draft.expires_at || null, refresh_seconds: draft.refresh_seconds });

/** The first thing missing before the form can be saved, in words; "" when it can. */
export function draftProblem(draft) {
  if (!draft.name.trim()) return "要写看板的名字";
  if (!draft.components.length) return "至少加一个组件";
  const bare = draft.components.findIndex((c) => !c.title.trim());
  if (bare >= 0) return `第 ${bare + 1} 个组件要写标题`;
  const blank = draft.components.findIndex((c) => c.kind === "query" && !c.text.trim());
  if (blank >= 0) return `第 ${blank + 1} 个组件要写查询`;
  const params = (draft.params ?? []).map(cleanParam);
  const twice = params.find((p, i) => params.findIndex((q) => q.name === p.name) !== i);
  if (twice) return `参数名 $${twice.name} 重复了`;
  const bareParam = params.find((p) => !p.name || !p.default);
  if (bareParam) return bareParam.name ? `参数 $${bareParam.name} 要写默认值` : "参数要写名字";
  const missing = draft.components.filter((c) => c.kind === "query").flatMap((c) => paramsIn(c.text)).find((n) => !params.some((p) => p.name === n));
  if (missing) return `查询里用到 $${missing}，要在参数里加上它和默认值`;
  if (draft.scope === "named" && !draft.visible_to.length) return "指定的人至少选一位";
  return "";
}

/** Whether the line at the top of a board should stand out: something on it is grey, waits for a confirmation or cannot be read by this person. */
export const headlineStands = (headline) => Boolean(headline.grey?.length || headline.waiting?.length || headline.unavailable?.length);

/** A component's answer as the card says it: what it could not show, in words, or "". */
export const unavailableText = (component) => (component.status === "ok" ? "" : component.message);
