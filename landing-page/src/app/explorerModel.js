// The explorer and the charts, as plain functions of what the service sends, so the words, the arithmetic of the drawings and the grey rule can be tested without a browser.

export const OPS = { eq: "等于", ne: "不等于", contains: "包含", gt: "大于", ge: "不小于", lt: "小于", le: "不大于", empty: "为空", filled: "有值" };
export const CHART_KINDS = [["number", "数字"], ["bar", "柱状图"], ["pie", "饼图"], ["histogram", "直方图"], ["table", "统计表"]];
const NUMERIC_ONLY = ["sum", "avg", "median", "p25", "p75"];

/** The ways a filter on this field may compare: size only where the service can put the values in order (numbers, years-months, dates). */
export const opsFor = (field) => [...["eq", "ne", "contains", "empty", "filled"], ...(field?.ordered ? ["gt", "ge", "lt", "le"] : [])];

export const emptyFilter = (fields) => ({ field: fields[0]?.key ?? "", op: "eq", value: "" });

/** The filters that say something: a comparison with no value is left out until it has one. */
export const readyFilters = (filters) =>
  filters.filter((f) => f.field && (f.op === "empty" || f.op === "filled" || String(f.value).trim() !== "")).map((f) => ({ field: f.field, op: f.op, value: f.op === "empty" || f.op === "filled" ? "" : String(f.value) }));

/** The query the service reads. `pivot` is {relation, side, source} or null. */
export const queryOf = ({ type, view = "", filters = [], pivot = null }) => ({ type, view: view || null, filters: readyFilters(filters), rows: null, pivot });

/** The aggregations a measure may have: a number any; anything else only counting and the extremes. No measure: counting rows. */
export function fnOptions(measure, aggregations) {
  if (!measure) return ["count"];
  return Object.keys(aggregations).filter((fn) => measure.numeric || !NUMERIC_ONLY.includes(fn));
}

/** What is still missing before a chart of this kind can be asked for, in words; "" when nothing is. */
export function chartMissing({ kind, group, measure, fn }) {
  if ((kind === "bar" || kind === "pie") && !group) return "选按哪一列分组";
  if ((kind === "histogram" || kind === "table") && !measure) return "选一个数字列来量";
  if (fn !== "count" && !measure && kind !== "histogram" && kind !== "table") return "选要统计的列";
  return "";
}

export const chartSpec = ({ kind, group, measure, fn, bins }) => ({ kind, group: group || null, measure: measure || null, fn: fn || "count", bins: bins ?? 10 });

/** 1234.5 -> "1,234.5"; at most two decimals; nothing -> "—". */
export function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** The line under a result that is not in colour: why, from the definition at the bottom of the chain. "" when it is. */
export const greyText = (standing) => (standing?.confirmed ? "" : standing?.why ?? "用到的定义现在不是已确认的状态");

// bars, one row for each group: the width is the share of the biggest value
export function barRows(groups) {
  const biggest = Math.max(0, ...groups.map((g) => Math.abs(Number(g.value) || 0)));
  return groups.map((g) => ({ label: g.label, value: Number(g.value) || 0, rows: g.rows, fraction: biggest ? Math.abs(Number(g.value) || 0) / biggest : 0 }));
}

export const histogramBars = (bins) => {
  const biggest = Math.max(0, ...bins.map((b) => b.count));
  return bins.map((b) => ({ ...b, fraction: biggest ? b.count / biggest : 0 }));
};

// one hue in five steps, so a pie reads from one accent without a rainbow; grey is the same five steps without the hue
const BLUES = ["#1757dc", "#4a7be3", "#7d9fea", "#a9bff0", "#d3def8"];
const GREYS = ["#6b6b66", "#8c8c86", "#aaaaa4", "#c6c6c1", "#dcdcd5"];
export const sliceColor = (i, grey) => (grey ? GREYS : BLUES)[i % BLUES.length];

/** Pie slices from the groups: the share, and the SVG path of each wedge of a circle of radius r centred at (r, r). A single slice is the whole circle. */
export function pieSlices(groups, r = 80) {
  const values = groups.map((g) => Math.max(0, Number(g.value) || 0));
  const total = values.reduce((a, b) => a + b, 0);
  let start = -Math.PI / 2;
  return groups.map((g, i) => {
    const share = total ? values[i] / total : 0;
    const end = start + share * 2 * Math.PI;
    const point = (angle) => `${(r + r * Math.cos(angle)).toFixed(2)} ${(r + r * Math.sin(angle)).toFixed(2)}`;
    let path = "";
    if (share >= 0.9999) path = `M ${r} 0 A ${r} ${r} 0 1 1 ${r} ${2 * r} A ${r} ${r} 0 1 1 ${r} 0 Z`;
    else if (share > 0) path = `M ${r} ${r} L ${point(start)} A ${r} ${r} 0 ${share > 0.5 ? 1 : 0} 1 ${point(end)} Z`;
    start = end;
    return { label: g.label, value: values[i], share, path };
  });
}

/** The query that opens the linked set of another type: the objects of `relation.other` that the rows `source` selects link to. */
export const pivotQuery = (source, relation) => ({ type: relation.other, view: null, filters: [], rows: null, pivot: { relation: relation.id, side: relation.side, source } });

/** What the pivot of a query says in words: 经过 订单属于客户，从 订单 的 N 个筛选条件。 */
export function pivotText(query, relationName, sourceName) {
  const n = query.pivot?.source?.filters?.length ?? 0;
  return `与「${sourceName}」${n ? `（${n} 个条件）` : ""}关联，经过 ${relationName}`;
}

/** The query kept in an address (the explorer opens from a link with its pivot already set) and read back; anything unreadable is no query. */
export const queryToParam = (query) => JSON.stringify(query);
export function queryFromParam(text) {
  if (!text) return null;
  try {
    const q = JSON.parse(text);
    return q && typeof q === "object" && typeof q.type === "string" ? q : null;
  } catch {
    return null;
  }
}
