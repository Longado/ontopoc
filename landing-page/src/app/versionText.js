// The Versions tab: each version's mode and counts in words, and the updates that wrote no version, in time order with them.
import { t } from "./i18n/index.js";

const MODES = ["new", "update_by_key", "overwrite", "upload"];

export const modeLabel = (mode) => t(`data.mode.${MODES.includes(mode) ? mode : "upload"}`);

/** How a version was made: by the old screen's modelling run (it never moves the current version) or the way it was uploaded. */
export const versionWay = (v) =>
  v.action ? t("data.way.action", { id: v.action.id, by: v.action.submitted_by, approver: v.action.approved_by }) : v.origin && v.origin !== "upload" ? t("data.origin.modeling") : modeLabel(v.mode);

const sameAs = (v) => (v.same_as ? t("data.sameAs", { n: v.same_as }) : "");

/** What a version changed, as the row of the version list says it. */
export function versionChangeText(v) {
  if (v.mode === "update_by_key") return `${t("data.change.update", { changed: v.changed, added: v.added, unchanged: v.unchanged })}${v.blank_kept ? t("data.change.blankKept", { count: v.blank_kept }) : ""}`;
  if (v.mode === "overwrite" && v.replaced_rows != null) return `${t("data.change.replaced", { before: v.replaced_rows, count: v.rows })}${sameAs(v)}`;
  return `${t("data.n.rows", { count: v.rows })}${sameAs(v)}`;
}

/** The keys of the rows an update changed or added: the ones kept, and "and more" when there are more than were kept. */
export const keyListText = (keys, total) => keys.join(t("data.listSep")) + (total > keys.length ? t("data.keysMore", { total }) : "");

/** An update that matched every row and changed none: one plain sentence. */
export const noChangeText = (u) =>
  u.mode === "overwrite"
    ? t("data.noChange.overwrite")
    : `${t("data.noChange.update", { keys: (u.key_columns ?? []).join(t("data.listSep")) })}${u.blank_kept ? t("data.noChange.blank", { count: u.blank_kept }) : ""}`;

/** Versions and skipped updates as one list, newest first; an update skipped in the same second as a version comes first. */
export function timeline(versions, skipped) {
  const rows = [
    ...versions.map((v) => ({ type: "version", at: v.at, ...v })),
    ...skipped.map((u) => ({ type: "no_change", ...u })),
  ];
  const rank = (r) => (r.type === "no_change" ? 1 : 0);
  return rows.sort((a, b) => (a.at === b.at ? rank(b) - rank(a) || (b.version ?? 0) - (a.version ?? 0) : a.at < b.at ? 1 : -1));
}
