// What the pipeline pages decide without a browser: the graph's layout, the card texts, how a draft definition is changed (always into a new object), the operator
// picker's filtering, the simple expression form, what a confirm screen counts as seen. The service's own words are shown as they come.

export const KIND_LABEL = { input: "输入", join: "关联", transform: "转换", llm: "AI 判断", union: "合并", split: "拆分", output: "输出" };
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
const PREFIX = { input: "in", join: "j", transform: "t", llm: "ai", union: "u", split: "s", output: "out" };

const STATE_WORD = { proposed: "已提出", checked: "已检查", confirmed: "已确认", needs_look: "需再看", rejected: "已退回" };
/** The state chip of a pipeline or of one of its outputs: a pipeline that needs another look says why (数据变了 / 定义改了). */
export const pipelineStateText = (item) => (item.state === "needs_look" && item.cause_word ? `需再看：${item.cause_word}` : STATE_WORD[item.state] ?? "");

export const numberText =(value) => (typeof value === "number" ? value.toLocaleString("en-US") : value == null ? "—" : String(value));
export const rowsText = (n) => `${numberText(n)} 行`;

/** The ids a step reads (a branch id stands for the split that makes it). */
export const inputsOf = (step) => (step.type === "join" ? [step.left, step.right] : step.type === "union" ? [...(step.inputs ?? [])] : step.type === "input" ? [] : [step.from]).filter(Boolean);

/** {branch id: the id of the split that makes it}. */
export const branchOwners = (steps) => Object.fromEntries(steps.filter((s) => s.type === "split").flatMap((s) => (s.branches ?? []).map((b) => [b.id, s.id])));

/** The steps a step reads, as steps: a branch is its split. */
const readsOf = (step, owners) => [...new Set(inputsOf(step).map((i) => owners[i] ?? i))];

/** What a step can read, in order: every step but a split and an output, and each branch of a split, with the words of a picker. */
export const readableSteps = (steps) => steps.flatMap((s) => (s.type === "split" ? (s.branches ?? []).map((b) => ({ id: b.id, label: `拆分的分支：${b.id}` }))
  : s.type === "output" ? [] : [{ id: s.id, label: `${KIND_LABEL[s.type]}：${stepTitle(s, steps)}` }]));

/** Where each card goes, left to right: a step stands one column right of the furthest step it reads; the order of the steps decides the order in a column. */
export function layout(steps, size = { w: 208, h: 116, gx: 56, gy: 16 }) {
  const column = {};
  const owners = branchOwners(steps);
  for (const s of steps) column[s.id] = Math.max(-1, ...readsOf(s, owners).map((i) => column[i] ?? -1)) + 1;
  const used = {};
  const nodes = {};
  for (const s of steps) {
    const row = used[column[s.id]] ?? 0;
    used[column[s.id]] = row + 1;
    nodes[s.id] = { col: column[s.id], row, x: column[s.id] * (size.w + size.gx), y: row * (size.h + size.gy) };
  }
  const edges = steps.flatMap((s) => readsOf(s, owners).filter((i) => nodes[i]).map((from) => ({ from, to: s.id })));
  const cols = Math.max(0, ...Object.values(column)) + 1;
  const rows = Math.max(1, ...Object.values(used));
  return { nodes, edges, size, width: steps.length ? cols * size.w + (cols - 1) * size.gx : 0, height: rows * size.h + (rows - 1) * size.gy };
}

/** The steps that feed no output, when there is an output at all: they are drawn and marked "不会运行". */
export function orphans(steps) {
  if (!steps.some((s) => s.type === "output")) return [];
  const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
  const owners = branchOwners(steps);
  const live = new Set();
  const walk = (id) => {
    if (live.has(id) || !byId[id]) return;
    live.add(id);
    readsOf(byId[id], owners).forEach(walk);
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
  if (step.type === "input") return `${step.dataset || step.view || "（还没选）"}${step.version ? ` 第 ${step.version} 版` : ""}`;
  if (step.type === "output") return step.name || "（还没写名字）";
  if (step.type === "join") return `${nameOf(step.left, steps)} 和 ${nameOf(step.right, steps)}`;
  if (step.type === "union") return (step.inputs ?? []).map((i) => (branchOwners(steps)[i] ? i : nameOf(i, steps))).join("、") || "（还没选）";
  if (step.type === "split") return (step.branches ?? []).map((b) => b.id).join(" / ") || "（还没有分支）";
  if (step.type === "llm") return step.name || "（还没写新列的名字）";
  const n = step.operators?.length ?? 0;
  return n ? step.operators.map(operatorName).join("、") : "（还没有操作）";
}

export const OP_NAME = { filter: "数据过滤", fill_null: "空值替换", text_clean: "文本清理", cast: "字段转换", calc: "计算列", aggregate: "分组统计", dedupe: "排重", label: "打标签" };
export const operatorName = (op) => OP_NAME[op.op] ?? op.op;

/** The conditions of a filter, flattened in the order the form shows them. */
const conditionsOf = (node) => (node?.all || node?.any ? (node.all ?? node.any).flatMap(conditionsOf) : node ? [node] : []);
const VALUE_CMPS = new Set(["eq", "ne", "gt", "lt", "ge", "le"]);

/** A message from the engine ("步骤 t1 的第 1 个操作（filter）：没有列「」") said as a person says it: an operator by its name ("数据过滤：条件 1 没选列"; "分组统计（第 2 个操作）：…" when the step has
 * several), any other step by its kind and title, no empty quotes. An id that is not among `steps` is left as it is. */
export function friendlyError(message, steps) {
  let lastOp = null;
  const said = String(message ?? "").replace(/步骤 ([^\s：，、（）。]+?)(?: 的第 (\d+) 个操作（(\w+)）)?(?=[：，、。 ）]|$)/g, (whole, id, n, op) => {
    const step = steps.find((s) => s.id === id);
    if (!step) return whole;
    const operator = n ? step.operators?.[Number(n) - 1] : null;
    if (operator) {
      lastOp = operator;
      return `${OP_NAME[op] ?? op}${step.operators.length > 1 ? `（第 ${n} 个操作）` : ""}`;
    }
    const head = `${KIND_LABEL[step.type]}「${stepTitle(step, steps.filter((s) => s !== step))}」`;
    return n ? `${head}的第 ${n} 个操作（${OP_NAME[op] ?? op}）` : head;
  });
  const empty = lastOp?.op === "filter" ? conditionsOf(lastOp.where).findIndex((c) => !c.column) + 1 || 1 : 0;
  return said
    .replace(/没有列「」|(?<=：)没选列$/, empty ? `条件 ${empty} 没选列` : "没选列")
    .replace(/数据集「」(?:不存在|没有)?/, "数据集还没选")
    .replace(/没有(\S{0,4}?)「」/, "没选$1")
    .replace(/里没有列\s*$/, "里没选列")
    .replace(/「」/g, "");
}

/** Whether a step is set up so that it can run: what is still missing, in words ("数据过滤：条件 1 没选列"). A step that has none of these may still fail when the service checks it. */
export function stepIssues(step) {
  if (step.type === "input") return step.dataset || step.view ? [] : ["还没选数据集"];
  if (step.type === "join") {
    return [...(step.left ? [] : ["左边还没选"]), ...(step.right ? [] : ["右边还没选"]), ...((step.on ?? []).some((p) => !p.left || !p.right) ? ["关联的列没选齐"] : [])];
  }
  if (step.type === "output") return String(step.name ?? "").trim() ? [] : ["还没写数据集的名字"];
  if (step.type === "union") return (step.inputs ?? []).length < 2 ? ["合并至少要选两步"] : [];
  if (step.type !== "transform") return [];
  if (!step.operators?.length) return ["还没有操作"];
  return step.operators.flatMap((op) => {
    const who = operatorName(op);
    if (op.op === "filter") {
      return conditionsOf(op.where).flatMap((c, i) => {
        if (!c.column) return [`${who}：条件 ${i + 1} 没选列`];
        const open = VALUE_CMPS.has(c.cmp) ? c.value == null || c.value === "" && !("meaning" in c || "meanings" in c)
          : c.cmp === "in" ? !(c.values ?? []).length && !("meaning" in c || "meanings" in c) : c.cmp === "between" ? c.low == null || c.low === "" || c.high == null || c.high === "" : false;
        return open ? [`${who}：条件 ${i + 1} 未填`] : [];
      });
    }
    if (op.op === "calc") return [...(op.name ? [] : [`${who}：还没写新列的名字`]), ...(op.expression ? [] : [`${who}：还没写表达式`])];
    if (["cast", "label"].includes(op.op)) return op.column ? [] : [`${who}：还没选列`];
    if (["fill_null", "text_clean"].includes(op.op)) return op.columns?.length ? [] : [`${who}：还没选列`];
    return [];
  });
}

/** {step id: what is missing} for the steps that are not set up yet. */
export function allIssues(steps) {
  return Object.fromEntries(steps.map((s) => [s.id, stepIssues(s)]).filter(([, list]) => list.length));
}

const KEY_LIKE = /(号|编号|编码|代码|键|id|key)$/i;
/** The columns a join can put in as its key: the columns of the same name and type on both sides. `best` is the one most likely the key (a name that ends like one, the first in the left
 * input); `others` are the other key-like ones, which would make the key longer. A same-name column that does not look like a key (a status, an amount) is not offered. */
export function suggestJoinKeys(left = [], right = []) {
  const there = new Map(right.map((c) => [c.name, c]));
  const same = left.filter((c) => KEY_LIKE.test(c.name) && there.has(c.name) && (!c.type || !there.get(c.name).type || c.type === there.get(c.name).type)).map((c) => ({ left: c.name, right: c.name }));
  return { best: same[0] ?? null, others: same.slice(1) };
}

/** Why the run button is grey ("" when it is not). */
export function runBlockReason({ dirty, hasOutput, todo = 0, running = false }) {
  if (running) return "正在运行";
  if (dirty) return "有改动还没保存，先保存";
  if (!hasOutput) return "要有一个输出步骤才能运行";
  if (todo > 0) return `还有 ${todo} 处没配好，先配好`;
  return "";
}

/** How many rows a step added or dropped, for its card ("" for an input, which has nothing before it). */
export function rowChangeText(node) {
  if (!node || node.type === "input" || !node.rows_in?.length || node.rows_out == null) return "";
  const delta = node.rows_out - node.rows_in[0];
  return delta === 0 ? "行数不变" : `${delta > 0 ? "+" : "\u2212"}${numberText(Math.abs(delta))} 行`;
}

/** What a run left on each card: {step id: {rows, warn}}. */
export function runResults(run) {
  return Object.fromEntries((run?.nodes ?? []).map((n) => [n.id, { rows: n.rows_out, warn: Object.keys(n.failures ?? {}).length > 0 }]));
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
export function newStep(steps, kind, near, datasets = [], model = "") {
  const id = unusedId(steps, kind);
  const picked = near ?? steps[steps.length - 1]?.id ?? null;
  const split = steps.find((s) => s.id === picked && s.type === "split");
  const branches = (split?.branches ?? []).map((b) => b.id);
  const last = split ? branches[0] ?? null : picked;   // a split is read through its branches
  if (kind === "input") return { id, type: "input", dataset: "" };   // empty: the person picks the data; the first dataset in the list is not a guess worth making
  if (kind === "join") {
    const right = [...steps].reverse().find((s) => s.id !== picked && s.type === "input") ?? [...steps].reverse().find((s) => s.id !== picked && s.type !== "split" && s.type !== "output");
    return { id, type: "join", left: last, right: right?.id ?? null, how: "left", on: [{ left: "", right: "" }], null_keys: "no_match" };
  }
  if (kind === "transform") return { id, type: "transform", from: last, operators: [] };
  if (kind === "union") {
    if (split) return { id, type: "union", inputs: branches, missing: "error" };
    const other = [...steps].reverse().find((s) => s.id !== last && s.type !== "output" && s.type !== "split");
    return { id, type: "union", inputs: [last, other?.id].filter(Boolean), missing: "error" };
  }
  if (kind === "split") return { id, type: "split", from: last, branches: [{ id: `${id}_甲`, where: { all: [{ column: "", cmp: "eq", value: "" }] } }, { id: `${id}_其余`, rest: true }] };
  if (kind === "llm") return { id, type: "llm", from: near ? last : [...steps].reverse().find((s) => s.type !== "output" && s.type !== "split")?.id ?? last, model, name: "", template: "classify", context: "", column: "", categories: ["其他"], multiple: false };
  return { id, type: "output", from: last, name: "" };
}

/** New steps go in front of the first output so that it can read them: a step can only read what is above it. An output is added last. */
const withSteps = (spec, added) => {
  const at = added.some((s) => s.type === "output") ? -1 : spec.steps.findIndex((s) => s.type === "output");
  return { ...spec, steps: at < 0 ? [...spec.steps, ...added] : [...spec.steps.slice(0, at), ...added, ...spec.steps.slice(at)] };
};
export const addStep = (spec, step) => withSteps(spec, [step]);
export const updateStep = (spec, id, patch) => ({ ...spec, steps: spec.steps.map((s) => (s.id === id ? { ...s, ...patch } : s)) });

/** Removes a step; refused (spec unchanged, `blocked` the ids that read it) while another step reads it. */
export function removeStep(spec, id) {
  const owners = branchOwners(spec.steps);
  const blocked = spec.steps.filter((s) => s.id !== id && readsOf(s, owners).includes(id)).map((s) => s.id);
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

const AGG_SUFFIX = { sum: "合计", count: "计数", count_distinct: "去重数", avg: "平均", min: "最小值", max: "最大值", median: "中位数", p25: "P25", p75: "P75" };
/** The name a statistic gets when the person has not typed one: the column and what was done to it (金额合计); counting whole rows is 行数. */
export const aggAutoName = (a) => (a.column ? `${a.column}${AGG_SUFFIX[a.fn] ?? AGG_LABEL[a.fn]}` : "行数");

/** A statistic after its function or column changed: its result name follows, unless the person typed their own (a name that is neither this one's old default nor the service's). */
export function retargetAgg(agg, change) {
  const next = { ...agg, ...change };
  if (!next.column) delete next.column;
  const auto = agg.as === undefined || agg.as === aggAutoName(agg) || agg.as === aggDefaultName(agg);
  if (auto) next.as = aggAutoName(next);
  return next;
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
  ai_failed: (n) => `${n} 行 AI 没答成`,
  ai_off_list: (n) => `${n} 行 AI 答的不在列表里`,
  ai_unanswered: (n) => `${n} 行 AI 答不出`,
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

/** The summary's nodes with one for each branch of a split, so that a step reading a branch sees its columns: the split's columns, the branch's rows. */
export function withBranchNodes(nodes, steps) {
  const out = { ...nodes };
  for (const s of steps.filter((x) => x.type === "split" && nodes[x.id])) {
    for (const b of s.branches ?? []) {
      const counted = nodes[s.id].split?.branches?.find((x) => x.id === b.id);
      out[b.id] = { id: b.id, type: "branch", column_types: nodes[s.id].column_types, columns: nodes[s.id].columns, rows_in: [nodes[s.id].rows_out], rows_out: counted?.rows };
    }
  }
  return out;
}

/** A branch renamed, and every step that reads it reading the new name. */
export function renameBranch(spec, splitId, from, to) {
  const taken = new Set([...spec.steps.map((s) => s.id), ...spec.steps.flatMap((s) => (s.branches ?? []).map((b) => b.id))]);
  if (!from || !String(to ?? "").trim() || taken.has(to)) return spec;   // nothing, or a name that is already a step's or a branch's: left as it was
  const swap = (v) => (v === from ? to : v);
  return {
    ...spec,
    steps: spec.steps.map((s) => (s.id === splitId ? { ...s, branches: s.branches.map((b) => (b.id === from ? { ...b, id: to } : b)) }
      : { ...s, ...(s.left !== undefined ? { left: swap(s.left) } : {}), ...(s.right !== undefined ? { right: swap(s.right) } : {}), ...(s.from !== undefined ? { from: swap(s.from) } : {}),
        ...(Array.isArray(s.inputs) ? { inputs: s.inputs.map(swap) } : {}) })),
  };
}

/** A name for a new branch that no step or branch has. */
export function newBranchId(split, steps) {
  const taken = new Set([...steps.map((s) => s.id), ...steps.flatMap((s) => (s.branches ?? []).map((b) => b.id)), ...(split.branches ?? []).map((b) => b.id)]);
  let n = (split.branches ?? []).length + 1;
  while (taken.has(`${split.id}_${n}`)) n += 1;
  return `${split.id}_${n}`;
}

/** The steps that read a branch. */
export const branchReaders = (steps, id) => steps.filter((s) => [s.left, s.right, s.from, ...(s.inputs ?? [])].includes(id)).map((s) => s.id);

/** What a union did besides stacking rows: rows found in more than one input, and the rows a missing column was left empty on. */
export function unionLines(union) {
  if (!union) return [];
  const same = union.same_rows?.count ? [`${numberText(union.same_rows.count)} 行在不止一个输入里都有，后面求和会算两次`] : [];
  return [...same, ...Object.entries(union.filled_empty ?? {}).map(([col, n]) => `${col}：${numberText(n)} 行没有这一列，留空`)];
}

/** Where a split sent the rows: each branch with its rows, the rows whose condition field was empty, the rows that met it after an earlier branch took them, and the rows in no branch. */
export function splitLines(split) {
  if (!split) return [];
  const branch = (b) => {
    const notes = [b.empty_condition ? `${numberText(b.empty_condition)} 行条件字段是空的，没进这个分支` : "", b.also_matched ? `${numberText(b.also_matched)} 行也满足，但已经进了前面的分支` : ""].filter(Boolean);
    return `${b.id}：${rowsText(b.rows)}${notes.length ? `（${notes.join("；")}）` : ""}`;
  };
  return [...split.branches.map(branch), ...(split.unassigned ? [`${numberText(split.unassigned)} 行没进任何分支，不会往下走`] : [])];
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
  if (node.union?.same_rows?.count) out.push({ level: "warn", text: `${numberText(node.union.same_rows.count)} 行重复` });
  if (node.split?.unassigned) out.push({ level: "warn", text: `${numberText(node.split.unassigned)} 行没进任何分支` });
  const doubled = (node.operators ?? []).flatMap(doubledGroupLines);
  if (doubled.length) out.push({ level: "warn", text: `${(node.operators ?? []).reduce((n, o) => n + (o.double_counted ?? []).reduce((m, d) => Math.max(m, d.groups), 0), 0)} 组的合计重复计算了行` });
  if (node.llm?.pending > 0) out.push({ level: "note", text: `${numberText(node.llm.pending)} 行 AI 还没跑` });
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
  if (step.type === "llm") return [`读 ${nameOf(step.from, steps)}，让 AI 写「${step.name}」（${LLM_TEMPLATE[step.template ?? "empty"]}）`, `模型 ${step.model}`, ...llmSettingLines(step)];
  if (step.type === "union") return [`把 ${stepTitle(step, steps)} 的行接在一起，按列名对上`, step.missing === "empty" ? "缺的列留空" : "有一步缺列就不合并",
    ...(step.source_column ? [`加一列「${step.source_column}」标出每行来自哪一步`] : [])];
  if (step.type === "split") return [`读 ${nameOf(step.from, steps)}，每行进第一个满足条件的分支`,
    ...(step.branches ?? []).map((b) => `${b.id}：${b.rest ? "其余的行" : operatorTitle({ op: "filter", where: b.where })}`)];
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

// --- the AI node and the assistant ---

export const LLM_TEMPLATE = { classify: "分类", extract: "抽取", summary: "摘要", empty: "自己写提示" };
export const LLM_OUTPUT = { text: "一段文字", choice: "几个答案里选一个", number: "一个数" };
export const TRIAL_MODE = { sample: "随机样本", rows: "选几行", values: "自己填一个值" };

/** The lines a person reads of an AI step's settings, for the confirm screen. */
export function llmSettingLines(step) {
  const t = step.template ?? "empty";
  if (t === "classify") return [`按「${step.column || "（还没选）"}」分成：${(step.categories ?? []).join("、")}${step.multiple ? "（可以选几个）" : ""}`, ...(step.context ? [`背景：${step.context}`] : [])];
  if (t === "summary") return [`把「${step.column || "（还没选）"}」概括成不超过 ${step.size ?? "?"} ${step.unit ?? "字"}`];
  if (t === "extract") return [`从「${step.column || "（还没选）"}」抽取：${(step.fields ?? []).map((f) => `${f.name}（${f.type === "number" ? "数" : "文字"}）`).join("、")}`];
  return [`提示：${step.prompt || "（还没写）"}`, `答案：${LLM_OUTPUT[step.output ?? "text"]}${step.output === "choice" ? `（${(step.choices ?? []).join("、")}）` : ""}`];
}

/** What a run (or a read of what is kept) did, as a person says it: "30 行答了（18 行是以前记下的），2 行失败，3 行跳过". */
export function llmRunText(report) {
  if (!report) return "";
  const parts = [`${numberText(report.answered)} 行答了${report.from_cache ? `（${numberText(report.from_cache)} 行用的是以前记下的）` : ""}`];
  if (report.failed) parts.push(`${numberText(report.failed)} 行失败`);
  if (report.off_list) parts.push(`${numberText(report.off_list)} 行答的不在列表里`);
  if (report.unanswered) parts.push(`${numberText(report.unanswered)} 行答不出`);
  if (report.skipped) parts.push(`${numberText(report.skipped)} 行跳过（提示用到的列都是空的）`);
  if (report.pending) parts.push(`${numberText(report.pending)} 行还没跑`);
  return parts.join("，");
}

/** "答了 '质量问题'，不在列表里：3 行" for each off-list answer. */
export const offListLines = (report) => Object.entries(report?.off_list_answers ?? {}).map(([answer, n]) => `答了「${answer}」，不在列表里：${numberText(n)} 行`);

/** What a run would ask of the model before it starts: calls, characters in, cost when known. */
export function estimateText(estimate) {
  if (!estimate) return "";
  const money = estimate.cost == null ? "服务没有配单价，没有估价" : `约 ${estimate.cost} 元`;
  const cap = estimate.cap == null ? "" : `；一次运行最多 ${numberText(estimate.cap)} 次`;
  return `要调用 ${numberText(estimate.calls)} 次，约 ${numberText(estimate.chars_in)} 字发给模型；${money}${cap}`;
}

/** The whole run's calls against the most one run may make, over all its AI steps; null when the service does not say. */
export function runCalls(states) {
  const all = Object.values(states).map((d) => d.estimate);
  if (!all.length || all.some((e) => e.cap == null)) return null;
  const calls = all.reduce((sum, e) => sum + e.calls, 0);
  const cap = Math.min(...all.map((e) => e.cap));
  return { calls, cap, over: calls > cap };
}

/** "20 行里 17 行对上" and where the review stands against the line the step names. */
export function reviewText(review) {
  if (!review) return "";
  if (!review.reviewable) return "概括没有标准答案，不做样本审核";
  if (!review.labelled) return "还没有标注";
  if (review.matched == null) return `${review.labelled} 行有标注，还没有按现在的提示核对`;
  const count = `${review.total} 行里 ${review.matched} 行对上`;
  if (!review.current) return `${count}（那是改提示之前的结果，要重跑）`;
  if (review.min_match == null) return `${count}；还没定要对上几行才算通过`;
  if (review.need_labelled != null && review.labelled < review.need_labelled) return `${count}；至少要标注 ${review.need_labelled} 行才能通过，现在 ${review.labelled} 行`;
  return `${count}，${review.passed ? "达到" : "没达到"}要求的 ${review.need_match ?? review.min_match} 行`;
}

/** One labelled row for the person who confirms: what the row said, what was expected, what the step answered, and whether they match. */
export function labelledRow(row) {
  const answered = row.ai == null ? (row.status === "absent" ? "这一行不在现在的数据里" : "还没核对") : row.ai.map((v) => (v == null ? "空" : String(v))).join("；");
  const expected = row.expected !== null && typeof row.expected === "object" ? Object.values(row.expected).map((v) => (v == null ? "空" : String(v))).join("；") : String(row.expected);
  return { text: Object.values(row.fields).map((v) => (v == null || v === "" ? "空" : String(v))).join(" ｜ "), expected, answered, matched: row.matched === true, checked: row.matched != null, who: row.who ?? "—" };
}

/** The AI columns an output keeps and what holds each back from being a key or a code meaning, from the pipeline's AI nodes. */
export const aiNodeLine = (node) => `${node.name}：${reviewText(node.review)}；记下了 ${numberText(node.cache.current)} 条答案`;

/** A new draft after the assistant's steps were applied: they are ordinary steps from then on. */
export const applyDraft = (spec, steps) => withSteps(spec, steps.map((s) => s.step));

/** The recent sentences a person gave the assistant, newest first, one of each, at most `keep`. */
export function rememberPrompt(list, entry, keep = 8) {
  return [entry, ...list.filter((e) => e.text !== entry.text)].slice(0, keep);
}

/** The values a sample row shows in its columns: the fields of the prompt, in order, empty ones as "空". */
export const fieldCells = (fields, values) => fields.map((f) => (values[f] == null || values[f] === "" ? "空" : String(values[f])));

/** Puts a field into the prompt where the caret is, written `${名字}`: {text, caret}. */
export function insertField(text, start, end, name) {
  const insert = "${" + name + "}";
  const from = Math.min(start ?? text.length, end ?? text.length);
  const to = Math.max(start ?? text.length, end ?? text.length);
  return { text: text.slice(0, from) + insert + text.slice(to), caret: from + insert.length };
}
