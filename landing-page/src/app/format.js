const TYPE_LABEL = { integer: "整数", decimal: "小数", text: "文本", date: "日期", month: "月份", datetime: "日期时间", boolean: "是否" };

export const typeLabel = (type) => TYPE_LABEL[type] ?? type;
export const isNumeric = (type) => type === "integer" || type === "decimal";

/** 1 -> 100%; anything short of full never rounds up to 100%. */
export function percentText(rate) {
  if (rate == null) return "—";
  return rate >= 1 ? "100%" : `${Math.floor(rate * 1000) / 10}%`;
}

/** Where a dataset came from, in words: an upload, or (anything else) a modelling run. */
export const originText = (origin) => (origin === "upload" ? "上传" : "建模运行");

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
    const parts = [check.violations ? `重复 ${check.violations} 行` : "", check.null_key_rows ? `空 ${check.null_key_rows} 行` : ""].filter(Boolean);
    return check.status === "passed" ? "唯一，没有空值" : `主键检查没通过：${parts.join("，") || "没有结果"}`;
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
