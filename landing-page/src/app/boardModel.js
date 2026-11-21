// Boards: the words of the list and the page, and the form's draft as plain functions, so they can be tested without a browser.
import { t } from "./i18n/index.js";
import { chartSpec, readyFilters } from "./explorerModel.js";
import { paramsIn } from "./qaModel.js";

export { paramsIn };

const SCOPES = ["private", "named", "everyone"];
const REFRESH_SECONDS = [0, 60, 300, 900, 3600];
const KINDS = ["number", "bar", "pie", "histogram", "table", "rows", "query"];

/** Who a board is published to, in a word: "private", "named" or "everyone". */
export const scopeLabel = (scope) => (SCOPES.includes(scope) ? t(`boards.scope.${scope}`) : scope);
/** The scopes in the order the form lists them: [[key, label]]. */
export const scopeOptions = () => SCOPES.map((k) => [k, scopeLabel(k)]);
/** How often a board reads: [[seconds, label]]. */
export const refreshOptions = () => REFRESH_SECONDS.map((s) => [s, t(`boards.refresh.${s}`)]);
/** The kinds of component a board holds: [[kind, label]]. */
export const componentKinds = () => KINDS.map((k) => [k, t(`boards.kind.${k}`)]);

/** Who a board is published to. The names come only to its author and an admin; a reader is told it is for named people. */
export const scopeText = (board) => (board.scope === "named" ? (board.visible_names ? t("boards.scope.namedList", { names: board.visible_names.join(t("ask.sep")) || t("boards.scope.nobody") }) : scopeLabel("named")) : scopeLabel(board.scope));

export const expiryText = (board) => (!board.expires_at ? t("boards.expiry.never") : board.expired ? t("boards.expiry.expired", { date: board.expires_at }) : t("boards.expiry.until", { date: board.expires_at }));

export const refreshText = (seconds) => (REFRESH_SECONDS.includes(seconds) ? t(`boards.refresh.${seconds}`) : t("boards.refresh.every", { seconds }));

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
    filters: c.query.filters ?? [], text: "",
  })),
});

const cleanParam = (p) => ({ name: p.name.trim(), label: (p.label ?? "").trim() || p.name.trim(), default: String(p.default ?? "").trim() });

/** The spec the service reads, from the form's draft. A component keeps the conditions it was saved with; the form does not edit them (the filter bar does that for the reader). */
export const specOf = (draft) => ({
  components: draft.components.map((c) => (c.kind === "query" ? { id: c.id, title: c.title.trim(), text: c.text, chart: { kind: "query" } } : {
    id: c.id, title: c.title.trim(), query: { type: c.type, view: c.view || null, filters: readyFilters(c.filters ?? []), rows: null, pivot: null },
    chart: c.kind === "rows" ? { kind: "rows" } : chartSpec(c),
  })),
  filters: draft.filters.filter((f) => f.field).map((f) => ({ field: f.field, label: (f.label || f.field).trim(), ...(f.op === "name_is" ? { op: f.op } : {}) })),
  params: (draft.params ?? []).map(cleanParam),
});

/** The payload of a save. */
export const payloadOf = (draft) => ({ name: draft.name.trim(), spec: specOf(draft), scope: draft.scope, visible_to: draft.scope === "named" ? draft.visible_to : [], expires_at: draft.expires_at || null, refresh_seconds: draft.refresh_seconds });

/** The first thing missing before the form can be saved: {key, vars} (key is a boards.problem.* word), or null when it can be saved. */
export function draftIssue(draft) {
  if (!draft.name.trim()) return { key: "name" };
  if (!draft.components.length) return { key: "components" };
  const bare = draft.components.findIndex((c) => !c.title.trim());
  if (bare >= 0) return { key: "title", vars: { n: bare + 1 } };
  const blank = draft.components.findIndex((c) => c.kind === "query" && !c.text.trim());
  if (blank >= 0) return { key: "query", vars: { n: blank + 1 } };
  const params = (draft.params ?? []).map(cleanParam);
  const twice = params.find((p, i) => params.findIndex((q) => q.name === p.name) !== i);
  if (twice) return { key: "paramTwice", vars: { name: twice.name } };
  const bareParam = params.find((p) => !p.name || !p.default);
  if (bareParam) return bareParam.name ? { key: "paramDefault", vars: { name: bareParam.name } } : { key: "paramName" };
  const missing = draft.components.filter((c) => c.kind === "query").flatMap((c) => paramsIn(c.text)).find((n) => !params.some((p) => p.name === n));
  if (missing) return { key: "paramMissing", vars: { name: missing } };
  if (draft.scope === "named" && !draft.visible_to.length) return { key: "people" };
  return null;
}

/** Whether what is missing is about the parameters (the preview waits for them). */
export const isParamIssue = (issue) => Boolean(issue?.key.startsWith("param"));

/** The first thing missing before the form can be saved, in words; "" when it can. */
export function draftProblem(draft) {
  const issue = draftIssue(draft);
  return issue ? t(`boards.problem.${issue.key}`, issue.vars) : "";
}

/** Whether the line at the top of a board should stand out: something on it is grey, waits for a confirmation or cannot be read by this person. */
/** What feeds the filter bar and parameter boxes: this read, or the last good read of the same board while a new pick loads or has failed. */
export const controlsOf = (data, last, id) => data ?? (last?.id === id ? last.data : undefined);

export const headlineStands = (headline) => Boolean(headline.grey?.length || headline.waiting?.length || headline.unavailable?.length);

/** A component's answer as the card says it: what it could not show, in words, or "". */
export const unavailableText = (component) => (component.status === "ok" ? "" : component.message);
