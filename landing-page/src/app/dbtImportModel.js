// The words and decisions of the dbt import dialog, as plain functions of what the service answers (POST /api/workspace/types/dbt-import).
// The service reads the manifest, runs the checks and decides; the page only says it.
import { t } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";

/** The service's limit (dbt_import.MAX_MANIFEST_BYTES): a bigger file is not sent at all. */
export const MANIFEST_LIMIT_MB = 20;

const sep = () => t("types.sep");
const stateWord = (state) => t(`types.state.${state}`);

/** "" when the chosen file may be sent, else why not. */
export function fileProblem(file) {
  if (!file || file.size <= MANIFEST_LIMIT_MB * 1024 * 1024) return "";
  return t("types.dbt.tooLarge", { size: Math.ceil(file.size / 1024 / 1024), limit: MANIFEST_LIMIT_MB });
}

/** One object type: the key and that it was checked on every row, or that it is already there and left alone. */
export function typeLine(ty) {
  if (ty.status === "already_there") return t("types.dbt.already", { name: ty.id, state: stateWord(ty.state) });
  return t("types.dbt.typeLine", { name: ty.id, dataset: ty.dataset, key: ty.key.join(" + "), rows: ty.key_rows ?? "?", properties: ty.properties.join(sep()) });
}

/** One relation: its two ends and how many rows connect on the data now (the counts this person may read). */
export function relationLine(rel) {
  if (rel.status === "already_there") return t("types.dbt.already", { name: rel.id, state: stateWord(rel.state) });
  const n = rel.numbers;
  const parts = [t("types.dbt.connect", { matched: n.matched, rows: n.rows })];
  if (n.unmatched) parts.push(t("types.dbt.nowhere", { count: n.unmatched, to: rel.to }));
  if (n.empty) parts.push(t("types.dbt.empty", { count: n.empty }));
  if (rel.cardinality_holds === false) parts.push(t("types.dbt.fanOut"));
  return t("types.dbt.relationLine", { from: `${rel.from}.${rel.from_column}`, to: `${rel.to}.${rel.to_column}`, cardinality: t("types.dbt.manyToOne"), counts: parts.join(t("types.semi")) });
}

/** One accepted_values column: the values dbt allows, which still need someone to say what they mean. */
export function codeLine(code) {
  const head = t("types.dbt.codeLine", { column: `${code.type}.${code.column}`, values: code.values.join(sep()) });
  return code.code_column ? head : `${head} ${code.note ?? ""}`.trim();
}

/** {fresh, already, canApply, headline}: how many new proposals and how many already there; Apply is offered on a preview with something new. */
export function importSummary(result) {
  const all = [...result.types, ...result.relations];
  const fresh = all.filter((x) => x.status === "new").length;
  const already = all.length - fresh;
  const types = result.types.filter((x) => x.status === "new").length;
  const relations = fresh - types;
  const what = [types && t("types.dbt.types", { count: types }), relations && t("types.dbt.relations", { count: relations })].filter(Boolean).join(t("types.dbt.and"));
  const headline = !fresh ? t("types.dbt.nothingNew", { count: already })
    : result.applied ? t("types.dbt.proposed", { what }) : t("types.dbt.wouldPropose", { what });
  return { fresh, already, canApply: !result.applied && fresh > 0, headline };
}

/** The dialog's lists, the empty ones left out: [{id, title, items: [{text, href?}], more?}]. */
export function importSections(result) {
  const sections = [
    { id: "types", items: result.types.map((ty) => ({ text: typeLine(ty), href: hrefFor({ page: "type", id: ty.id, tab: "props" }) })) },
    { id: "relations", items: result.relations.map((rel) => ({ text: relationLine(rel), href: hrefFor({ page: "relation", id: rel.id }) })) },
    { id: "codes", items: result.codes.map((c) => ({ text: codeLine(c) })) },
    { id: "unmatched", items: result.unmatched_models.map((m) => ({ text: m })) },
    { id: "skipped", items: result.skipped.map((s) => ({ text: s.model ? `${s.model}${t("types.comma")}${s.what}${t("types.colon")} ${s.reason}` : `${s.what}${t("types.colon")} ${s.reason}` })),
      more: result.skipped_more ? t("types.dbt.more", { count: result.skipped_more }) : undefined },
    { id: "leftOut", items: result.left_out.map((s) => ({ text: `${s.what}${t("types.colon")} ${s.reason}` })) },
  ];
  return sections.filter((s) => s.items.length).map((s) => ({ ...s, title: t(`types.dbt.section.${s.id}`) }));
}
