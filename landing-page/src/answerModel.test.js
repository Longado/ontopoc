import assert from "node:assert/strict";
import test from "node:test";

import { derivedCard, editedLabel, elsewhereLine, mustExplain, noteHint, reasonView, reviewPoints, statusPill } from "./answerModel.js";

test("a reason the model wrote is said in one plain sentence, its words one click away", () => {
  const item = { status: "query_limit", reason: "要从 客户 经 下单 到 订单明细，再算 单价 × 数量 ×（1 − 折扣）", reason_from_model: true };
  assert.deepEqual(reasonView(item), { line: "模型说现在的查询写不出这道题。这是模型的判断，代码没有核对过。", detail: item.reason });
  assert.deepEqual(reasonView({ ...item, status: "ontology_gap" }), { line: "模型说本体里缺回答它要的对象、关系或字段。这是模型的判断，代码没有核对过。", detail: item.reason });
});

test("a reason code found is short and stands as it is", () => {
  const item = { status: "ontology_gap", reason: "本体里的 订单明细 没有属性 地区，无法按它筛选" };
  assert.deepEqual(reasonView(item), { line: item.reason, detail: null });
  assert.equal(reasonView({ status: "answered" }), null);
});

test("a derived measure waiting for the person shows the formula, what code computed and what it could not", () => {
  const item = { status: "needs_derived", derive: { type: "order_line", label: "金额", formula: "单价 × 数量 ×（1 − 折扣）",
    preview: { counted: 2155, skipped: 2, skipped_examples: ["10248 · 11：折扣 = 无 不是数字"], examples: [{ name: "10248 · 11", value: 168 }] } } };
  assert.deepEqual(derivedCard(item, "订单明细"), {
    formula: "金额 = 单价 × 数量 ×（1 − 折扣）",
    tried: "在全部订单明细上试算：算出 2,155 个，2 个算不了",
    examples: ["10248 · 11 → 168"],
    skipped: ["10248 · 11：折扣 = 无 不是数字"],
  });
});

// The payment question as the exam run produced it: the model added two conditions the question never says; one removed nothing.
const ontology = { object_types: [{ key: "financial_transaction", label: "财务支出行" }, { key: "contract", label: "合同授标" }, { key: "parent_vehicle", label: "母合同" }] };
const paid = (over = {}) => ({
  question: "垦务局签的合同在 2025 财年第一季度（截至 2024-12-31）累计付了多少钱？", status: "answered",
  query: { start: "financial_transaction", where: [{ field: "period_end_date", equals: "2024-12-31" }, { field: "award_agency_id", equals: "1425" }, { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" }],
    measure: { field: "gross_outlay_fyb_to_period_end", op: "sum" } },
  answer: { total: 1444, measure: { field: "gross_outlay_fyb_to_period_end", op: "sum", value: 140216640.65, counted: 1213, skipped: 231 } },
  evidence: { filters: [
    { field: "period_end_date", equals: "2024-12-31", before: 1921, after: 1455, examples: [], removed_measure: 24998153.82 },
    { field: "award_agency_id", equals: "1425", before: 1455, after: 1455, examples: [], not_in_question: true },
    { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", before: 1455, after: 1444, examples: [], removed_measure: 4176392.96, not_in_question: true }] },
  ...over,
});

test("a condition the model added that took rows away is listed with what it took, and the one that took none is not", () => {
  assert.deepEqual(reviewPoints(paid(), ontology), [{ kind: "filter", field: "awarding_subagency", equals: "BUREAU OF RECLAMATION",
    line: "模型自己加了条件“awarding_subagency = BUREAU OF RECLAMATION”，问题里没提：筛掉 11 个财务支出行，按“gross_outlay_fyb_to_period_end”合计 4,176,392.96。",
    drop: { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" } }]);
});

test("the condition to drop is the query's own entry, matched by value and then by position", () => {
  const unasked = (field, before, after) => ({ field, equals: "1", before, after, examples: [], not_in_question: true });
  const item = { status: "answered", query: { start: "contract", where: [{ field: "甲字段", equals: "1" }, { field: "乙字段", equals: "1" }] },
    evidence: { filters: [unasked("a", 10, 8), unasked("b", 8, 5)] } };
  assert.deepEqual(reviewPoints(item, ontology).map((p) => p.drop), [{ field: "甲字段", equals: "1" }, { field: "乙字段", equals: "1" }]);   // the query's spelling, not the check pack's
  assert.deepEqual(reviewPoints({ ...item, query: { start: "contract" } }, ontology).map((p) => p.drop), [null, null]);   // nothing to drop it from
});

test("without a measure the line says only how many rows went, and an unnamed object type reads as 对象", () => {
  const item = { status: "answered", query: { start: "contract", where: [{ field: "x", equals: "1" }] },
    evidence: { filters: [{ field: "x", equals: "1", before: 5, after: 2, not_in_question: true }] } };
  assert.equal(reviewPoints(item, ontology)[0].line, "模型自己加了条件“x = 1”，问题里没提：筛掉 3 个合同授标。");
  assert.equal(reviewPoints(item)[0].line, "模型自己加了条件“x = 1”，问题里没提：筛掉 3 个对象。");
});

test("a group several objects were counted as one is listed by what was merged", () => {
  const item = { status: "answered", query: { start: "vendor" }, evidence: { merged: [
    { group: "GREENBERRY INDUSTRIAL LLC", starts: 1, objects: 2, start: "承包商", reached: "最终母公司", examples: ["PRRXANJSLS26", "ZZ3GL25MGJH2"] },
    { group: "华东", starts: 3, objects: 4, start: "门店", reached: "大区", examples: ["a", "b"] }] } };
  assert.deepEqual(reviewPoints(item, ontology), [
    { kind: "merged", line: "“GREENBERRY INDUSTRIAL LLC”这一组把 2 个不同的最终母公司（PRRXANJSLS26、ZZ3GL25MGJH2）算成了一个。" },
    { kind: "merged", line: "“华东”这一组下有 3 个门店各连到不止一个不同的大区，最多 4 个（例如 a、b），按同一个算了。" }]);
});

test("only an answer that was given has anything to check", () => {
  assert.deepEqual(reviewPoints(paid({ status: "no_data" }), ontology), []);
  assert.deepEqual(reviewPoints({ status: "answered", query: { start: "contract" } }, ontology), []);
});

test("an answer with something to check says so in amber, and the plain ones keep their own label", () => {
  const labels = { answered: "能回答", no_data: "数据里没有", broken: "查询失效", ontology_gap: "本体缺这一块" };
  assert.deepEqual(statusPill(paid(), labels), { cls: "review", text: "能回答，要核对" });
  assert.deepEqual(statusPill(paid({ evidence: {} }), labels), { cls: "answered", text: "能回答" });
  assert.deepEqual(statusPill({ status: "no_data" }, labels), { cls: "no_data", text: "数据里没有" });
  assert.deepEqual(statusPill({ status: "broken" }, labels), { cls: "ontology_gap", text: "查询失效" });
});

test("an answer worked again without a condition says which one went and that no model was called", () => {
  assert.equal(editedLabel({ edited: { dropped: [{ field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" }] } }), "去掉了条件“awarding_subagency = BUREAU OF RECLAMATION”后重算，没调模型");
  assert.equal(editedLabel({ edited: { dropped: [{ field: "a", equals: "1" }, { field: "b", equals: "2" }] } }), "去掉了条件“a = 1”、“b = 2”后重算，没调模型");
  assert.equal(editedLabel({}), "");
});

test("a value missing from the start object but found on another says where, and that the question may mean that one", () => {
  const item = { status: "no_data", query: { start: "contract", where: [{ field: "piid", equals: "GS03F102CA" }] },
    evidence: { found_elsewhere: [{ type: "parent_vehicle", equals: "GS03F102CA", linked: 9 }] } };
  assert.equal(elsewhereLine(item, ontology), "合同授标里没有“GS03F102CA”；母合同里有（9 个合同授标连着它）。这道题问的可能是母合同。");
  assert.equal(elsewhereLine({ ...item, evidence: { found_elsewhere: [{ type: "parent_vehicle", label: "框架合同", equals: "GS03F102CA" }] } }, ontology),
    "合同授标里没有“GS03F102CA”；框架合同里有。这道题问的可能是框架合同。");
  assert.equal(elsewhereLine({ ...item, evidence: {} }, ontology), "");
  assert.equal(elsewhereLine({ ...item, status: "answered" }, ontology), "");
});

test("the note a person must write before fixing such an answer says which conditions the client has to stand behind", () => {
  const [one] = reviewPoints(paid(), ontology);
  assert.equal(noteHint([one]), "模型加了条件“awarding_subagency = BUREAU OF RECLAMATION”。客户认可这个条件，就在口径里写一句为什么；不认可就先点“去掉这个条件重算”。");
  assert.equal(noteHint([one, { ...one, field: "b", equals: "2" }]), "模型加了条件“awarding_subagency = BUREAU OF RECLAMATION”、“b = 2”。客户认可这些条件，就在口径里写一句为什么；不认可就先点“去掉这个条件重算”。");
  assert.equal(noteHint([{ kind: "merged", line: "…" }]), "有 1 组把几个不同的对象算成了一个，客户认可这样算，就在口径里写一句为什么。");
  assert.equal(noteHint([one, { kind: "merged", line: "…" }]).endsWith("另外有 1 组把几个不同的对象算成了一个，客户认可这样算，也在口径里写一句为什么。"), true);
  assert.equal(noteHint([]), "");
});

// A fixed question carries the note its basis was written in; the same answer asked in the box has none.
const fixed = (note, over = {}) => paid({ note, ...over });
const labels = { answered: "能回答", no_data: "数据里没有", broken: "查询失效", ontology_gap: "本体缺这一块" };
const groups = { merged: [{ group: "GREENBERRY INDUSTRIAL LLC", starts: 1, objects: 2, start: "承包商", reached: "最终母公司", examples: ["PRRXANJSLS26", "ZZ3GL25MGJH2"] }] };

test("a fixed question whose basis is written down says the model's condition is settled, with nothing left to drop", () => {
  assert.deepEqual(reviewPoints(fixed("只算垦务局自己签的合同"), ontology), [{ kind: "filter", field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", settled: true, drop: null,
    line: "口径里已写明：模型加了条件“awarding_subagency = BUREAU OF RECLAMATION”（筛掉 11 个财务支出行，按“gross_outlay_fyb_to_period_end”合计 4,176,392.96）。" }]);
  assert.equal(reviewPoints(fixed("  "), ontology)[0].settled, undefined);   // a blank note writes nothing down
  assert.equal(reviewPoints(paid(), ontology)[0].settled, undefined);   // the same answer asked in the box is not settled
});

test("a fixed question with its basis written down carries the plain label, but a merged group still asks to be looked at", () => {
  assert.deepEqual(statusPill(fixed("只算垦务局自己签的合同"), labels), { cls: "answered", text: "能回答" });
  assert.deepEqual(statusPill(fixed(""), labels), { cls: "review", text: "能回答，要核对" });
  assert.deepEqual(statusPill(fixed("只算垦务局自己签的合同", { evidence: { ...paid().evidence, ...groups } }), labels), { cls: "review", text: "能回答，要核对" });
});

test("whichever button fixes an answer with something to check, it cannot go without a line on why", () => {
  assert.equal(mustExplain(paid(), ""), true);
  assert.equal(mustExplain(paid(), "  "), true);
  assert.equal(mustExplain(paid(), "客户只要垦务局签的"), false);
  assert.equal(mustExplain(paid({ evidence: {} }), ""), false);
  assert.equal(mustExplain(paid({ status: "no_data" }), ""), false);
});
