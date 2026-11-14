// What the pipeline pages decide without a browser: the graph's layout, the card texts, how a draft definition is changed (always into a new object), the operator
// picker's filtering, the simple expression form, what a confirm screen counts as seen. The service's own words are shown as they come.

export const KIND_LABEL = { input: "输入", join: "关联", transform: "转换", output: "输出" };
export const HOW_LABEL = { left: "保留左边全部", inner: "只留两边都对上的", anti: "只留左边没对上的", semi: "只留左边对上的" };
export const NULL_KEYS_LABEL = { no_match: "空值不匹配", equal: "空值相等" };
export const STATUS_LABEL = { success: "成功", failed: "失败", running: "运行中", cancelled: "已取消" };
export const CHANGE_LABEL = { ADD: "新增", MOD: "改了", DEL: "删除" };
export const CMP_LABEL = { eq: "等于", ne: "不等于", gt: "大于", lt: "小于", ge: "大于等于", le: "小于等于", in: "属于", between: "介于", is_null: "为空", not_null: "不为空" };
export const AGG_LABEL = { sum: "求和", count: "计数", count_distinct: "去重计数", avg: "平均", min: "最小", max: "最大", median: "中位数", p25: "P25", p75: "P75" };
export const CAST_LABEL = { date: "日期", datetime: "日期时间", decimal: "小数", integer: "整数", boolean: "是否" };
export const CLEAN_LABEL = { trim: "去首尾空格", whitespace: "合并多余空白", upper: "转大写", lower: "转小写", replace: "替换文字" };
export const UNMAPPED_LABEL = { null: "留空", keep: "保留原代码", other: "写成指定文字" };
const CATEGORY_ORDER = ["常用", "清洗", "类型", "日期", "数值", "文本", "汇总"];
const PREFIX = { input: "in", join: "j", transform: "t", output: "out" };

const STATE_WORD = { proposed: "已提出", checked: "已检查", confirmed: "已确认", needs_look: "需再看", rejected: "已退回" };
/** The state chip of a pipeline or of one of its outputs: a pipeline that needs another look says why (数据变了 / 定义改了). */
export const pipelineStateText = (item) => (item.state === "needs_look" && item.cause_word ? `需再看：${item.cause_word}` : STATE_WORD[item.state] ?? "");

export const numberText =(value) => (typeof value === "number" ? value.toLocaleString("en-US") : value == null ? "—" : String(value));
export const rowsText = (n) => `${numberText(n)} 行`;

/** The ids of the steps a step reads. */
export const inputsOf = (step) => (step.type === "join" ? [step.left, step.right] : step.type === "input" ? [] : [step.from]).filter(Boolean);

/** Where each card goes, left to right: a step stands one column right of the furthest step it reads; the order of the steps decides the order in a column. */
export function layout(steps, size = { w: 208, h: 116, gx: 56, gy: 16 }) {
  const column = {};
  for (const s of steps) column[s.id] = Math.max(-1, ...inputsOf(s).map((i) => column[i] ?? -1)) + 1;
  const used = {};
  const nodes = {};
  for (const s of steps) {
    const row = used[column[s.id]] ?? 0;
    used[column[s.id]] = row + 1;
    nodes[s.id] = { col: column[s.id], row, x: column[s.id] * (size.w + size.gx), y: row * (size.h + size.gy) };
  }
  const edges = steps.flatMap((s) => inputsOf(s).filter((i) => nodes[i]).map((from) => ({ from, to: s.id })));
  const cols = Math.max(0, ...Object.values(column)) + 1;
  const rows = Math.max(1, ...Object.values(used));
  return { nodes, edges, size, width: steps.length ? cols * size.w + (cols - 1) * size.gx : 0, height: rows * size.h + (rows - 1) * size.gy };
}

/** The steps that feed no output, when there is an output at all: they are drawn and marked "不会运行". */
export function orphans(steps) {
  if (!steps.some((s) => s.type === "output")) return [];
  const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
  const live = new Set();
  const walk = (id) => {
    if (live.has(id) || !byId[id]) return;
    live.add(id);
    inputsOf(byId[id]).forEach(walk);
  };
  steps.filter((s) => s.type === "output").forEach((s) => walk(s.id));
  return steps.filter((s) => !live.has(s.id)).map((s) => s.id);
}

/** The card's top line: what kind of step, and for a join how it keeps rows. */
export const kindLine = (step) => (step.type === "join" ? `关联，${HOW_LABEL[step.how] ?? ""}` : KIND_LABEL[step.type]);

/** A step by its title, from its id (the id itself when it is not among `steps`). */
export function nameOf(id, steps) {
  const s = steps.find((x) => x.id === id);
  return s ? stepTitle(s, steps.filter((x) => x !== s)) : id ?? "?";
}

/** What a step is called: a dataset or output by its name, a join by the two steps it joins (`steps` lets it name them, else it uses their ids). */
export function stepTitle(step, steps = []) {
  if (step.type === "input") return `${step.dataset ?? step.view ?? "（还没选）"}${step.version ? ` 第 ${step.version} 版` : ""}`;
  if (step.type === "output") return step.name || "（还没写名字）";
  if (step.type === "join") return `${nameOf(step.left, steps)} 和 ${nameOf(step.right, steps)}`;
  const n = step.operators?.length ?? 0;
  return n ? step.operators.map(operatorName).join("、") : "（还没有操作）";
}

export const OP_NAME = { filter: "数据过滤", fill_null: "空值替换", text_clean: "文本清理", cast: "字段转换", calc: "计算列", aggregate: "分组统计", dedupe: "排重", label: "打标签" };
export const operatorName = (op) => OP_NAME[op.op] ?? op.op;

/** A message from the engine ("步骤 t1 的第 1 个操作（calc）：…") with the step id and the operator id said as a person says them ("转换「计算列」的第 1 个操作（计算列）：…"). An id that is not among `steps` is left as it is. */
export function friendlyError(message, steps) {
  return String(message ?? "").replace(/步骤 ([^\s：，、（）。]+?)(?: 的第 (\d+) 个操作（(\w+)）)?(?=[：，、。 ）]|$)/g, (whole, id, n, op) => {
    const step = steps.find((s) => s.id === id);
    if (!step) return whole;
    const head = `${KIND_LABEL[step.type]}「${stepTitle(step, steps.filter((s) => s !== step))}」`;
    return n ? `${head}的第 ${n} 个操作（${OP_NAME[op] ?? op}）` : head;
  });
}

/** The picker: the categories present (in the order people look for them), and the operators of the chosen one that match the search. */
export function catalogView(catalog, category, query) {
  const text = String(query ?? "").trim().toLowerCase();
  const present = [...new Set(catalog.map((c) => c.category))].sort((a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b));
  const matches = (c) => !text || `${c.name}${c.text}${c.op}`.toLowerCase().includes(text);
  return { categories: present, items: catalog.filter((c) => (!category || c.category === category) && matches(c)) };
}

// --- changing a draft: every function returns a new spec ---

const unusedId = (steps, kind) => {
  const taken = new Set(steps.map((s) => s.id));
  let n = 1;
  while (taken.has(`${PREFIX[kind]}${n}`)) n += 1;
  return `${PREFIX[kind]}${n}`;
};

/** A new step after the others. `near` is the step selected now: a join reads it and, as its right side, the nearest other step that reads data; a transform or an output reads it. */
export function newStep(steps, kind, near, datasets = []) {
  const id = unusedId(steps, kind);
  const last = near ?? steps[steps.length - 1]?.id ?? null;
  if (kind === "input") return { id, type: "input", dataset: datasets[0] ?? "" };
  if (kind === "join") {
    const right = [...steps].reverse().find((s) => s.id !== last && s.type === "input") ?? [...steps].reverse().find((s) => s.id !== last);
    return { id, type: "join", left: last, right: right?.id ?? null, how: "left", on: [{ left: "", right: "" }], null_keys: "no_match" };
  }
  if (kind === "transform") return { id, type: "transform", from: last, operators: [] };
  return { id, type: "output", from: last, name: "" };
}

export const addStep = (spec, step) => ({ ...spec, steps: [...spec.steps, step] });
export const updateStep = (spec, id, patch) => ({ ...spec, steps: spec.steps.map((s) => (s.id === id ? { ...s, ...patch } : s)) });

/** Removes a step; refused (spec unchanged, `blocked` the ids that read it) while another step reads it. */
export function removeStep(spec, id) {
  const blocked = spec.steps.filter((s) => inputsOf(s).includes(id)).map((s) => s.id);
  return blocked.length ? { spec, blocked } : { spec: { ...spec, steps: spec.steps.filter((s) => s.id !== id) }, blocked };
}

const withOperators = (spec, id, change) => updateStep(spec, id, { operators: change(spec.steps.find((s) => s.id === id).operators) });
export const addOperator = (spec, id, op) => withOperators(spec, id, (ops) => [...ops, op]);
export const setOperator = (spec, id, i, op) => withOperators(spec, id, (ops) => ops.map((o, k) => (k === i ? op : o)));
export const removeOperator = (spec, id, i) => withOperators(spec, id, (ops) => ops.filter((_, k) => k !== i));
export const copyOperator = (spec, id, i) => withOperators(spec, id, (ops) => [...ops.slice(0, i + 1), structuredClone(ops[i]), ...ops.slice(i + 1)]);
export function moveOperator(spec, id, i, by) {
  return withOperators(spec, id, (ops) => {
    const to = i + by;
    if (to < 0 || to >= ops.length) return ops;
    const next = [...ops];
    [next[i], next[to]] = [next[to], next[i]];
    return next;
  });
}

export const sameSpec = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export function newOperator(kind) {
  const starts = {
    filter: { where: { all: [{ column: "", cmp: "eq", value: "" }] } },
    fill_null: { columns: [], with: { constant: "" } },
    text_clean: { columns: [], steps: [{ do: "trim" }] },
    cast: { column: "", to: "decimal" },
    calc: { name: "", expression: "" },
    aggregate: { group_by: [], aggregations: [{ fn: "count", as: "行数" }] },
    dedupe: { keys: [], keep: "first", order_by: "" },
    label: { column: "", from_meaning: true, unmapped: "null" },
  };
  return { op: kind, ...structuredClone(starts[kind]) };
}

const list = (names) => (names?.length ? names.join("、") : "（还没选）");

/** One operator in a sentence, for its card. */
export function operatorTitle(op) {
  if (op.op === "filter") return `留下满足条件的行（${conditionCount(op.where)} 个条件）`;
  if (op.op === "fill_null") return `${list(op.columns)} 的空值换成${op.with?.column ? `「${op.with.column}」` : op.with?.expression ? `表达式 ${op.with.expression}` : ` ${op.with?.constant ?? ""}`}`;
  if (op.op === "text_clean") return `${list(op.columns)}：${(op.steps ?? []).map((s) => CLEAN_LABEL[s.do] ?? s.do).join("，")}`;
  if (op.op === "cast") return `「${op.column || "（还没选）"}」转成${CAST_LABEL[op.to] ?? op.to}${op.as && op.as !== op.column ? `，放进新列「${op.as}」` : ""}${op.thousands ? "（千分位）" : ""}`;
  if (op.op === "calc") return `${op.replace ? "替换" : "新增"}「${op.name || "（还没写名字）"}」= ${op.expression || "（还没写表达式）"}`;
  if (op.op === "aggregate") return `${op.group_by?.length ? `按 ${list(op.group_by)} 分组` : "全部合成一组"}：${(op.aggregations ?? []).map((a) => `${a.as ?? aggDefaultName(a)}`).join("、")}`;
  if (op.op === "dedupe") return op.keys?.length ? `按 ${list(op.keys)} 排重，留${op.keep === "last" ? "最后" : "第一"}条（按「${op.order_by || "（还没选）"}」）` : "整行一样的只留一行";
  if (op.op === "label") return `「${op.column || "（还没选）"}」的代码换成含义${op.from_meaning ? "（读已确认的含义）" : ""}`;
  return operatorName(op);
}

export const aggDefaultName = (a) => `${AGG_LABEL[a.fn]}${a.column ? `_${a.column}` : ""}`;
const conditionCount = (node) => (node?.all || node?.any ? (node.all ?? node.any).reduce((n, c) => n + conditionCount(c), 0) : 1);

// --- the expression editor ---

const BARE = /^[\p{L}_][\p{L}\p{M}\p{N}_]*$/u;   // the service's word: a letter (Chinese too) or underscore, then letters, digits, underscores
const KEYWORDS = new Set(["and", "or", "not", "true", "false", "null"]);
/** How a field is written inside an expression: as it is when that reads as one word, else in square brackets. */
export const fieldRef = (name) => (BARE.test(name) && !KEYWORDS.has(name.toLowerCase()) ? name : `[${name}]`);

/** The simple form (field, operator, field or number) as the expression it writes; empty until it is complete and the number is a number. */
export function simpleExpression({ left, op, right, rightIsField }) {
  if (!left || !op || right === "" || right == null) return "";
  if (!rightIsField && !/^-?\d+(\.\d+)?$/.test(String(right).trim())) return "";
  return `${fieldRef(left)} ${op} ${rightIsField ? fieldRef(right) : String(right).trim()}`;
}
export const SIMPLE_OPERATORS = ["+", "-", "*", "/", "=", "<>", ">", "<", ">=", "<="];

/** Puts `insert` in the text where the caret is (replacing what is selected): {text, caret}. */
export function insertAt(text, start, end, insert) {
  const from = Math.min(start ?? text.length, end ?? text.length);
  const to = Math.max(start ?? text.length, end ?? text.length);
  return { text: text.slice(0, from) + insert + text.slice(to), caret: from + insert.length };
}

// --- cards, flags, lines ---

/** "160 行 → 169 行": what went in and what came out; a join shows both inputs. */
export function countsText(node) {
  if (!node) return "";
  const into = node.rows_in.length > 1 ? node.rows_in.map(numberText).join(" + ") : numberText(node.rows_in[0]);
  return node.type === "input" ? `${rowsText(node.rows_out)}` : `${into} 行 → ${rowsText(node.rows_out)}`;
}

const FAILURE_TEXT = {
  cast_failures: (n) => `${n} 个值没转成功`,
  calc_errors: (n) => `${n} 行算不出结果`,
  unmapped_rows: (n) => `${n} 行的代码没有对应的含义`,
  dropped_by_empty_condition: (n) => `${n} 行因为条件的字段是空的被删掉`,
};
export const failureLine = (kind, n) => (FAILURE_TEXT[kind] ?? (() => `${kind} ${n}`))(n);
export const failureLines = (node) => Object.entries(node?.failures ?? {}).map(([kind, n]) => failureLine(kind, n));

/** "KH099：合计算成 52,620，每行只算一次是 49,470" for each group a statistic counted a source row more than once. */
export function doubledGroupLines(operator) {
  return (operator.double_counted ?? []).flatMap((d) => d.examples.map((e) => `${Object.values(e.group).join("、")}：${d.as ?? d.column}算成 ${numberText(e.with)}，每行只算一次是 ${numberText(e.true)}`));
}

/** What a join's fan-out did to the sums, in lines: which column, and the figure with and without the repeated rows. */
export function fanOutLines(join) {
  const side = (f, name) => (f?.double_counted ?? []).map((d) => `${name}「${d.column}」的合计从 ${numberText(d.without)} 变成 ${numberText(d.with)}`);
  return [...side(join?.fan_out, "左边"), ...side(join?.right_fan_out, "右边")];
}

/** What the card carries beside its counts: {level: "warn" | "bad", text}. */
export function cardFlags(node) {
  if (!node) return [];
  const out = [];
  if (node.type === "join" && node.join) {
    if (node.join.extra_rows > 0) out.push({ level: "warn", text: `多出 ${node.join.extra_rows} 行：右边同一个键有多条` });
    if (fanOutLines(node.join).length) out.push({ level: "warn", text: "合计会被重复计算" });
    if (node.join.left_unmatched > 0 && node.join.how !== "semi") out.push({ level: "note", text: `${node.join.left_unmatched} 行左边没有对上` });
  }
  const doubled = (node.operators ?? []).flatMap(doubledGroupLines);
  if (doubled.length) out.push({ level: "warn", text: `${(node.operators ?? []).reduce((n, o) => n + (o.double_counted ?? []).reduce((m, d) => Math.max(m, d.groups), 0), 0)} 组的合计重复计算了行` });
  const failures = failureLines(node);
  if (failures.length) out.push({ level: "warn", text: failures[0] + (failures.length > 1 ? ` 等 ${failures.length} 类` : "") });
  if (node.type === "output" && node.output) {
    if (node.output.status?.state === "error") out.push({ level: "bad", text: node.output.status.text });
    if (node.output.duplicate_keys) out.push({ level: "bad", text: `主键有 ${node.output.duplicate_keys.count} 个重复` });
    if (node.output.empty_keys) out.push({ level: "bad", text: `${node.output.empty_keys} 行主键是空的` });
  }
  return out;
}

/** What a join did, in lines a person can check against the data: matched and unmatched left rows, rows beyond the left input, the sums that repeat, keys that match after cleaning. */
export function joinVerdictLines(join) {
  if (!join) return [];
  const lines = [`左边 ${rowsText(join.left_rows)}，${numberText(join.matched_left)} 行对上了，${numberText(join.left_unmatched)} 行没有对上`];
  if (join.extra_rows > 0) {
    const repeated = join.fan_out?.repeated_keys;
    lines.push(`多出 ${numberText(join.extra_rows)} 行：${repeated ? `${numberText(repeated)} 个键在右边有不止一行` : "同一个键在右边有不止一行"}`);
    lines.push(...fanOutLines(join));
  }
  if (join.right_fan_out) lines.push(`左边有 ${numberText(join.right_fan_out.repeated_keys)} 个键不止一行，右边的合计也会重复：${fanOutLines({ right_fan_out: join.right_fan_out }).join("；")}`);
  if (join.left_blank || join.right_blank) lines.push(`键是空的：左边 ${numberText(join.left_blank)} 行，右边 ${numberText(join.right_blank)} 行（${NULL_KEYS_LABEL[join.null_keys] ?? ""}）`);
  for (const n of join.near_matches ?? []) lines.push(`「${n.left}」有 ${numberText(n.count)} 个值去掉空格或按数字读就能和「${n.right}」对上，例如 ${n.examples.slice(0, 3).join("、")}`);
  return lines;
}

/** The parameters each operator takes, for the picker's right-hand side. */
export const OPERATOR_PARAMS = {
  filter: ["条件：列、比较、值（代码列可以按含义选）", "条件之间是“全部满足”或“任一满足”"],
  fill_null: ["要换的列（可以几列）", "换成：一个常量、另一列、或表达式的结果", "空字符串是否也算空"],
  text_clean: ["要清理的文本列", "动作：去空格、合并空白、转大小写、替换文字（按原样的文字找）"],
  cast: ["列和目标类型", "日期格式、千分位", "转不了时记录继续，或停下"],
  calc: ["新列的名字，或替换哪一列", "表达式（可以先试算）"],
  aggregate: ["按哪几列分组（可以不分组）", "统计：求和、计数、去重计数、平均、最小、最大、中位数、P25、P75", "空值不计入；代码列不能求和"],
  dedupe: ["按哪几列排重（不选则整行一样才算重复）", "留第一条还是最后一条", "按哪一列排先后"],
  label: ["要换成含义的代码列", "读已确认的含义，或自己写对照表", "对不上的代码：留空、保留或写成指定文字"],
};

export const durationText =(ms) => (ms == null ? "" : ms < 1000 ? `${ms} 毫秒` : `${(ms / 1000).toFixed(1)} 秒`);
export const versionsText = (inputs) => Object.entries(inputs ?? {}).map(([k, v]) => `${k.replace(/^view:/, "视图 ")} 第 ${v} 版`).join("、");

// --- the confirm screen ---

/** One step in words, for the before / after of a change. */
export function stepSummary(step, steps = []) {
  if (!step) return [];
  if (step.type === "input") return [`读 ${stepTitle(step)}`];
  if (step.type === "join") return [`${HOW_LABEL[step.how] ?? step.how}：${nameOf(step.left, steps)} 和 ${nameOf(step.right, steps)}`,`按 ${(step.on ?? []).map((p) => `${p.left} = ${p.right}`).join("，")}，${NULL_KEYS_LABEL[step.null_keys ?? "no_match"]}`,
    ...(step.right_columns ? [`右边只带 ${list(step.right_columns)}`] : [])];
  if (step.type === "transform") return [`读 ${nameOf(step.from, steps)}`, ...(step.operators ?? []).map(operatorTitle)];
  return [`读 ${nameOf(step.from, steps)}，写到「${step.name}」`, ...(step.key ? [`主键 ${list(step.key.columns)}`] : []), ...(step.columns ? [`只留 ${list(step.columns)}`] : [])];
}

/** Marks made for one definition version only: a definition that was edited has none. */
export const markedIds = (marks, version) => (marks?.version === version ? marks.ids : []);
export function toggleMark(marks, version, id) {
  const ids = markedIds(marks, version);
  return { version, ids: ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id] };
}
export const progressOf = (changes, marks, version) => {
  const seen = markedIds(marks, version);
  return { seen: changes.filter((c) => seen.includes(c.id)).length, total: changes.length };
};

/** A column's statistics before and after, side by side: [{name, before, after, changed}], where each side is the text of rows empty, distinct values, smallest, largest. */
export function statRows(before, after) {
  const text = (c) => (c ? `空 ${numberText(c.nulls)}，${numberText(c.distinct)} 种，${c.min ?? "—"} ~ ${c.max ?? "—"}` : "—");
  const names = [...new Set([...(after ?? []).map((c) => c.name), ...(before ?? []).map((c) => c.name)])];
  return names.map((name) => {
    const b = (before ?? []).find((c) => c.name === name);
    const a = (after ?? []).find((c) => c.name === name);
    return { name, before: text(b), after: text(a), changed: text(b) !== text(a) };
  });
}
