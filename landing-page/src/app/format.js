import { formatDateTime } from "./i18n/index.js";
import { sourceOrigin } from "./sourceModel.js";

const TYPE_LABEL = { integer: "整数", decimal: "小数", text: "文本", date: "日期", month: "月份", datetime: "日期时间", boolean: "是否" };

export const typeLabel = (type) => TYPE_LABEL[type] ?? type;
export const isNumeric = (type) => type === "integer" || type === "decimal";

/** 1 -> 100%; anything short of full never rounds up to 100%. */
export function percentText(rate) {
  if (rate == null) return "—";
  return rate >= 1 ? "100%" : `${Math.floor(rate * 1000) / 10}%`;
}

/** Where a dataset came from, in words: an upload, or (anything else) a modelling run. */
export const originText = (origin) => {
  const source = sourceOrigin(origin);
  return origin === "upload" ? "上传" : source ? `数据源“${source.source}”的表 ${source.table}` : "建模运行";
};

/** An ISO time as the person reads it ("Nov 13, 2026, 2:05 PM" in English; the locale's own form in Chinese), through the i18n formatter; "" when it is not a time. */
export const timeText = (iso) => formatDateTime(iso);

/** What the stored counts and the recorded checks say about a column as a key. */
export function keyText(column) {
  const check = column.key_check;
  if (check) {
    const parts = [check.violations ? `重复 ${check.violations} 行` : "", check.null_key_rows ? `空 ${check.null_key_rows} 行` : ""].filter(Boolean);
    if (check.status === "passed") return "唯一，没有空值";
    const failed = `主键检查没通过：${parts.join("，") || "没有结果"}`;
    return column.near_key ? `${failed}；${nearKeyText(column.near_key)}` : failed;   // which values repeat, beside the check
  }
  if (column.possible_key) return "唯一，没有空值";
  return column.near_key ? nearKeyText(column.near_key) : "—";
}

/** A column that is almost a key: which values repeat (the worst few) and how many rows are blank. */
export function nearKeyText(near) {
  const shown = near.samples.map((s) => `${s.value}，${s.rows} 行`).join("；");
  const repeated = near.repeated_values ? `重复 ${near.repeated_values} 个值（${shown}${near.repeated_values > near.samples.length ? " 等" : ""}）` : "";
  return [repeated, near.missing ? `空 ${near.missing} 行` : ""].filter(Boolean).join("，");
}
