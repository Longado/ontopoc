import assert from "node:assert/strict";
import test from "node:test";

import {
  CARD_VOCAB, ITEM_CHOICES, answeredRows, blankLine, canAnswerItem, cardBody, cardCells, cardEmptyText, cardEvidence, changedCells, confirmedCells,
  itemAnswer, itemChoices, itemForm, itemProblem, readAnswerer, rememberAnswerer, saveProblem, saysOf, stampLine, uniqueLine,
} from "./cardModel.js";

const at = new Date(2026, 9, 27, 12, 0).toISOString();   // local noon: the same day in every time zone
const said = (value, extra = {}) => ({ value, says: saysOf("amount", value), by: "张三", basis: "10-27 会议", at, ...extra });

const card = (over = {}) => ({
  tables: [{ source: "financial_rows", rows: 1921,
    objects: [{ type: "financial_transaction", label: "财务支出行", identity: ["source_row", "submission_period"] }],
    grain: { id: "grain:financial_rows", unique: { fields: ["source_row", "submission_period"], distinct: 1921, duplicates: 0, examples: [] }, answer: null },
    dates: [{ id: "date:financial_rows.period_end_date", range_id: "range:financial_rows.period_end_date", field: "period_end_date", type: "DATE",
      min: "2024-11-30", max: "2024-12-31", empty: 0, answer: null, declared: null }],
    amounts: [{ id: "amount:financial_rows.gross_outlay_fyb_to_period_end", field: "gross_outlay_fyb_to_period_end", type: "DECIMAL", empty: 231, answer: null }] }],
  objects: [{ id: "complete:financial_rows|source_row,submission_period", type: "financial_transaction", label: "财务支出行", count: 1921, answer: null }],
  cells: 4, blank: 4, ...over,
});
const AMOUNT = "amount:financial_rows.gross_outlay_fyb_to_period_end";
const DATE = "date:financial_rows.period_end_date";
const RANGE = "range:financial_rows.period_end_date";
const COMPLETE = "complete:financial_rows|source_row,submission_period";

test("the card's words are the contract's, in one place", () => {
  assert.deepEqual(CARD_VOCAB.grain.map(([v]) => v), ["one_object", "event", "period", "unsure"]);
  assert.equal(saysOf("grain", "one_object"), "一行就是一个对象");
  assert.equal(saysOf("grain", "event"), "一行是一次事件或一次修改（同一个东西有多行）");
  assert.equal(saysOf("grain", "period"), "一行是一段时期的汇总");
  assert.equal(saysOf("date", "business"), "业务发生的日期");
  assert.equal(saysOf("date", "system"), "系统录入或修改的时间");
  assert.equal(saysOf("date", "fetched"), "取数的时间");
  assert.equal(saysOf("amount", "flow"), "每行是这一笔自己的数，可以跨行相加");
  assert.equal(saysOf("amount", "running"), "每次事件后的累计值");
  assert.equal(saysOf("amount", "latest"), "截至最近一次的值");
  assert.equal(saysOf("amount", "period_to_date"), "期初到期末的累计值");
  assert.equal(saysOf("amount", "not_amount"), "不是数量（编号或代码）");
  assert.equal(saysOf("complete", "full"), "数据里是全的");
  assert.equal(saysOf("complete", "partial"), "数据里只有一部分");
  for (const kind of ["grain", "date", "amount", "complete"]) assert.equal(saysOf(kind, "unsure"), "说不清");
  assert.equal(saysOf("amount", "nope"), "");
});

test("the card lays out its cells table by table, the objects last, each with the id the service gave", () => {
  const cells = cardCells(card());
  assert.deepEqual(cells.map((c) => [c.id, c.kind]), [
    ["grain:financial_rows", "grain"], [DATE, "date"], [RANGE, "range"], [AMOUNT, "amount"], [COMPLETE, "complete"]]);
  assert.equal(cells[2].name, "period_end_date");
  assert.equal(cells[4].name, "财务支出行");
  assert.equal(cells[0].table, "financial_rows");
  assert.equal(cells[4].table, "financial_rows");   // the table an object's cell is for is in the cell's id
  assert.deepEqual(cardCells(null), []);
});

test("only the cells that were changed go in the request: a cell put back to what is saved is not a change", () => {
  const saved = card();
  saved.tables[0].amounts[0].answer = said("flow");
  assert.deepEqual(changedCells(saved, {}), []);
  assert.deepEqual(changedCells(saved, { [AMOUNT]: "flow" }), []);
  assert.deepEqual(changedCells(saved, { [AMOUNT]: "period_to_date", [DATE]: "business" }), [
    { id: DATE, value: "business" }, { id: AMOUNT, value: "period_to_date" }]);   // in the order the card shows them
  assert.deepEqual(changedCells(saved, { [AMOUNT]: null }), [{ id: AMOUNT, value: null }]);   // null clears the cell
  assert.deepEqual(changedCells(saved, { "amount:gone.x": "flow" }), []);   // a cell no longer on the card is dropped
});

test("one basis written on the page goes on every cell that changed", () => {
  assert.deepEqual(changedCells(card(), { [DATE]: "system" }, " 10-27 会议 "), [{ id: DATE, value: "system", basis: "10-27 会议" }]);
  assert.deepEqual(changedCells(card(), { [DATE]: "system" }, "  "), [{ id: DATE, value: "system" }]);
});

test("a declared period is sent as from and to, and blank on both ends clears it", () => {
  assert.deepEqual(changedCells(card(), { [RANGE]: { from: "2024-10-01", to: "2024-12-31" } }), [{ id: RANGE, value: { from: "2024-10-01", to: "2024-12-31" } }]);
  assert.deepEqual(changedCells(card(), { [RANGE]: { from: "", to: "2024-12-31" } }), [{ id: RANGE, value: { from: null, to: "2024-12-31" } }]);
  assert.deepEqual(changedCells(card(), { [RANGE]: { from: "", to: "" } }), []);   // nothing declared, nothing saved: no change
  const declared = card();
  declared.tables[0].dates[0].declared = { value: { from: "2024-10-01", to: "2024-12-31" }, says: "声明覆盖 2024-10-01 至 2024-12-31", by: "张三", at };
  assert.deepEqual(changedCells(declared, { [RANGE]: { from: "2024-10-01", to: "2024-12-31" } }), []);
  assert.deepEqual(changedCells(declared, { [RANGE]: { from: "", to: "" } }), [{ id: RANGE, value: null }]);
});

test("the request carries the run, the person, and only what there is to save", () => {
  const cells = [{ id: DATE, value: "business" }];
  const items = [{ id: "data_gaps", text: "客户说另一个系统还有" }];
  assert.deepEqual(cardBody({ saved_as: "r.json", by: " 张三 ", cells }), { saved_as: "r.json", by: "张三", cells });
  assert.deepEqual(cardBody({ saved_as: "r.json", by: "张三", items }), { saved_as: "r.json", by: "张三", items });
  assert.deepEqual(cardBody({ saved_as: "r.json", by: "张三", cells, items }), { saved_as: "r.json", by: "张三", cells, items });
});

test("saving says what is missing before it is sent", () => {
  const cells = [{ id: DATE, value: "business" }];
  assert.equal(saveProblem("张三", cells, []), "");
  assert.equal(saveProblem("张三", [], [{ id: "data_gaps" }]), "");
  assert.equal(saveProblem("  ", cells, []), "先填答复人");
  assert.equal(saveProblem("张".repeat(41), cells, []), "答复人最多 40 个字");
  assert.equal(saveProblem("张三", [], []), "还没有改动");
});

test("the person who answers is remembered in this browser, and not having a browser to remember in is fine", () => {
  const store = new Map();
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  assert.equal(readAnswerer(storage), "");
  rememberAnswerer(storage, "张三");
  assert.equal(readAnswerer(storage), "张三");
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.equal(readAnswerer(broken), "");
  assert.doesNotThrow(() => rememberAnswerer(broken, "张三"));
  assert.equal(readAnswerer(null), "");
  assert.doesNotThrow(() => rememberAnswerer(null, "张三"));
});

test("a cell's answer reads as who, which day and the basis", () => {
  assert.equal(stampLine(said("flow")), "张三 · 10-27 · 出处：10-27 会议");
  assert.equal(stampLine(said("flow", { basis: "" })), "张三 · 10-27");
  assert.equal(stampLine(said("flow", { basis: undefined })), "张三 · 10-27");
  assert.equal(stampLine(null), "");
});

test("the code's facts about a table: whether the identity fields are unique, and with what to show for it", () => {
  const unique = { fields: ["source_row", "submission_period"], distinct: 1921, duplicates: 0, examples: [] };
  assert.equal(uniqueLine(unique, 1921), "source_row + submission_period：1,921 行，1,921 种不同的组合，没有重复");
  assert.equal(uniqueLine({ ...unique, distinct: 1900, duplicates: 12, examples: ["7 · 2024Q4", "9 · 2024Q4"] }, 1921),
    "source_row + submission_period：1,921 行，1,900 种不同的组合，有 12 个组合出现了不止一次（例如 7 · 2024Q4；9 · 2024Q4）");
  assert.equal(uniqueLine(null, 40), "这张表上没有识别字段，看不出一行是不是唯一的");
});

test("the card says how many cells are still unclear, and what an empty card means", () => {
  assert.equal(blankLine(card()), "共 4 格，还有 4 格没说清");
  assert.equal(blankLine(card({ blank: 0 })), "共 4 格，都答过了");
  assert.equal(cardEmptyText({ ontology: { status: "auto_built_verified" } }), "这次运行没有可填的表。");
  assert.equal(cardEmptyText({ ontology: { status: "needs_review" } }), "本体还没通过核验，代码先不出口径卡。");
});

test("a thing to settle can be answered unless it is one that is settled by doing something else", () => {
  for (const kind of ["unlinked", "same_name", "merged", "found_elsewhere", "unstable", "check_finding", "data_gaps", "unanswered"]) {
    assert.equal(canAnswerItem({ id: `${kind}:x`, kind }), true, kind);
  }
  for (const kind of ["model_filter", "unjudged", "card_blank"]) assert.equal(canAnswerItem({ id: `${kind}:x`, kind }), false, kind);
  assert.equal(canAnswerItem({ kind: "data_gaps" }), false);   // an old service gives the items no id: there is nothing to answer by
});

test("the choices an item offers are the contract's, and the rest are answered in words only", () => {
  assert.deepEqual(itemChoices({ kind: "unlinked" }).map(([v, label]) => [v, label]), [["expected", "本来就没有对应，属正常"], ["incomplete", "数据没导全"]]);
  assert.deepEqual(itemChoices({ kind: "same_name" }), [["distinct", "是不同的对象"], ["same", "是同一个"]]);
  assert.deepEqual(itemChoices({ kind: "merged" }), ITEM_CHOICES.same_name);
  assert.deepEqual(itemChoices({ kind: "data_gaps" }), []);
});

test("an answer to an item carries what the person chose and wrote, and leaves out what they did not", () => {
  const form = { choice: "", text: "客户说另一个系统还有", basis: "" };
  assert.deepEqual(itemAnswer({ id: "data_gaps", kind: "data_gaps" }, form), { items: [{ id: "data_gaps", text: "客户说另一个系统还有" }], cells: [] });
  assert.deepEqual(itemAnswer({ id: "same_name:customer", kind: "same_name" }, { choice: "distinct", text: " ", basis: " 10-27 会议 " }),
    { items: [{ id: "same_name:customer", choice: "distinct", basis: "10-27 会议" }], cells: [] });
});

test("choosing that the data was not all imported also marks the other end's objects as only partly there, in the same request", () => {
  const item = { id: "unlinked:financial_row_corresponds_to_contract", kind: "unlinked", complete_id: "complete:contract_awards|award_id" };
  assert.deepEqual(itemAnswer(item, { choice: "incomplete", text: "合同授标只导了 FY25Q1 的", basis: "10-27 会议" }), {
    items: [{ id: item.id, choice: "incomplete", text: "合同授标只导了 FY25Q1 的", basis: "10-27 会议" }],
    cells: [{ id: "complete:contract_awards|award_id", value: "partial", note: "合同授标只导了 FY25Q1 的", basis: "10-27 会议" }] });
  assert.deepEqual(itemAnswer(item, { choice: "incomplete", text: "", basis: "" }).cells, [{ id: "complete:contract_awards|award_id", value: "partial", note: "" }]);
  assert.deepEqual(itemAnswer(item, { choice: "expected", text: "", basis: "" }).cells, []);   // a normal gap says nothing about the data
  assert.deepEqual(itemAnswer({ ...item, complete_id: undefined }, { choice: "incomplete", text: "", basis: "" }).cells, []);
});

test("an answer is not ready until it says something and says who", () => {
  const unlinked = { kind: "unlinked" }, gaps = { kind: "data_gaps" };
  assert.equal(itemProblem(unlinked, { choice: "expected", text: "", basis: "" }, "张三"), "");
  assert.equal(itemProblem(unlinked, { choice: "", text: "客户另有说法", basis: "" }, "张三"), "");
  assert.equal(itemProblem(unlinked, { choice: "", text: "", basis: "" }, "张三"), "选一项，或写下客户怎么答的");
  assert.equal(itemProblem(gaps, { choice: "", text: "", basis: "" }, "张三"), "写下客户怎么答的");
  assert.equal(itemProblem(gaps, { choice: "", text: "客户说另一个系统还有", basis: "" }, ""), "先填答复人");
});

test("changing an answer starts from the old one", () => {
  assert.deepEqual(itemForm(null), { choice: "", text: "", basis: "" });
  assert.deepEqual(itemForm({ choice: "incomplete", text: "只导了一季", basis: "会议" }), { choice: "incomplete", text: "只导了一季", basis: "会议" });
  assert.deepEqual(itemForm({ says: "", text: "有别的系统", by: "张三" }), { choice: "", text: "有别的系统", basis: "" });
});

test("what the client answered is listed with the question as it was asked then, the answer, who, which day and the basis", () => {
  const rows = answeredRows([
    { id: "unlinked:a", kind: "unlinked", ask: "现在的问法", answer: { choice: "incomplete", says: "数据没导全", text: "合同授标只导了 FY25Q1 的", by: "张三", basis: "10-27 会议", at, asked: "当时的问法" } },
    { id: "data_gaps", kind: "data_gaps", ask: "还缺什么数据？", answer: { says: "", text: "另一个系统还有", by: "李四", at } },
    { id: "same_name:c", kind: "same_name", ask: "这两个是同一个吗？", answer: { choice: "same", says: "是同一个", text: "", by: "王五", at, asked: "" } }]);
  assert.deepEqual(rows.map((r) => [r.id, r.asked, r.says, r.stamp]), [
    ["unlinked:a", "当时的问法", "数据没导全：合同授标只导了 FY25Q1 的", "张三 · 10-27 · 出处：10-27 会议"],
    ["data_gaps", "还缺什么数据？", "另一个系统还有", "李四 · 10-27"],   // with no asked text the question as it stands now is shown
    ["same_name:c", "这两个是同一个吗？", "是同一个", "王五 · 10-27"]]);
  assert.equal(rows[0].item.id, "unlinked:a");
  assert.deepEqual(answeredRows([]), []);
});

test("an answer given with the card says which table was used, how far its data goes, and which meanings of the client's it followed", () => {
  const evidence = { card: {
    tables: [{ source: "financial_rows", rows: 1921, through: "2024-12-31" }],
    lines: [{ id: AMOUNT, field: "gross_outlay_fyb_to_period_end", says: "期初到期末的累计值", by: "张三", basis: "10-27 会议", at },
      { id: DATE, field: "period_end_date", says: "业务发生的日期", by: "李四", basis: "", at }],
    incomplete: [{ type: "contract", label: "合同授标", note: "只导了 FY25Q1", by: "张三" }, { type: "vendor", label: "供应商", by: "张三" }] } };
  assert.deepEqual(cardEvidence({ evidence }), {
    data: "用的数据：financial_rows（1,921 行，数据到 2024-12-31）",
    lines: ["按口径：「gross_outlay_fyb_to_period_end」是期初到期末的累计值（张三 答复，出处：10-27 会议）", "按口径：「period_end_date」是业务发生的日期（李四 答复）"],
    incomplete: ["合同授标在数据里只有一部分：只导了 FY25Q1", "供应商在数据里只有一部分"] });
});

test("the data line says only what is known, and an answer without the card's evidence has nothing to add", () => {
  const evidence = { card: { tables: [{ source: "a", rows: 3 }, { source: "b", rows: 1200, through: "2024-12-31" }], lines: [], incomplete: [] } };
  assert.equal(cardEvidence({ evidence }).data, "用的数据：a（3 行）；b（1,200 行，数据到 2024-12-31）");
  assert.equal(cardEvidence({ evidence: { card: { tables: [], lines: [], incomplete: [] } } }).data, "");
  assert.equal(cardEvidence({ evidence: {} }), null);
  assert.equal(cardEvidence({}), null);
});

test("the minutes list the meanings the client agreed to by table, leaving out what was never answered or answered as unclear", () => {
  const filled = card();
  const t = filled.tables[0];
  t.grain.answer = { value: "event", says: saysOf("grain", "event"), by: "张三", basis: "10-27 会议", at };
  t.dates[0].answer = { value: "business", says: "业务发生的日期", by: "张三", at };
  t.dates[0].declared = { value: { from: "2024-10-01", to: "2024-12-31" }, says: "声明覆盖 2024-10-01 至 2024-12-31", by: "张三", at };
  t.amounts[0].answer = said("unsure", { says: "说不清" });
  filled.objects[0].answer = { value: "partial", says: "数据里只有一部分", by: "李四", basis: "邮件", at };
  assert.deepEqual(confirmedCells(filled), [{ source: "financial_rows", lines: [
    { name: "一行是什么", says: "一行是一次事件或一次修改（同一个东西有多行）", by: "张三", basis: "10-27 会议" },
    { name: "period_end_date", says: "业务发生的日期", by: "张三", basis: "" },
    { name: "period_end_date", says: "声明覆盖 2024-10-01 至 2024-12-31", by: "张三", basis: "" },
    { name: "财务支出行", says: "数据里只有一部分", by: "李四", basis: "邮件" }] }]);
  assert.deepEqual(confirmedCells(card()), []);
  assert.deepEqual(confirmedCells(null), []);
});
