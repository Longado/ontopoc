// What the pipeline pages decide without a browser: the graph's layout, the card texts, how a draft definition is changed (always into a new object), the operator
// picker's filtering, the simple expression form, what a confirm screen counts as seen. The service's own words are shown as they come.

import { t } from "./i18n/index.js";
import { AGG_SERVER, CATEGORY_ORDER, KEY_LIKE, SERVER_PATTERNS, UNIT_CHARS, UNIT_SENTENCES } from "./pipelineServerText.js";

/** An object whose values are read from the dictionary when they are used, so that a language change shows at once: LABELS.kind.join -> t("pipeline.m.kind.join"). */
const labels = (prefix, keys) => Object.defineProperties({}, Object.fromEntries(keys.map((k) => [k, { enumerable: true, get: () => t(`pipeline.m.${prefix}.${k}`) }])));
export const KIND_LABEL = labels("kind", ["input", "join", "transform", "llm", "union", "split", "output", "branch"]);
export const HOW_LABEL = labels("how", ["left", "inner", "anti", "semi"]);
export const NULL_KEYS_LABEL = labels("nullkeys", ["no_match", "equal"]);
export const STATUS_LABEL = labels("status", ["success", "failed", "running", "cancelled"]);
export const CHANGE_LABEL = labels("change", ["ADD", "MOD", "DEL"]);
export const CMP_LABEL = labels("cmp", ["eq", "ne", "gt", "lt", "ge", "le", "in", "between", "is_null", "not_null"]);
export const AGG_LABEL = labels("agg", ["sum", "count", "count_distinct", "avg", "min", "max", "median", "p25", "p75"]);
export const CAST_LABEL = labels("cast", ["date", "datetime", "decimal", "integer", "boolean"]);
export const CLEAN_LABEL = labels("clean", ["trim", "whitespace", "upper", "lower", "replace"]);
export const UNMAPPED_LABEL = labels("unmapped", ["null", "keep", "other"]);
const PREFIX = { input: "in", join: "j", transform: "t", llm: "ai", union: "u", split: "s", output: "out" };

const STATE_WORDS = ["proposed", "checked", "confirmed", "needs_look", "rejected"];
/** The state chip of a pipeline or of one of its outputs: a pipeline that needs another look says why (the service's own words: data changed / definition changed). */
export const pipelineStateText = (item) => (item.state === "needs_look" && item.cause_word ? t("pipeline.m.state.needs_look_why", { cause: item.cause_word }) : STATE_WORDS.includes(item.state) ? t(`pipeline.m.state.${item.state}`) : "");

export const numberText =(value) => (typeof value === "number" ? value.toLocaleString("en-US") : value == null ? "—" : String(value));
export const rowsText = (n, shown = numberText(n)) => t("pipeline.m.rows", { count: typeof n === "number" ? n : 2, n: shown });

/** The ids a step reads (a branch id stands for the split that makes it). */
export const inputsOf = (step) => (step.type === "join" ? [step.left, step.right] : step.type === "union" ? [...(step.inputs ?? [])] : step.type === "input" ? [] : [step.from]).filter(Boolean);

/** {branch id: the id of the split that makes it}. */
export const branchOwners = (steps) => Object.fromEntries(steps.filter((s) => s.type === "split").flatMap((s) => (s.branches ?? []).map((b) => [b.id, s.id])));

/** The steps a step reads, as steps: a branch is its split. */
const readsOf = (step, owners) => [...new Set(inputsOf(step).map((i) => owners[i] ?? i))];

/** What a step can read, in order: every step but a split and an output, and each branch of a split, with the words of a picker. */
export const readableSteps = (steps) => steps.flatMap((s) => (s.type === "split" ? (s.branches ?? []).map((b) => ({ id: b.id, label: t("pipeline.m.readable.branch", { id: b.id }) }))
  : s.type === "output" ? [] : [{ id: s.id, label: t("pipeline.m.readable.step", { kind: KIND_LABEL[s.type], title: stepTitle(s, steps) }) }]));

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

/** A drag position on the 8px grid. */
export const snap = (v, grid = 8) => Math.round(v / grid) * grid;

/** The layout with the cards the reader dragged at their own places (`moved` is {step id: {x, y}} in layout coordinates, which may be negative;
 * ids of removed steps are ignored). Everything shifts by `shift` so the top-left card sits at 0, and the picture grows to hold every card.
 * With nothing moved it is the layout itself. */
export function placed(lay, moved) {
  const ids = Object.keys(moved ?? {}).filter((id) => lay.nodes[id]);
  if (!ids.length) return lay;
  const raw = { ...lay.nodes };
  for (const id of ids) raw[id] = { ...raw[id], x: moved[id].x, y: moved[id].y };
  const all = Object.values(raw);
  const shift = { x: Math.max(0, -Math.min(...all.map((n) => n.x))), y: Math.max(0, -Math.min(...all.map((n) => n.y))) };
  const nodes = Object.fromEntries(Object.entries(raw).map(([id, n]) => [id, { ...n, x: n.x + shift.x, y: n.y + shift.y }]));
  const shifted = Object.values(nodes);
  return { ...lay, nodes, shift, width: Math.max(...shifted.map((n) => n.x)) + lay.size.w, height: Math.max(...shifted.map((n) => n.y)) + lay.size.h };
}

/** A link drawn from `from`'s out-port to `to`'s in-port (`slot` "left" | "right" for a join), as {id, patch} for `to`, or {error} with the reason's key:
 * input (an input reads a dataset), output (an output has no out-port), self, same (already linked), loop (`from` already reads `to`), branchless (a split with no branch). */
export function linkSteps(steps, from, to, slot = "left") {
  const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
  const src = byId[from];
  const dst = byId[to];
  if (!src || !dst) return { error: "missing" };
  if (src.type === "output") return { error: "output" };
  if (dst.type === "input") return { error: "input" };
  if (from === to) return { error: "self" };
  const owners = branchOwners(steps);
  const reads = readsOf(dst, owners);
  if (reads.includes(from) && dst.type !== "join") return { error: "same" };
  if (dst.type === "join" && (owners[dst[slot]] ?? dst[slot]) === from) return { error: "same" };
  const upstream = new Set();
  const walk = (id) => {
    if (upstream.has(id) || !byId[id]) return;
    upstream.add(id);
    readsOf(byId[id], owners).forEach(walk);
  };
  walk(from);
  if (upstream.has(to)) return { error: "loop" };
  let id = from;
  if (src.type === "split") {
    const branches = (src.branches ?? []).map((b) => b.id);
    if (!branches.length) return { error: "branchless" };
    const read = new Set(steps.flatMap(inputsOf));
    id = branches.find((b) => !read.has(b)) ?? branches[0];
  }
  if (dst.type === "join") return { id: to, patch: { [slot === "right" ? "right" : "left"]: id } };
  if (dst.type === "union") return { id: to, patch: { inputs: [...(dst.inputs ?? []), id] } };
  return { id: to, patch: { from: id } };
}

/** The steps with every step after all the steps it reads (the engine reads only steps written before), otherwise in their own order; the same list when nothing moves. */
export function inReadingOrder(steps) {
  const owners = branchOwners(steps);
  const known = new Set(steps.map((s) => s.id));
  const done = new Set();
  const out = [];
  let rest = steps;
  while (rest.length) {
    const ready = rest.filter((s) => readsOf(s, owners).every((i) => done.has(i) || !known.has(i) || i === s.id));
    const take = ready.length ? [ready[0]] : [rest[0]];   // a loop (never made by a link) keeps its order
    take.forEach((s) => { done.add(s.id); out.push(s); });
    rest = rest.filter((s) => !done.has(s.id));
  }
  return out.every((s, i) => s === steps[i]) ? steps : out;
}

/** The edge from `from` (a step; a split stands for its branches) to `to` taken away, as {id, patch} for `to`, or null when `to` does not read it. */
export function unlinkSteps(steps, from, to) {
  const dst = steps.find((s) => s.id === to);
  if (!dst) return null;
  const owners = branchOwners(steps);
  const hit = (i) => i != null && (owners[i] ?? i) === from;
  if (dst.type === "union") return (dst.inputs ?? []).some(hit) ? { id: to, patch: { inputs: dst.inputs.filter((i) => !hit(i)) } } : null;
  if (dst.type === "join") {
    const patch = { ...(hit(dst.left) ? { left: null } : {}), ...(hit(dst.right) ? { right: null } : {}) };
    return Object.keys(patch).length ? { id: to, patch } : null;
  }
  return hit(dst.from) ? { id: to, patch: { from: null } } : null;
}

/** The steps that feed no output, when there is an output at all: they are drawn and marked "will not run". */
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
export const kindLine = (step) => (step.type === "join" ? t("pipeline.m.kind.join_how", { how: HOW_LABEL[step.how] ?? "" }) : KIND_LABEL[step.type]);

/** A step by its title, from its id (the id itself when it is not among `steps`). */
export function nameOf(id, steps) {
  const s = steps.find((x) => x.id === id);
  return s ? stepTitle(s, steps.filter((x) => x !== s)) : id ?? "?";
}

/** What a step is called: a dataset or output by its name, a join by the two steps it joins (`steps` lets it name them, else it uses their ids). */
export function stepTitle(step, steps = []) {
  if (step.type === "input") return `${step.dataset || step.view || t("pipeline.m.title.unset")}${step.version ? t("pipeline.m.title.version", { version: step.version }) : ""}`;
  if (step.type === "output") return step.name || t("pipeline.m.title.unnamed");
  if (step.type === "join") return t("pipeline.m.title.pair", { a: nameOf(step.left, steps), b: nameOf(step.right, steps) });
  if (step.type === "union") return (step.inputs ?? []).map((i) => (branchOwners(steps)[i] ? i : nameOf(i, steps))).join(t("pipeline.m.sep.list")) || t("pipeline.m.title.unset");
  if (step.type === "split") return (step.branches ?? []).map((b) => b.id).join(" / ") || t("pipeline.m.title.no_branches");
  if (step.type === "llm") return step.name || t("pipeline.m.title.no_column_name");
  const n = step.operators?.length ?? 0;
  return n ? step.operators.map(operatorName).join(t("pipeline.m.sep.list")) : t("pipeline.m.title.no_ops");
}

export const OP_NAME = labels("op", ["filter", "fill_null", "text_clean", "cast", "calc", "aggregate", "dedupe", "label", "extract"]);
export const operatorName = (op) => OP_NAME[op.op] ?? op.op;

/** The conditions of a filter, flattened in the order the form shows them. */
const conditionsOf = (node) => (node?.all || node?.any ? (node.all ?? node.any).flatMap(conditionsOf) : node ? [node] : []);
const VALUE_CMPS = new Set(["eq", "ne", "gt", "lt", "ge", "le"]);

/** A message from the engine (in its own words: "步骤 t1 的第 1 个操作（filter）：没有列「」") said as a person says it: an operator by its name ("Filter rows: condition 1 has no column";
 * "Group and aggregate (operation 2): ..." when the step has several), any other step by its kind and title, no empty quotes. An id that is not among `steps` is left as it is.
 * The patterns that read the service's text are in pipelineServerText.js. */
export function friendlyError(message, steps) {
  let lastOp = null;
  const said = String(message ?? "").replace(SERVER_PATTERNS.step, (whole, id, n, op) => {
    const step = steps.find((s) => s.id === id);
    if (!step) return whole;
    const operator = n ? step.operators?.[Number(n) - 1] : null;
    if (operator) {
      lastOp = operator;
      return step.operators.length > 1 ? t("pipeline.m.err.opnum", { name: OP_NAME[op] ?? op, n }) : OP_NAME[op] ?? op;
    }
    const head = t("pipeline.m.err.head", { kind: KIND_LABEL[step.type], title: stepTitle(step, steps.filter((s) => s !== step)) });
    return n ? t("pipeline.m.err.head_op", { head, n, op: OP_NAME[op] ?? op }) : head;
  });
  const empty = lastOp?.op === "filter" ? conditionsOf(lastOp.where).findIndex((c) => !c.column) + 1 || 1 : 0;
  const noColumn = empty ? t("pipeline.m.err.cond_no_column", { n: empty }) : t("pipeline.m.err.no_column");
  return said
    .replace(SERVER_PATTERNS.noColumn, noColumn)
    .replace(SERVER_PATTERNS.datasetEmpty, t("pipeline.m.err.dataset_unset"))
    .replace(SERVER_PATTERNS.noneChosen, (m, what) => t("pipeline.m.err.not_chosen", { what }))
    .replace(SERVER_PATTERNS.inNoColumn, t("pipeline.m.err.in_no_column"))
    .replace(SERVER_PATTERNS.emptyQuotes, "");
}

/** Whether a step is set up so that it can run: what is still missing, in words ("Filter rows: condition 1 needs a column"). A step that has none of these may still fail when the service checks it. */
export function stepIssues(step) {
  if (step.type === "input") return step.dataset || step.view ? [] : [t("pipeline.m.issue.input_dataset")];
  if (step.type === "join") {
    return [...(step.left ? [] : [t("pipeline.m.issue.join_left")]), ...(step.right ? [] : [t("pipeline.m.issue.join_right")]), ...((step.on ?? []).some((p) => !p.left || !p.right) ? [t("pipeline.m.issue.join_cols")] : [])];
  }
  if (step.type === "output") return String(step.name ?? "").trim() ? [] : [t("pipeline.m.issue.output_name")];
  if (step.type === "union") return (step.inputs ?? []).length < 2 ? [t("pipeline.m.issue.union_two")] : [];
  if (step.type !== "transform") return [];
  if (!step.operators?.length) return [t("pipeline.m.issue.no_ops")];
  return step.operators.flatMap((op) => {
    const who = operatorName(op);
    if (op.op === "filter") {
      return conditionsOf(op.where).flatMap((c, i) => {
        if (!c.column) return [t("pipeline.m.issue.cond_col", { who, n: i + 1 })];
        const open = VALUE_CMPS.has(c.cmp) ? c.value == null || c.value === "" && !("meaning" in c || "meanings" in c)
          : c.cmp === "in" ? !(c.values ?? []).length && !("meaning" in c || "meanings" in c) : c.cmp === "between" ? c.low == null || c.low === "" || c.high == null || c.high === "" : false;
        return open ? [t("pipeline.m.issue.cond_open", { who, n: i + 1 })] : [];
      });
    }
    if (op.op === "calc") return [...(op.name ? [] : [t("pipeline.m.issue.calc_name", { who })]), ...(op.expression ? [] : [t("pipeline.m.issue.calc_expr", { who })])];
    if (["cast", "label"].includes(op.op)) return op.column ? [] : [t("pipeline.m.issue.pick_col", { who })];
    if (["fill_null", "text_clean"].includes(op.op)) return op.columns?.length ? [] : [t("pipeline.m.issue.pick_col", { who })];
    if (op.op === "extract") {
      return [...(op.column ? [] : [t("pipeline.m.issue.pick_col", { who })]), ...(op.separator ? [] : [t("pipeline.m.issue.separator", { who })]), ...(op.as ? [] : [t("pipeline.m.issue.calc_name", { who })])];
    }
    return [];
  });
}

/** {step id: what is missing} for the steps that are not set up yet. */
export function allIssues(steps) {
  return Object.fromEntries(steps.map((s) => [s.id, stepIssues(s)]).filter(([, list]) => list.length));
}

/** The columns a join can put in as its key: the columns of the same name and type on both sides. `best` is the one most likely the key (a name that ends like one, the first in the left
 * input); `others` are the other key-like ones, which would make the key longer. A same-name column that does not look like a key (a status, an amount) is not offered. */
export function suggestJoinKeys(left = [], right = []) {
  const there = new Map(right.map((c) => [c.name, c]));
  const same = left.filter((c) => KEY_LIKE.test(c.name) && there.has(c.name) && (!c.type || !there.get(c.name).type || c.type === there.get(c.name).type)).map((c) => ({ left: c.name, right: c.name }));
  return { best: same[0] ?? null, others: same.slice(1) };
}

/** Why the run button is grey ("" when it is not). */
export function runBlockReason({ dirty, hasOutput, todo = 0, running = false }) {
  if (running) return t("pipeline.m.block.running");
  if (dirty) return t("pipeline.m.block.dirty");
  if (!hasOutput) return t("pipeline.m.block.no_output");
  if (todo > 0) return t("pipeline.m.block.todo", { count: todo });
  return "";
}

/** How many rows a step added or dropped, for its card ("" for an input, which has nothing before it). */
export function rowChangeText(node) {
  if (!node || node.type === "input" || !node.rows_in?.length || node.rows_out == null) return "";
  const delta = node.rows_out - node.rows_in[0];
  return delta === 0 ? t("pipeline.m.delta.same") : t("pipeline.m.delta.rows", { count: Math.abs(delta), sign: delta > 0 ? "+" : "\u2212", n: numberText(Math.abs(delta)) });
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
  if (kind === "split") return { id, type: "split", from: last, branches: [{ id: `${id}_${t("pipeline.m.default.branch_a")}`, where: { all: [{ column: "", cmp: "eq", value: "" }] } }, { id: `${id}_${t("pipeline.m.default.branch_rest")}`, rest: true }] };
  if (kind === "llm") return { id, type: "llm", from: near ? last : [...steps].reverse().find((s) => s.type !== "output" && s.type !== "split")?.id ?? last, model, name: "", template: "classify", context: "", column: "", categories: [t("pipeline.m.default.other")], multiple: false };
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
    aggregate: { group_by: [], aggregations: [{ fn: "count", as: t("pipeline.m.default.agg_rows") }] },
    dedupe: { keys: [], keep: "first", order_by: "" },
    label: { column: "", from_meaning: true, unmapped: "null" },
    extract: { column: "", separator: "", part: 1, as: "" },
  };
  return { op: kind, ...structuredClone(starts[kind]) };
}

const list = (names) => (names?.length ? names.join(t("pipeline.m.sep.list")) : t("pipeline.m.title.unset"));

/** One operator in a sentence, for its card. */
export function operatorTitle(op) {
  const unset = t("pipeline.m.title.unset");
  if (op.op === "filter") return t("pipeline.m.op.filter_title", { count: conditionCount(op.where) });
  if (op.op === "fill_null") {
    const value = op.with?.column ? t("pipeline.m.op.fill_column", { column: op.with.column }) : op.with?.expression ? t("pipeline.m.op.fill_expr", { expression: op.with.expression }) : t("pipeline.m.op.fill_const", { constant: op.with?.constant ?? "" });
    return t("pipeline.m.op.fill_title", { cols: list(op.columns), value });
  }
  if (op.op === "text_clean") return t("pipeline.m.op.clean_title", { cols: list(op.columns), steps: (op.steps ?? []).map((s) => CLEAN_LABEL[s.do] ?? s.do).join(t("pipeline.m.sep.comma")) });
  if (op.op === "cast") return `${t("pipeline.m.op.cast_title", { column: op.column || unset, to: CAST_LABEL[op.to] ?? op.to })}${op.as && op.as !== op.column ? t("pipeline.m.op.cast_as", { as: op.as }) : ""}${op.thousands ? t("pipeline.m.op.cast_thousands") : ""}`;
  if (op.op === "calc") return t("pipeline.m.op.calc_title", { verb: op.replace ? t("pipeline.m.op.calc_replace") : t("pipeline.m.op.calc_add"), name: op.name || t("pipeline.m.op.calc_no_name"), expr: op.expression || t("pipeline.m.op.calc_no_expr") });
  if (op.op === "aggregate") return t("pipeline.m.op.agg_title", { group: op.group_by?.length ? t("pipeline.m.op.agg_group", { cols: list(op.group_by) }) : t("pipeline.m.op.agg_all"), aggs: (op.aggregations ?? []).map((a) => `${a.as ?? aggDefaultName(a)}`).join(t("pipeline.m.sep.list")) });
  if (op.op === "dedupe") return op.keys?.length ? t("pipeline.m.op.dedupe_title", { keys: list(op.keys), which: op.keep === "last" ? t("pipeline.m.op.dedupe_last") : t("pipeline.m.op.dedupe_first"), order: op.order_by || unset }) : t("pipeline.m.op.dedupe_all");
  if (op.op === "label") return t("pipeline.m.op.label_title", { column: op.column || unset, meaning: op.from_meaning ? t("pipeline.m.op.label_meaning") : "" });
  if (op.op === "extract") return t(op.part === "last" ? "pipeline.m.op.extract_title_last" : "pipeline.m.op.extract_title", { column: op.column || unset, separator: op.separator ?? "", part: op.part, as: op.as || unset });
  return operatorName(op);
}

/** What the service would refuse in an extract, said before it is sent: a separator longer than 10 characters, a part that is not 1 to 100 or the last. A separator
 * not written yet is for stepIssues. The separator is taken as written: a space is a separator, and nothing in it is read as a pattern. */
export function extractProblems(op) {
  const sep = op.separator ?? "";
  return [
    ...(sep.length > 10 ? [t("pipeline.m.extract.separator_length")] : []),
    ...(op.part === "last" || (Number.isInteger(op.part) && op.part >= 1 && op.part <= 100) ? [] : [t("pipeline.m.extract.part_range")]),
  ];
}

/** Where a column a person sees came from, for the columns table: the stored column, the column a part was extracted from, or the statistic that made it. */
export function columnFrom(c) {
  if (c.origin != null) return c.origin;
  if (c.extracted) {
    const { column, origin, separator, part } = c.extracted;
    return t(part === "last" ? "pipeline.m.from.extracted_last" : "pipeline.m.from.extracted", { source: origin ?? column, separator, part });
  }
  return c.aggregation ? `${c.aggregation.fn} (${c.aggregation.column ?? t("pipeline.panel.wholeRow")})` : "";
}

const AGG_SUFFIXES = ["sum", "count", "count_distinct", "avg", "min", "max", "median", "p25", "p75"];
/** The name a statistic gets when the person has not typed one: the column and what was done to it (amount_sum); counting whole rows is row_count. */
export const aggAutoName = (a) => (a.column ? t("pipeline.m.agg.auto", { column: a.column, suffix: AGG_SUFFIXES.includes(a.fn) ? t(`pipeline.m.aggsuffix.${a.fn}`) : AGG_LABEL[a.fn] }) : t("pipeline.m.default.agg_rows"));

/** A statistic after its function or column changed: its result name follows, unless the person typed their own (a name that is neither this one's old default nor the service's). */
export function retargetAgg(agg, change) {
  const next = { ...agg, ...change };
  if (!next.column) delete next.column;
  const auto = agg.as === undefined || agg.as === aggAutoName(agg) || agg.as === aggDefaultName(agg);
  if (auto) next.as = aggAutoName(next);
  return next;
}
export const aggDefaultName = (a) => `${AGG_SERVER[a.fn]}${a.column ? `_${a.column}` : ""}`;   // the service names a statistic itself, in its own words
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

/** "160 rows → 169 rows": what went in and what came out; a join shows both inputs. */
export function countsText(node) {
  if (!node) return "";
  const into = node.rows_in.length > 1 ? node.rows_in.map(numberText).join(" + ") : numberText(node.rows_in[0]);
  return node.type === "input" ? `${rowsText(node.rows_out)}` : `${rowsText(node.rows_in.length > 1 ? 2 : node.rows_in[0], into)} → ${rowsText(node.rows_out)}`;
}

const FAILURE_KINDS = ["cast_failures", "calc_errors", "unmapped_rows", "dropped_by_empty_condition", "ai_failed", "ai_off_list", "ai_unanswered"];
export const failureLine = (kind, n) => (FAILURE_KINDS.includes(kind) ? t(`pipeline.m.fail.${kind}`, { count: n }) : `${kind} ${n}`);
export const failureLines = (node) => Object.entries(node?.failures ?? {}).map(([kind, n]) => failureLine(kind, n));

/** "KH099: total came to 52,620; counting each row once gives 49,470" for each group a statistic counted a source row more than once. */
export function doubledGroupLines(operator) {
  return (operator.double_counted ?? []).flatMap((d) => d.examples.map((e) => t("pipeline.m.doubled.line", { group: Object.values(e.group).join(t("pipeline.m.sep.list")), name: d.as ?? d.column, with: numberText(e.with), true: numberText(e.true) })));
}

/** What a join's fan-out did to the sums, in lines: which column, and the figure with and without the repeated rows. */
export function fanOutLines(join) {
  const side = (f, name) => (f?.double_counted ?? []).map((d) => t("pipeline.m.fanout.line", { side: name, column: d.column, without: numberText(d.without), with: numberText(d.with) }));
  return [...side(join?.fan_out, t("pipeline.m.side.left")), ...side(join?.right_fan_out, t("pipeline.m.side.right"))];
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
  const same = union.same_rows?.count ? [t("pipeline.m.union.same", { count: union.same_rows.count, n: numberText(union.same_rows.count) })] : [];
  return [...same, ...Object.entries(union.filled_empty ?? {}).map(([col, n]) => t("pipeline.m.union.filled", { col, count: n, n: numberText(n) }))];
}

/** Where a split sent the rows: each branch with its rows, the rows whose condition field was empty, the rows that met it after an earlier branch took them, and the rows in no branch. */
export function splitLines(split) {
  if (!split) return [];
  const branch = (b) => {
    const notes = [b.empty_condition ? t("pipeline.m.split.empty_cond", { count: b.empty_condition, n: numberText(b.empty_condition) }) : "", b.also_matched ? t("pipeline.m.split.also", { count: b.also_matched, n: numberText(b.also_matched) }) : ""].filter(Boolean);
    const base = t("pipeline.m.split.branch", { id: b.id, rows: rowsText(b.rows) });
    return notes.length ? t("pipeline.m.split.notes", { base, notes: notes.join(t("pipeline.m.sep.semi")) }) : base;
  };
  return [...split.branches.map(branch), ...(split.unassigned ? [t("pipeline.m.split.unassigned", { count: split.unassigned, n: numberText(split.unassigned) })] : [])];
}

/** The counts as a card's footer has room for them: "160 + 30 → 160 rows" (an input: "160 rows"). */
export function countsShort(node) {
  if (!node) return "";
  if (node.type === "input" || !node.rows_in?.length) return rowsText(node.rows_out);
  const into = node.rows_in.length > 1 ? node.rows_in.map(numberText).join(" + ") : numberText(node.rows_in[0]);
  return t("pipeline.m.counts", { count: typeof node.rows_out === "number" ? node.rows_out : 2, from: into, n: numberText(node.rows_out) });
}

/** What the card carries beside its counts: {level: "warn" | "bad", text}. */
export function cardFlags(node) {
  if (!node) return [];
  const out = [];
  if (node.type === "join" && node.join) {
    if (node.join.extra_rows > 0) out.push({ level: "warn", text: t("pipeline.m.flag.extra", { count: node.join.extra_rows }) });
    if (fanOutLines(node.join).length) out.push({ level: "warn", text: t("pipeline.m.flag.double") });
    if (node.join.left_unmatched > 0 && node.join.how !== "semi") out.push({ level: "note", text: t("pipeline.m.flag.unmatched", { count: node.join.left_unmatched }) });
  }
  if (node.union?.same_rows?.count) out.push({ level: "warn", text: t("pipeline.m.flag.dupes", { count: node.union.same_rows.count }) });
  if (node.split?.unassigned) out.push({ level: "warn", text: t("pipeline.m.flag.no_branch", { count: node.split.unassigned }) });
  const doubled = (node.operators ?? []).flatMap(doubledGroupLines);
  if (doubled.length) out.push({ level: "warn", text: t("pipeline.m.flag.groups", { count: (node.operators ?? []).reduce((n, o) => n + (o.double_counted ?? []).reduce((m, d) => Math.max(m, d.groups), 0), 0) }) });
  if (node.llm?.pending > 0) out.push({ level: "note", text: t("pipeline.m.flag.ai_pending", { count: node.llm.pending }) });
  const failures = failureLines(node);
  if (failures.length) out.push({ level: "warn", text: failures.length > 1 ? t("pipeline.m.flag.more", { first: failures[0], total: failures.length, rest: failures.length - 1 }) : failures[0] });
  if (node.type === "output" && node.output) {
    if (node.output.status?.state === "error") out.push({ level: "bad", text: node.output.status.text });
    if (node.output.duplicate_keys) out.push({ level: "bad", text: t("pipeline.m.flag.dup_keys", { count: node.output.duplicate_keys.count }) });
    if (node.output.empty_keys) out.push({ level: "bad", text: t("pipeline.m.flag.empty_keys", { count: node.output.empty_keys }) });
  }
  return out;
}

/** What a join did, in lines a person can check against the data: matched and unmatched left rows, rows beyond the left input, the sums that repeat, keys that match after cleaning. */
export function joinVerdictLines(join) {
  if (!join) return [];
  const lines = [t("pipeline.m.verdict.left", { rows: rowsText(join.left_rows), matched: numberText(join.matched_left), unmatched: numberText(join.left_unmatched) })];
  if (join.extra_rows > 0) {
    const repeated = join.fan_out?.repeated_keys;
    lines.push(t("pipeline.m.verdict.extra", { n: numberText(join.extra_rows), why: repeated ? t("pipeline.m.verdict.extra_keys", { n: numberText(repeated) }) : t("pipeline.m.verdict.extra_key") }));
    lines.push(...fanOutLines(join));
  }
  if (join.right_fan_out) lines.push(t("pipeline.m.verdict.right_fan", { n: numberText(join.right_fan_out.repeated_keys), lines: fanOutLines({ right_fan_out: join.right_fan_out }).join(t("pipeline.m.sep.semi")) }));
  if (join.left_blank || join.right_blank) lines.push(t("pipeline.m.verdict.blank", { l: numberText(join.left_blank), r: numberText(join.right_blank), nk: NULL_KEYS_LABEL[join.null_keys] ?? "" }));
  for (const n of join.near_matches ?? []) lines.push(t("pipeline.m.verdict.near", { left: n.left, right: n.right, n: numberText(n.count), ex: n.examples.slice(0, 3).join(t("pipeline.m.sep.list")) }));
  return lines;
}

/** The parameters each operator takes, for the picker's right-hand side. */
export const OPERATOR_PARAMS = {
  get filter() { return [t("pipeline.m.params.filter.0"), t("pipeline.m.params.filter.1")]; },
  get fill_null() { return [t("pipeline.m.params.fill_null.0"), t("pipeline.m.params.fill_null.1"), t("pipeline.m.params.fill_null.2")]; },
  get text_clean() { return [t("pipeline.m.params.text_clean.0"), t("pipeline.m.params.text_clean.1")]; },
  get cast() { return [t("pipeline.m.params.cast.0"), t("pipeline.m.params.cast.1"), t("pipeline.m.params.cast.2")]; },
  get calc() { return [t("pipeline.m.params.calc.0"), t("pipeline.m.params.calc.1")]; },
  get aggregate() { return [t("pipeline.m.params.aggregate.0"), t("pipeline.m.params.aggregate.1"), t("pipeline.m.params.aggregate.2")]; },
  get dedupe() { return [t("pipeline.m.params.dedupe.0"), t("pipeline.m.params.dedupe.1"), t("pipeline.m.params.dedupe.2")]; },
  get label() { return [t("pipeline.m.params.label.0"), t("pipeline.m.params.label.1"), t("pipeline.m.params.label.2")]; },
  get extract() { return [t("pipeline.m.params.extract.0"), t("pipeline.m.params.extract.1"), t("pipeline.m.params.extract.2")]; },
};

export const durationText = (ms) => (ms == null ? "" : ms < 1000 ? t("pipeline.m.dur.ms", { ms }) : t("pipeline.m.dur.s", { s: (ms / 1000).toFixed(1) }));
export const versionsText = (inputs) => Object.entries(inputs ?? {}).map(([k, v]) => t("pipeline.m.version.item", { name: k.replace(/^view:/, t("pipeline.m.version.view")), v })).join(t("pipeline.m.sep.list"));

// --- the confirm screen ---

/** One step in words, for the before / after of a change. */
export function stepSummary(step, steps = []) {
  if (!step) return [];
  const from = () => nameOf(step.from, steps);
  if (step.type === "input") return [t("pipeline.m.sum.input", { title: stepTitle(step) })];
  if (step.type === "join") {
    return [t("pipeline.m.sum.join", { how: HOW_LABEL[step.how] ?? step.how, a: nameOf(step.left, steps), b: nameOf(step.right, steps) }),
      t("pipeline.m.sum.join_on", { pairs: (step.on ?? []).map((p) => `${p.left} = ${p.right}`).join(t("pipeline.m.sep.comma")), nk: NULL_KEYS_LABEL[step.null_keys ?? "no_match"] }),
      ...(step.right_columns ? [t("pipeline.m.sum.join_right", { cols: list(step.right_columns) })] : [])];
  }
  if (step.type === "transform") return [t("pipeline.m.sum.reads", { from: from() }), ...(step.operators ?? []).map(operatorTitle)];
  if (step.type === "llm") return [t("pipeline.m.sum.llm", { from: from(), name: step.name, template: LLM_TEMPLATE[step.template ?? "empty"] }), t("pipeline.m.sum.model", { model: step.model }), ...llmSettingLines(step)];
  if (step.type === "union") {
    return [t("pipeline.m.sum.union", { title: stepTitle(step, steps) }), step.missing === "empty" ? t("pipeline.m.sum.union_empty") : t("pipeline.m.sum.union_strict"),
      ...(step.source_column ? [t("pipeline.m.sum.union_source", { col: step.source_column })] : [])];
  }
  if (step.type === "split") return [t("pipeline.m.sum.split", { from: from() }), ...(step.branches ?? []).map((b) => t("pipeline.m.sum.split_branch", { id: b.id, what: b.rest ? t("pipeline.m.sum.split_rest") : operatorTitle({ op: "filter", where: b.where }) }))];
  return [t("pipeline.m.sum.output", { from: from(), name: step.name }), ...(step.key ? [t("pipeline.m.sum.key", { cols: list(step.key.columns) })] : []), ...(step.columns ? [t("pipeline.m.sum.keeps", { cols: list(step.columns) })] : [])];
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
  const text = (c) => (c ? t("pipeline.m.stat.text", { nulls: numberText(c.nulls), distinct: numberText(c.distinct), min: c.min ?? "—", max: c.max ?? "—" }) : "—");
  const names = [...new Set([...(after ?? []).map((c) => c.name), ...(before ?? []).map((c) => c.name)])];
  return names.map((name) => {
    const b = (before ?? []).find((c) => c.name === name);
    const a = (after ?? []).find((c) => c.name === name);
    return { name, before: text(b), after: text(a), changed: text(b) !== text(a) };
  });
}

// --- the AI node and the assistant ---

export const LLM_TEMPLATE = labels("llm.template", ["classify", "extract", "summary", "empty"]);
export const LLM_OUTPUT = labels("llm.output", ["text", "choice", "number"]);
export const TRIAL_MODE = labels("llm.trial", ["sample", "rows", "values"]);

/** The lines a person reads of an AI step's settings, for the confirm screen. */
export function llmSettingLines(step) {
  const kind = step.template ?? "empty";
  const col = step.column || t("pipeline.m.title.unset");
  if (kind === "classify") return [t("pipeline.m.llm.classify", { col, cats: (step.categories ?? []).join(t("pipeline.m.sep.list")), multi: step.multiple ? t("pipeline.m.llm.multi") : "" }), ...(step.context ? [t("pipeline.m.llm.context", { text: step.context })] : [])];
  if (kind === "summary") {
    const unit = step.unit === UNIT_SENTENCES ? t("pipeline.m.llm.unit_sentences") : !step.unit || step.unit === UNIT_CHARS ? t("pipeline.m.llm.unit_chars") : step.unit;
    return [t("pipeline.m.llm.summary", { col, size: step.size ?? "?", unit })];
  }
  if (kind === "extract") return [t("pipeline.m.llm.extract", { col, fields: (step.fields ?? []).map((f) => t("pipeline.m.llm.field", { name: f.name, type: f.type === "number" ? t("pipeline.m.llm.field_number") : t("pipeline.m.llm.field_text") })).join(t("pipeline.m.sep.list")) })];
  return [t("pipeline.m.llm.prompt", { text: step.prompt || t("pipeline.m.llm.prompt_empty") }), t("pipeline.m.llm.answer", { what: LLM_OUTPUT[step.output ?? "text"], choices: step.output === "choice" ? t("pipeline.m.llm.choices", { list: (step.choices ?? []).join(t("pipeline.m.sep.list")) }) : "" })];
}

/** What a run (or a read of what is kept) did, as a person says it: "30 answered (18 from earlier answers), 2 failed, 3 skipped". */
export function llmRunText(report) {
  if (!report) return "";
  const parts = [t("pipeline.m.run.answered", { n: numberText(report.answered), cache: report.from_cache ? t("pipeline.m.run.cache", { n: numberText(report.from_cache) }) : "" })];
  if (report.failed) parts.push(t("pipeline.m.run.failed", { n: numberText(report.failed) }));
  if (report.off_list) parts.push(t("pipeline.m.run.off_list", { n: numberText(report.off_list) }));
  if (report.unanswered) parts.push(t("pipeline.m.run.unanswered", { n: numberText(report.unanswered) }));
  if (report.skipped) parts.push(t("pipeline.m.run.skipped", { n: numberText(report.skipped) }));
  if (report.pending) parts.push(t("pipeline.m.run.pending", { n: numberText(report.pending) }));
  return parts.join(t("pipeline.m.sep.comma"));
}

/** One line for each off-list answer. */
export const offListLines = (report) => Object.entries(report?.off_list_answers ?? {}).map(([answer, n]) => t("pipeline.m.run.offlist_line", { answer, n: numberText(n) }));

/** What a run would ask of the model before it starts: calls, characters in, cost when known. */
export function estimateText(estimate) {
  if (!estimate) return "";
  const money = estimate.cost == null ? t("pipeline.m.est.nomoney") : t("pipeline.m.est.money", { cost: estimate.cost });
  const cap = estimate.cap == null ? "" : t("pipeline.m.est.cap", { n: numberText(estimate.cap) });
  return t("pipeline.m.est.text", { calls: numberText(estimate.calls), chars: numberText(estimate.chars_in), money, cap });
}

/** The whole run's calls against the most one run may make, over all its AI steps; null when the service does not say. */
export function runCalls(states) {
  const all = Object.values(states).map((d) => d.estimate);
  if (!all.length || all.some((e) => e.cap == null)) return null;
  const calls = all.reduce((sum, e) => sum + e.calls, 0);
  const cap = Math.min(...all.map((e) => e.cap));
  return { calls, cap, over: calls > cap };
}

/** "17 of 20 rows match" and where the review stands against the line the step names. */
export function reviewText(review) {
  if (!review) return "";
  if (!review.reviewable) return t("pipeline.m.review.noref");
  if (!review.labelled) return t("pipeline.m.review.none");
  if (review.matched == null) return t("pipeline.m.review.unchecked", { n: review.labelled });
  const count = t("pipeline.m.review.count", { total: review.total, matched: review.matched });
  if (!review.current) return t("pipeline.m.review.stale", { count });
  if (review.min_match == null) return t("pipeline.m.review.nomin", { count });
  if (review.need_labelled != null && review.labelled < review.need_labelled) return t("pipeline.m.review.needlabel", { count, need: review.need_labelled, have: review.labelled });
  return t("pipeline.m.review.result", { count, verdict: review.passed ? t("pipeline.m.review.met") : t("pipeline.m.review.missed"), n: review.need_match ?? review.min_match });
}

/** One labelled row for the person who confirms: what the row said, what was expected, what the step answered, and whether they match. */
export function labelledRow(row) {
  const empty = t("pipeline.m.labelled.empty");
  const semi = t("pipeline.m.sep.semi");
  const answered = row.ai == null ? (row.status === "absent" ? t("pipeline.m.labelled.absent") : t("pipeline.m.labelled.unchecked")) : row.ai.map((v) => (v == null ? empty : String(v))).join(semi);
  const expected = row.expected !== null && typeof row.expected === "object" ? Object.values(row.expected).map((v) => (v == null ? empty : String(v))).join(semi) : String(row.expected);
  return { text: Object.values(row.fields).map((v) => (v == null || v === "" ? empty : String(v))).join(" | "), expected, answered, matched: row.matched === true, checked: row.matched != null, who: row.who ?? "—" };
}

/** The AI columns an output keeps and what holds each back from being a key or a code meaning, from the pipeline's AI nodes. */
export const aiNodeLine = (node) => t("pipeline.m.ainode.line", { name: node.name, review: reviewText(node.review), n: numberText(node.cache.current) });

/** A new draft after the assistant's steps were applied: they are ordinary steps from then on. */
export const applyDraft = (spec, steps) => withSteps(spec, steps.map((s) => s.step));

/** The recent sentences a person gave the assistant, newest first, one of each, at most `keep`. */
export function rememberPrompt(list, entry, keep = 8) {
  return [entry, ...list.filter((e) => e.text !== entry.text)].slice(0, keep);
}

/** The values a sample row shows in its columns: the fields of the prompt, in order, empty ones as "empty". */
export const fieldCells = (fields, values) => fields.map((f) => (values[f] == null || values[f] === "" ? t("pipeline.m.labelled.empty") : String(values[f])));

/** Puts a field into the prompt where the caret is, written `${name}`: {text, caret}. */
export function insertField(text, start, end, name) {
  const insert = "${" + name + "}";
  const from = Math.min(start ?? text.length, end ?? text.length);
  const to = Math.max(start ?? text.length, end ?? text.length);
  return { text: text.slice(0, from) + insert + text.slice(to), caret: from + insert.length };
}

/** "Add data": a new input step that already reads `dataset` (the toolbar's dataset menu, as DIP's 添加数据). */
export function dataInput(steps, dataset) {
  return { ...newStep(steps, "input", null), dataset };
}

/** The canvas search: the steps whose title, kind or dataset contains `query`, ignoring case; nothing for an empty query. */
export function findSteps(steps, query) {
  const q = String(query ?? "").trim().toLowerCase();
  if (!q) return [];
  return steps.filter((s) => [stepTitle(s, steps), KIND_LABEL[s.type] ?? "", s.type, s.dataset ?? ""].some((x) => String(x).toLowerCase().includes(q)));
}
