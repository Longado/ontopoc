// The words of the object type pages, as plain functions of what the service sends, so they can be tested without a browser.
import { timeText } from "./format.js";
import { t } from "./i18n/index.js";
import { TYPE_TABS } from "./routeModel.js";
import { WORD_LIST, WORDS } from "./typeWords.js";

const STATES = ["proposed", "checked", "confirmed", "needs_look", "rejected"];
/** The word of each state a definition can be in; read it as STATE_LABEL[state] (it follows the language). */
export const STATE_LABEL = {};
for (const k of STATES) Object.defineProperty(STATE_LABEL, k, { get: () => t(`types.state.${k}`), enumerable: true });

export const joinList = (items) => items.join(t("types.sep"));
export const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);

/** The state chip's word. A model's draft says so; a code column nobody gave meanings to has no state. */
export function stateText(item) {
  if (item.model_draft) return t("types.state.modelDraft");
  return item.state ? STATE_LABEL[item.state] : t("types.state.none");
}

const versionsText = (on) => joinList(Object.entries(on ?? {}).map(([name, version]) => t("types.line.versionOf", { name, version })));

/** One sentence under the title: who stands behind it, or what it is waiting for. `noun` is what the item is ("This object type", "This set of meanings"). */
export function stateLine(item, noun) {
  const confirmed = item.confirmed_by ? t("types.line.confirmed", { who: item.confirmed_by, time: timeText(item.confirmed_at), versions: versionsText(item.confirmed_on) }) : "";
  if (item.state === "confirmed") return confirmed;
  if (item.state === "rejected") return item.proposed_by ? t("types.line.rejectedBy", { who: item.proposed_by }) : t("types.line.rejected");
  if (item.state === "needs_look") return confirmed ? t("types.line.needsLookWas", { confirmed }) : t("types.line.needsLook", { noun });
  if (item.model_draft) return t("types.line.modelDraft");
  if (item.state === "proposed" || item.state === "checked") {
    const by = item.proposed_by ? t("types.line.proposedBy", { who: item.proposed_by }) : "";
    return t(item.can_confirm ? "types.line.mayConfirm" : "types.line.needsConfirm", { by });
  }
  return "";
}

/** What a viewer reads of an object type whose data moved after it was confirmed: it is there, it waits for a second look. */
export const reconfirmText = (names) => t("types.line.reconfirm", { who: names?.length ? joinList(names) : t("types.line.reconfirmAnyone") });

/** Who could confirm, when it is waiting for someone and the reader is not one of them. */
export const confirmersText = (item) => (item.confirmers?.length && !item.can_confirm ? t("types.line.confirmers", { names: joinList(item.confirmers) }) : "");

const DATASET_LINE = [
  [/^import v(\d+)/, (m) => t("types.dataset.import", { version: m[1] })],
  [/^v(\d+) is current again/, (m) => t("types.dataset.current", { version: m[1] })],
  [/^no change/, () => t("types.dataset.nochange")],
];

const WHAT = { pipeline: "pipeline", relation: "relation", view: "view", derived: "derived", action: "action" };

/** One line of the log as a sentence: {who, text}; a line written with a token says so, with the token's label. */
export function logText(e) {
  const line = logSentence(e);
  if (e.with_token == null) return line;
  return { ...line, text: `${line.text ?? ""}${e.with_token ? t("types.log.withToken", { label: e.with_token }) : t("types.log.withTokenNoLabel")}` };
}

function logSentence(e) {
  const what = e.element === "meaning" ? t("types.what.meaning", { column: e.column }) : t(`types.what.${WHAT[e.element] ?? "type"}`);
  if (e.element === "dataset") {
    const hit = DATASET_LINE.map(([re, say]) => [re.exec(e.change), say]).find(([m]) => m);
    return { who: e.who, text: hit ? hit[1](hit[0]) : e.change };
  }
  if (e.change.startsWith("action_") || e.change === "row_rules_changed" || e.change === "column_access_changed" || e.change === "run" || e.change === "run_failed") return { who: e.who, text: e.text };   // the service writes these lines as sentences
  if (e.change === "needs_look") return { who: t("types.log.system"), text: t("types.log.needsLook", { what, reason: e.reason, cause: e.caused_by ? t("types.log.cause", { who: e.caused_by }) : "" }) };
  if (e.change === "confirmed") return { who: e.who, text: t("types.log.confirmed", { what, self: e.self_confirmed ? t("types.log.self") : "" }) };
  if (e.change === "confirmed_together") return { who: e.who, text: e.text };   // the service writes it as a sentence: confirmed together with 3 others
  if (e.change === "sent_back") return { who: e.who, text: t("types.log.sentBack", { what, reason: e.reason }) };
  if (e.change === "access_changed") return { who: e.who, text: t("types.log.access", { to: e.visible_to === "everyone" ? t("types.log.everyone") : e.visible_to?.length ? joinList(e.visible_to) : t("types.admins") }) };
  if (e.change === "meanings_retired") return { who: e.who, text: t("types.log.retired", { reason: e.reason, text: e.text }) };
  if (e.change === "edited") return { who: e.who, text: t("types.log.edited", { text: e.text }) };
  if (e.change === "checked" || e.change === "proposed") return { who: e.who, text: t("types.log.proposed", { what }) };
  if (e.change === "dbt_import") return { who: e.who, text: t("types.log.dbtImport", { what }) };   // where it came from: the service writes this line with the proposal (dbt_import)
  return { who: e.who, text: t("types.log.other", { what: capital(what), change: e.change }) };
}

/** The one line on a type's page for someone a row rule limits: their own rows of this type, and the other types whose rows a derived property of it is worked out over. "" when nothing limits them. */
export function limitedNote(type) {
  const parts = [
    ...(type.rows_limited ? [t("types.limited.own", { rows: type.rows, count: type.rows })] : []),
    ...(type.limited_reads ?? []).map((d) => t("types.limited.read", { name: d.name, types: joinList(d.types.map((x) => t("types.limited.type", { name: x.name, rows: x.rows, count: x.rows }))) })),
  ];
  return parts.length ? t("types.limited.note", { parts: parts.join(t("types.semi")) }) : "";
}

/** Why a derived value is empty for someone a row rule limits: what it is worked out from lies outside the rows they may read (it is not 0). */
export const outsideNote = () => t("types.outside");

/** A code cell on the objects tab: the value, and next to it what it means when that is confirmed, else why it is not shown as meaning. */
export function codeCell(value, enumState) {
  if (value == null) return { value: "", note: "" };
  const label = enumState?.labels?.[value];
  if (enumState?.state === "confirmed" && label) return { value, note: label };
  if (enumState?.state === "needs_look") return { value, note: t("types.cell.needsLook") };
  return { value, note: t("types.cell.unconfirmed") };
}

/** What a column of the dataset may be declared as, the first being what it is now. */
export const TYPE_CHOICES = {
  integer: ["integer", "decimal", "text"], decimal: ["decimal", "text"], text: ["text"], date: ["date", "datetime", "text"],
  month: ["month", "text"], datetime: ["datetime", "text"], boolean: ["boolean", "text"],
};

/** A key column the service would refuse, and why, before anything is sent; "" when it is fine. */
export function keyProblem(column) {
  if (column.type === "decimal") return t("types.form.decimalKey", { name: column.name });
  if (column.type === "boolean") return t("types.form.booleanKey", { name: column.name });
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

/** The number on each tab of a type page: properties and objects are the type's own; derived, views and actions come from what uses it (0 when nothing does). Before that is read, only the type's own. */
export function tabCounts(type, uses, live = {}) {   // `live`: a tab's own list, once read, is the one source of its number
  const own = { props: type.properties?.length ?? 0, objects: type.rows ?? 0 };
  if (!uses) return { ...own, ...live };
  const of = (kind) => uses.used_by.find((u) => u.kind === kind)?.count ?? 0;
  return { ...own, derived: of("derived"), views: of("views"), actions: of("actions"), ...live };
}

/** The tabs a type page shows, in order: 行为 only to a builder, and only when the type has actions (or the person opened that tab by its address). */
export const typeTabs = (counts, tab, mayBuild) => TYPE_TABS.filter((k) => k !== "actions" || (mayBuild && ((counts?.actions ?? 0) > 0 || tab === "actions")));

/** Whether a builder sees "+ 行为" after the tabs: the type has no actions yet (so the 行为 tab is hidden) and the count is known. The tab opens to make the first one. */
export const offerFirstAction = (counts, tab, mayBuild) => mayBuild && tab !== "actions" && counts?.actions === 0;

/** What uses a type, as one line: "Views 1 · Actions 3 · Relations 4"; "" when nothing uses the type. */
export const usesSummary = (uses) => (uses?.used_by ?? []).map((u) => `${u.label} ${u.count}`).join(" · ");

/** The grey line under a type's title: where it comes from and how many objects it has. `uploaded` ("3 days ago, Ann") is added when known. */
export function typeSub(type, uploaded = "") {
  const from = t("types.sub.from", { dataset: type.dataset, version: type.dataset_version }) + (uploaded ? t("types.sub.uploaded", { when: uploaded }) : " · ");
  return `${from}${t(type.rows_limited ? "types.sub.limited" : "types.sub.objects", { count: type.rows })}`;
}

/** The head of a code column's meanings: how many values, how many have a meaning written. */
export function meaningsSummary(meanings) {
  const values = meanings.values ?? [];
  if (!values.length) return t("types.meanings.none");
  return t("types.meanings.summary", { values: values.length, written: values.filter((v) => (v.label ?? "").trim()).length });
}

/** An English name for an object type from its Chinese name: known words joined by underscores (售后工单 → after_sales_ticket), a name already in letters tidied up, and "" when a word is not known. */
export function suggestEnglish(name) {
  let rest = String(name ?? "").trim().replace(/\u8868$/, "");
  if (!rest) return "";
  if (/^[\x20-\x7e]+$/.test(rest)) return rest.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const out = [];
  while (rest) {
    const word = WORD_LIST.find((w) => rest.startsWith(w));
    if (!word) return "";
    out.push(WORDS[word]);
    rest = rest.slice(word.length);
  }
  return out.join("_");
}
