// How an answer that cannot be given says why, what an answer that was given still leaves to check, and what a
// derived measure waiting for the person shows.
import { typeLabel } from "./ontologyStudioModel.js";

// A reason the model wrote is its reasoning, not a finding: the page says one fixed plain sentence per status and
// keeps the model's words one click away. A reason code found is short and exact, so it stands as it is.
const MODEL_SAYS = {
  query_limit: "模型说现在的查询写不出这道题。这是模型的判断，代码没有核对过。",
  ontology_gap: "模型说本体里缺回答它要的对象、关系或字段。这是模型的判断，代码没有核对过。",
  no_data: "本体里有这一块，但数据里没有能回答它的行。",
};

export function reasonView(item) {
  if (item.status === "answered" || !item.reason) return null;
  if (!item.reason_from_model) return { line: item.reason, detail: null };
  return { line: MODEL_SAYS[item.status] || "现在答不了。", detail: item.reason };
}

const count = (n) => n.toLocaleString("zh-CN");

export function derivedCard(item, typeLabel) {
  const { label, formula, preview } = item.derive;
  return {
    formula: `${label} = ${formula}`,
    tried: `在全部${typeLabel}上试算：算出 ${count(preview.counted)} 个${preview.skipped ? `，${count(preview.skipped)} 个算不了` : ""}`,
    examples: preview.examples.map((e) => `${e.name} → ${count(e.value)}`),
    skipped: preview.skipped_examples,
  };
}

const money = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
// "例如" only when the examples are not all of them
const shown = (examples, all) => (examples?.length ? `${all > examples.length ? "例如 " : ""}${examples.join("、")}` : "");

/** What an answer that was given still leaves for a person to look at: conditions the model added that took rows away
 *  (each with the query's own entry to drop it by) and groups several objects were counted into as one. A fixed
 *  question whose basis a person wrote down has had its conditions settled: they are said, not asked about. */
export function reviewPoints(item, ontology) {
  if (item.status !== "answered") return [];
  const settled = Boolean(item.note?.trim());
  const e = item.evidence || {};
  const where = item.query?.where || [];
  const noun = ontology && item.query?.start ? typeLabel(ontology, item.query.start) : "对象";
  const measure = item.answer?.measure?.field;
  // each check-pack filter belongs to one entry of the query: the one at its position if the value agrees, else the first free one that does
  const claimed = new Set();
  const entries = (e.filters || []).map((f, i) => {
    const at = [i, ...where.keys()].find((j) => !claimed.has(j) && where[j]?.equals === f.equals);
    if (at !== undefined) claimed.add(at);
    return at === undefined ? null : where[at];
  });
  const filters = (e.filters || []).flatMap((f, i) => {
    if (!f.not_in_question || !(f.after < f.before)) return [];
    const lost = f.removed_measure !== undefined && measure ? `，按“${measure}”合计 ${money.format(f.removed_measure)}` : "";
    const cut = `筛掉 ${money.format(f.before - f.after)} 个${noun}${lost}`;
    if (settled) return [{ kind: "filter", field: f.field, equals: f.equals, settled, drop: null, line: `口径里已写明：模型加了条件“${f.field} = ${f.equals}”（${cut}）。` }];
    return [{ kind: "filter", field: f.field, equals: f.equals, drop: entries[i] ? { field: entries[i].field, equals: entries[i].equals } : null,
      line: `模型自己加了条件“${f.field} = ${f.equals}”，问题里没提：${cut}。` }];
  });
  const merged = (e.merged || []).map((m) => {
    const [start, reached] = [m.start || "对象", m.reached || "对象"];   // results saved before the type labels were kept say 对象
    const named = shown(m.examples, m.objects);
    const eg = named ? `（${named}）` : "";
    return { kind: "merged", line: m.starts === 1 ? `“${m.group}”这一组把 ${m.objects} 个不同的${reached}${eg}算成了一个。`
      : `“${m.group}”这一组下有 ${m.starts} 个${start}各连到不止一个不同的${reached}，最多 ${m.objects} 个${eg}，按同一个算了。` };
  });
  return [...filters, ...merged];
}

const QUERY_CAN = "查询能数个数、算占比、求和求平均、按几样东西分组、对确认过的指标求和；还不能限定时间段、按数值条件筛选、一道题同时给两个数";

/** What a query can do, offered beside a way of asking it cannot do. A question the card stopped is not one of those:
 *  the query could be written, the client's own answer on the card says it must not be added that way. */
export const queryCanHint = (item) => (item.status === "query_limit" && !item.refused_by_card ? QUERY_CAN : undefined);

/** The label on an answer: the card's refusal, amber when there is something left to check, else the status as it reads. */
export function statusPill(item, labels) {
  const cls = item.status === "broken" ? "ontology_gap" : item.status;
  if (item.refused_by_card) return { cls, text: "口径卡拦下了" };
  if (reviewPoints(item).some((p) => !p.settled)) return { cls: "review", text: "能回答，要核对" };
  return { cls, text: labels[item.status] || item.status };
}

/** Said beside an answer worked out again without a condition: which one went, and that no model was asked. */
export function editedLabel(item) {
  const dropped = item.edited?.dropped || [];
  return dropped.length ? `去掉了条件${dropped.map((c) => `“${c.field} = ${c.equals}”`).join("、")}后重算，没调模型` : "";
}

/** A value the question named is not on the start object but is on another type: say where, so the person can say
 *  the question meant that one. "" when there is nothing like that to say. */
export function elsewhereLine(item, ontology) {
  const found = [].concat(item.evidence?.found_elsewhere || []);
  if (item.status !== "no_data" || !found.length) return "";
  const label = (key) => (ontology ? typeLabel(ontology, key) : key);
  const start = item.query?.start ? label(item.query.start) : "对象";
  const names = found.map((f) => f.label || label(f.type));
  const value = found[0].equals ?? item.query?.where?.[0]?.equals;
  const there = found.map((f, i) => `${names[i]}里有${f.linked ? `（${f.linked} 个${start}连着它）` : ""}`).join("；");
  return `${start}里没有“${value}”；${there}。这道题问的可能是${names.join("或")}。`;
}

/** Whether fixing this answer waits for a line on why the client stands behind it: something to check, and none written. */
export const mustExplain = (item, note) => !note?.trim() && reviewPoints(item).length > 0;

/** What the person is told to do before fixing an answer that has something to check. */
export function noteHint(points) {
  const conditions = points.filter((p) => p.kind === "filter").map((p) => `“${p.field} = ${p.equals}”`);
  const merged = points.filter((p) => p.kind === "merged").length;
  return [
    conditions.length ? `模型加了条件${conditions.join("、")}。客户认可${conditions.length > 1 ? "这些条件" : "这个条件"}，就在口径里写一句为什么；不认可就先点“去掉这个条件重算”。` : "",
    merged ? `${conditions.length ? "另外" : ""}有 ${merged} 组把几个不同的对象算成了一个，客户认可这样算，${conditions.length ? "也" : "就"}在口径里写一句为什么。` : "",
  ].join("");
}
