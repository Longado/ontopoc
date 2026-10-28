// The data-meaning card (口径卡): what the service works out about every uploaded table, and the answers a person writes
// down for the client. The words are the contract's, kept here and nowhere else.
import { localTime } from "./ontologyStudioModel.js";

const count = (n) => n.toLocaleString("zh-CN");

const UNSURE = ["unsure", "说不清"];
export const CARD_VOCAB = {
  grain: [["one_object", "一行就是一个对象"], ["event", "一行是一次事件或一次修改（同一个东西有多行）"], ["period", "一行是一段时期的汇总"], UNSURE],
  date: [["business", "业务发生的日期"], ["system", "系统录入或修改的时间"], ["fetched", "取数的时间"], UNSURE],
  amount: [["flow", "每行是这一笔自己的数，可以跨行相加"], ["running", "每次事件后的累计值"], ["latest", "截至最近一次的值"],
    ["period_to_date", "期初到期末的累计值"], ["not_amount", "不是数量（编号或代码）"], UNSURE],
  complete: [["full", "数据里是全的"], ["partial", "数据里只有一部分"], UNSURE],
};

export const saysOf = (kind, value) => CARD_VOCAB[kind]?.find(([v]) => v === value)?.[1] || "";

const SAME_OR_NOT = [["distinct", "是不同的对象"], ["same", "是同一个"]];
/** The choices a thing to settle offers; every other answerable kind is answered in words only. */
export const ITEM_CHOICES = {
  unlinked: [["expected", "本来就没有对应，属正常"], ["incomplete", "数据没导全"]],
  same_name: SAME_OR_NOT,
  merged: SAME_OR_NOT,
};
const WORDS_ONLY = ["found_elsewhere", "unstable", "check_finding", "data_gaps", "unanswered"];
// model_filter is settled by dropping the condition, unjudged by judging each one, card_blank by filling the card
const ANSWERABLE = [...Object.keys(ITEM_CHOICES), ...WORDS_ONLY];

export const itemChoices = (item) => ITEM_CHOICES[item.kind] || [];
export const canAnswerItem = (item) => Boolean(item.id) && ANSWERABLE.includes(item.kind);

// complete:{table}|{key columns}[|{where conditions}]: the table is what comes before the first bar
const sourceOfComplete = (id) => id.slice("complete:".length).split("|")[0];

/** Every cell on the card in the order the page shows them: each table's, then the objects'.
 *  `table` is the table the cell is about, `name` what the person reads beside it. */
export function cardCells(card) {
  if (!card) return [];
  const cell = (id, kind, table, name, answer) => ({ id, kind, table, name, answer });
  return [
    ...card.tables.flatMap((t) => [
      cell(t.grain.id, "grain", t.source, "一行是什么", t.grain.answer),
      ...t.dates.flatMap((d) => [cell(d.id, "date", t.source, d.field, d.answer), cell(d.range_id, "range", t.source, d.field, d.declared)]),
      ...t.amounts.map((a) => cell(a.id, "amount", t.source, a.field, a.answer)),
    ]),
    ...card.objects.map((o) => cell(o.id, "complete", sourceOfComplete(o.id), o.label, o.answer)),
  ];
}

// A declared period with neither end is nothing declared
const period = (v) => { const from = v?.from || null, to = v?.to || null; return from || to ? { from, to } : null; };
const same = (kind, a, b) => {
  if (kind !== "range") return (a ?? null) === (b ?? null);
  const [x, y] = [period(a), period(b)];
  return x?.from === y?.from && x?.to === y?.to;
};

/** The cells that differ from what is saved, ready for the request; `draft` maps a cell id to the value the person set.
 *  A null value clears the cell. One basis goes on all of them. */
export function changedCells(card, draft, basis = "") {
  const written = basis.trim();
  return cardCells(card).filter((c) => c.id in draft && !same(c.kind, draft[c.id], c.answer?.value))
    .map((c) => ({ id: c.id, value: c.kind === "range" ? period(draft[c.id]) : draft[c.id] ?? null, ...(written ? { basis: written } : {}) }));
}

/** The request body: cells and items only when there are some, since the service wants at least one of them. */
export function cardBody({ saved_as, by, cells = [], items = [] }) {
  return { saved_as, by: by.trim(), ...(cells.length ? { cells } : {}), ...(items.length ? { items } : {}) };
}

/** The edits on the card not saved yet. They are kept above the card's page, so a visit to another page does not lose
 *  them, and they belong to one run: another run starts blank. */
export const draftOf = (kept, saved_as) => (kept && kept.saved_as === saved_as ? kept : { saved_as, cells: {}, basis: "" });
export const editCell = (kept, saved_as, id, value) => {
  const draft = draftOf(kept, saved_as);
  return { ...draft, cells: { ...draft.cells, [id]: value } };
};
export const editBasis = (kept, saved_as, basis) => ({ ...draftOf(kept, saved_as), basis });

const byProblem = (by) => (!by.trim() ? "先填答复人" : by.trim().length > 40 ? "答复人最多 40 个字" : "");

/** What stops the card from being saved, in words; "" when it can go. */
export function saveProblem(by, cells, items) {
  return byProblem(by) || (cells.length || items.length ? "" : "还没有改动");
}

const ANSWERER_KEY = "ontopoc.card.by";
// the person's name is a convenience: a browser that will not keep it just asks again next time
export function readAnswerer(storage) {
  try { return storage?.getItem(ANSWERER_KEY) || ""; } catch { return ""; }
}
export function rememberAnswerer(storage, name) {
  try { storage?.setItem(ANSWERER_KEY, name); } catch { /* storage blocked: nothing to remember in */ }
}

/** Who answered, which day, and the basis if they gave one, as parts the caller joins. */
export const stampParts = (answer) => (!answer ? [] : [answer.by, localTime(answer.at).slice(0, 5), ...(answer.basis ? [`出处：${answer.basis}`] : [])]);
export const stampLine = (answer) => stampParts(answer).join(" · ");

/** What the pipeline must do to a number column written with thousands separators or placeholders ("" for a strict number column). */
export function noiseLine(noise) {
  const holders = Object.entries(noise?.placeholders || {}).map(([text, n]) => `“${text}” ${count(n)} 个`);
  const parts = [...(noise?.thousands ? [`千分位 ${count(noise.thousands)} 个`] : []), ...(holders.length ? [`占位符 ${holders.join("、")}`] : [])];
  return parts.length ? `有${parts.join("、")}，编排时要转成数值` : "";
}

// the 编排需求单: what each table needs done before it is used, for whoever builds the data pipeline. The header links it, the card page points at it.
export const PIPELINE_EXPORT = { label: "⤓ 编排需求单", title: "交给搭数据管道的人：每张表要做的清洗、关联、按期取数和校验，来自体检和客户答复" };
export const CARD_PIPELINE_NOTE = `填好的答复会写进编排需求单（页头 ${PIPELINE_EXPORT.label}）`;
export const pipelineUrl = (saved_as) => `/api/ontology/runs/${saved_as}/export/pipeline`;

/** The code's fact about a table's identity fields: how many rows, how many distinct (rows with an empty identity field
 *  among them), which repeat. */
export function uniqueLine(unique, rows) {
  if (!unique) return "这张表上没有识别字段，看不出一行是不是唯一的";
  const blank = unique.blank ? `其中 ${count(unique.blank)} 行识别字段是空的，` : "";
  const repeats = unique.duplicates
    ? `有 ${unique.duplicates} 个组合出现了不止一次${unique.examples.length ? `（例如 ${unique.examples.join("；")}）` : ""}` : "没有重复";
  return `${unique.fields.join(" + ")}：${count(rows)} 行，${count(unique.distinct)} 种不同的组合，${blank}${repeats}`;
}

export const blankLine = (card) => `共 ${card.cells} 格，${card.blank ? `还有 ${card.blank} 格没说清` : "都答过了"}`;

/** What an empty card means: nothing to fill, or nothing built because the ontology never passed verification. */
export const cardEmptyText = (run) => (run.ontology.status === "auto_built_verified" ? "这次运行没有可填的表。" : "本体还没通过核验，代码先不出口径卡。");

/** The answers on the card that stand as what the client said, by table. An answer of "unsure" is not one. */
export function confirmedCells(card) {
  const cells = cardCells(card).filter((c) => c.answer && c.answer.value != null && c.answer.value !== "unsure");
  return [...new Set(cells.map((c) => c.table))].map((source) => ({ source,
    lines: cells.filter((c) => c.table === source).map((c) => ({ name: c.name, says: c.answer.says, by: c.answer.by, basis: c.answer.basis || "", note: c.answer.note || "" })) }));
}

/** What answering a thing to settle sends: the item's answer alone. For an unlinked one the client says was not all
 *  imported, the service marks the other end's objects as only partly there, and takes that back if the answer changes. */
export function itemAnswer(item, form) {
  const [text, basis] = [form.text.trim(), form.basis.trim()];
  return { items: [{ id: item.id, ...(form.choice ? { choice: form.choice } : {}), ...(text ? { text } : {}), ...(basis ? { basis } : {}) }] };
}

/** What saving the answer will also do on the card, said beside the form: "" when it does nothing there. `answer` is the old one. */
export function linkedHint(item, form, answer = null) {
  if (item.kind !== "unlinked" || !item.complete_id) return "";
  if (form.choice === "incomplete") return "另一端的对象会同时在口径卡上记成“数据里只有一部分”。";
  return answer?.choice === "incomplete" ? "口径卡上那一格如果是这条答复记的，会一起清掉。" : "";
}

/** What stops an answer from being saved, in words; "" when it can go. */
export function itemProblem(item, form, by) {
  if (byProblem(by)) return byProblem(by);
  if (form.choice || form.text.trim()) return "";
  return itemChoices(item).length ? "选一项，或写下客户怎么答的" : "写下客户怎么答的";
}

/** The form for changing an answer starts from the old one. */
export const itemForm = (answer) => ({ choice: answer?.choice || "", text: answer?.text || "", basis: answer?.basis || "" });

/** The things the client has answered: the question as it was asked then, what the answer says, and who gave it. */
export const answeredRows = (answered) => answered.map((item) => ({ id: item.id, item, asked: item.answer.asked || item.ask,
  says: [item.answer.says, item.answer.text].filter(Boolean).join("："), stamp: stampLine(item.answer) }));

/** What an answer worked out with the card says about itself: the tables used, the client's meanings followed, and the
 *  objects the data holds only part of. Null when the card had no say in it. */
export function cardEvidence(item) {
  const card = item.evidence?.card;
  if (!card) return null;
  const used = (card.tables || []).map((t) => `${t.source}（${count(t.rows)} 行${t.through ? `，数据到 ${t.through}` : ""}）`);
  const name = (l) => l.field || l.label || l.id;
  const warned = new Set((card.incomplete || []).map((i) => i.label));   // an object warned about below is not also listed as followed
  return {
    data: used.length ? `用的数据：${used.join("；")}` : "",
    lines: (card.lines || []).filter((l) => !(l.id?.startsWith("complete:") && warned.has(name(l))))
      .map((l) => `按口径：「${name(l)}」是${l.says}（${l.by} 答复${l.basis ? `，出处：${l.basis}` : ""}）`),
    incomplete: (card.incomplete || []).map((i) => `${i.label}在数据里只有一部分${i.note ? `：${i.note}` : ""}`),
  };
}
