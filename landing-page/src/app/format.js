import { t } from "./i18n/index.js";
import { sourceOrigin } from "./sourceModel.js";

const TYPES = ["integer", "decimal", "text", "date", "month", "datetime", "boolean"];

export const typeLabel = (type) => (TYPES.includes(type) ? t(`data.type.${type}`) : type);
export const isNumeric = (type) => type === "integer" || type === "decimal";

/** 1 -> 100%; anything short of full never rounds up to 100%. */
export function percentText(rate) {
  if (rate == null) return "—";
  return rate >= 1 ? "100%" : `${Math.floor(rate * 1000) / 10}%`;
}

/** Where a dataset came from, in words: an upload, or (anything else) a modelling run. */
export const originText = (origin) => {
  const source = sourceOrigin(origin);
  return origin === "upload" ? t("data.origin.upload") : source ? t("data.origin.sourceTable", { source: source.source, table: source.table }) : t("data.origin.modeling");
};

/** An ISO time as the local "2026-11-13 14:05". */
export function timeText(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** What the stored counts and the recorded checks say about a column as a key. */
export function keyText(column) {
  const check = column.key_check;
  if (check) {
    const parts = [check.violations ? t("data.key.dup", { count: check.violations }) : "", check.null_key_rows ? t("data.key.blank", { count: check.null_key_rows }) : ""].filter(Boolean);
    if (check.status === "passed") return t("data.key.unique");
    const failed = t("data.key.failed", { parts: parts.join(t("data.sep")) || t("data.key.noResult") });
    return column.near_key ? `${failed}${t("data.semi")}${nearKeyText(column.near_key)}` : failed;   // which values repeat, beside the check
  }
  if (column.possible_key) return t("data.key.unique");
  return column.near_key ? nearKeyText(column.near_key) : "—";
}

/** A column that is almost a key: which values repeat (the worst few) and how many rows are blank. */
export function nearKeyText(near) {
  const shown = near.samples.map((s) => t("data.key.sample", { value: s.value, count: s.rows })).join(t("data.semi"));
  const repeated = near.repeated_values ? t("data.key.repeated", { count: near.repeated_values, shown, more: near.repeated_values > near.samples.length ? t("data.key.more") : "" }) : "";
  return [repeated, near.missing ? t("data.key.blank", { count: near.missing }) : ""].filter(Boolean).join(t("data.sep"));
}
