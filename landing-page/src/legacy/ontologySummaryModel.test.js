import assert from "node:assert/strict";
import test from "node:test";

import { downloadName, runName, summaryMarkdown } from "./ontologySummaryModel.js";

const run = (extra = {}) => ({
  file: { name: "客户订单.xlsx", kind: "table" }, purpose: "哪些客户经常延期交货？",
  started_at: "2026-09-16T02:00:00+00:00",
  sources: [{ name: "客户", rows: 26, fields: 4 }, { name: "订单", rows: 35, fields: 6 }],
  ontology: { object_types: [{ key: "customer", label: "客户" }, { key: "order", label: "订单" }],
    relations: [{ key: "r1", from: "order", to: "customer", label: "属于" }], data_gaps: ["缺少实际交货日期"], ignored_fields: [], attempts: [{ errors: [] }], status: "auto_built_verified" },
  evaluation: { data_fit: { checks: [{ key: "fields_accounted", passed: true }, { key: "identity_consistent", passed: false }],
    identity_conflicts: [{ type: "customer", identity: "C010", field: "客户名称", values: ["甲", "乙"] }], identity_spellings: [], suspected_duplicates: [],
    missing_across_sources: [{ type: "customer", source: "客户", count: 1, examples: ["C099"] }], relations: [], orphans: [], source_groups: [["客户", "订单"]], fields: {} } },
  ...extra,
});

test("the summary is for the people in the room: what was read, what it says, what to check", () => {
  const md = summaryMarkdown(run({ confirmation: { confirmed_at: "2026-09-16T03:00:00+00:00", confirmed_by: "信息部 王工", decisions: { types: { customer: { verdict: "ok", label: "客户主体" } }, relations: { r1: { verdict: "ok" } }, added: ["售后工程师"] } } }));
  assert.match(md, /^# 客户订单 本体摸底会议纪要/);
  assert.match(md, /哪些客户经常延期交货？/);
  assert.match(md, /客户（26 行 4 列）/);
  assert.match(md, /订单 属于 客户/);
  assert.match(md, /C010/);
  assert.match(md, /C099/);
  assert.match(md, /缺少实际交货日期/);
  assert.match(md, /信息部 王工/);
  assert.match(md, /改名：客户 改成“客户主体”/);
  assert.doesNotMatch(md, /customer|auto_built_verified/);   // no internal names in front of a client
});

test("without a confirmation it says plainly that nobody has checked it yet", () => {
  const md = summaryMarkdown(run());
  assert.match(md, /还没有人逐项确认/);
  assert.doesNotMatch(md, /确认人/);
});

test("a long answer is cut to one screen, saying how many groups there are in all", () => {
  const groups = Array.from({ length: 30 }, (_, i) => [`客户${i}`, 30 - i]);
  const md = summaryMarkdown(run({ evaluation: { ...run().evaluation,
    acceptance: { total: 1, answered: 1, items: [{ question: "每个客户几张工单？", note: "", status: "answered", changed: null,
      answer: { groups, total_groups: 30, without_value: 0 }, path: "工单 → 客户" }] } } }));
  assert.equal(md.split("\n").filter((l) => /^- 客户\d+：/.test(l)).length, 10);
  assert.match(md, /另有 20 组，完整结果见“本体和评测”文件/);
});

test("fixed questions come with the meaning agreed on and whether they still hold", () => {
  const md = summaryMarkdown(run({ evaluation: { ...run().evaluation,
    acceptance: { total: 1, answered: 1, items: [{ question: "哪些客户经常延期交货？", note: "按订单号计数", status: "answered", changed: false,
      answer: { groups: [["甲", 2, 2], ["乙", 1, 6]], total_groups: 2, share: { field: "交货状态", equals: "延期交货" } }, path: "订单 → 客户" }] } } }));
  assert.match(md, /验收问题/);
  assert.match(md, /按订单号计数/);
  assert.match(md, /甲：2 \/ 2（100%）/);
  assert.match(md, /未通过：同一个对象在不同行里的信息不打架/);
  assert.match(md, /和上次一致/);
});

test("a fixed question says it is compared with the answer agreed to, and when the data is another version", () => {
  const item = (previous, changed) => ({ question: "每个客户几张工单？", note: "", status: "answered", changed, previous, answer: { total: 3 }, path: "工单" });
  const agreed = { status: "answered", answer: { total: 2 }, confirmed_at: "2026-10-01T08:00:00.000Z", confirmed_file: "sha-v1" };
  const md = (items, sha) => summaryMarkdown(run({ file: { name: "订单.csv", kind: "table", sha256: sha }, evaluation: { ...run().evaluation, acceptance: { total: items.length, answered: items.length, items } } }));
  assert.match(md([item(agreed, true)], "sha-v2"), /结果：能回答，和认可时不一样，数据已换版本/);
  assert.match(md([item(agreed, true)], "sha-v1"), /结果：能回答，和认可时不一样\n/);
  assert.match(md([item(agreed, false)], "sha-v2"), /结果：能回答，和认可时一致/);
  assert.match(md([item({ status: "answered", answer: { total: 2 } }, true)], "sha-v2"), /结果：能回答，和上次不一样\n/);
});

const ask = (ask, facts = [], fromModel = false) => ({ kind: "unlinked", ask, facts, from_model: fromModel, target: { tab: "check" } });

test("the first section is what to settle with the client, numbered, with each ask's facts beneath it and the model's words marked", () => {
  const md = summaryMarkdown(run(), [
    ask("财务支出行（financial_rows）1,921 行里有 1,308 行没连上“财务支出行 对应 合同授标”。是这些行本来就没有对应的合同授标，还是数据没导全？", ["例如 1425|F1", "例如 1425|F2"]),
    ask("模型指出 2 处数据缺口（下面逐条）。客户那边有没有能补上的数据？", ["缺少实际交货日期", "缺少客户等级"], true)]);
  assert.equal(md.split("\n## ")[1].split("\n")[0], "要和客户确认的事（2 件）");
  assert.match(md, /## 要和客户确认的事（2 件）\n\n1\. 财务支出行（financial_rows）1,921 行里有 1,308 行没连上.*数据没导全？\n {3}- 例如 1425\|F1\n {3}- 例如 1425\|F2\n2\. 模型指出 2 处数据缺口（下面逐条）。客户那边有没有能补上的数据？（模型的说法）\n {3}- 缺少实际交货日期\n {3}- 缺少客户等级\n/);
});

test("a list that could not be fetched is said so in one sentence, and an empty one says nothing was found", () => {
  assert.match(summaryMarkdown(run(), null), /## 要和客户确认的事\n\n这次没取到要确认的事清单：示例结果没有这份清单，本机建模服务没连上时也取不到。\n/);
  assert.match(summaryMarkdown(run()), /这次没取到要确认的事清单/);
  assert.match(summaryMarkdown(run(), []), /## 要和客户确认的事（0 件）\n\n代码没有找到要和客户确认的事。\n/);
});

test("the data check counts what passed and names each relation that does not reach every row", () => {
  const ontology = { ...run().ontology, object_types: [{ key: "financial", label: "财务支出行" }, { key: "contract", label: "合同授标" }, { key: "office", label: "合同办公室" }],
    relations: [{ key: "r1", from: "financial", to: "contract", label: "对应" }, { key: "r2", from: "contract", to: "office", label: "由…签" }] };
  const base = run().evaluation.data_fit;
  const md = summaryMarkdown(run({ ontology, evaluation: { data_fit: { ...base, checks: [{ key: "fields_accounted", passed: true }, { key: "relations_link", passed: true }],
    relations: [{ key: "r1", source: "financial_rows", rows: 1921, linked_rows: 613, empty_rows: 1308 }, { key: "r2", source: "contracts", rows: 365, linked_rows: 365, empty_rows: 0 }] } } }));
  assert.match(md, /2 \/ 2 项检查通过。/);
  assert.doesNotMatch(md, /全部通过/);
  assert.match(md, /- 关系“财务支出行 对应 合同授标”：financial_rows 1,921 行里 1,308 行没连上\n/);
  assert.doesNotMatch(md, /关系“合同授标 由…签 合同办公室”/);
  assert.match(summaryMarkdown(run()), /1 \/ 2 项检查通过。/);
});

test("a fixed question carries what to check about its answer and that it was worked again without a condition", () => {
  const item = { question: "累计付了多少钱？", note: "", status: "answered", changed: null, path: "财务支出行", answer: { total: 1444 },
    query: { start: "financial", where: [{ field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" }] },
    evidence: { filters: [{ field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", before: 1455, after: 1444, removed_measure: 4176392.96, not_in_question: true }] },
    edited: { dropped: [{ field: "award_agency_id", equals: "1425" }] } };
  const ontology = { ...run().ontology, object_types: [{ key: "financial", label: "财务支出行" }] };
  const md = summaryMarkdown(run({ ontology, evaluation: { ...run().evaluation, acceptance: { total: 1, answered: 1, items: [item] } } }));
  assert.match(md, /结果：能回答，要核对\n/);
  assert.match(md, /要核对：模型自己加了条件“awarding_subagency = BUREAU OF RECLAMATION”，问题里没提：筛掉 11 个财务支出行。\n/);
  assert.match(md, /去掉了条件“award_agency_id = 1425”后重算，没调模型\n/);
});

test("without a confirmation the last section says the objects and relations are the model's draft to go through in the meeting", () => {
  assert.match(summaryMarkdown(run()), /还没有人逐项确认：对象和关系都是模型提出的草稿，要在会上逐项确认。/);
});

test("the page and the files are named by the file's own name, never cut inside a word", () => {
  const named = (name, files) => ({ file: { name, kind: "table", ...(files ? { files: files.map((f) => ({ name: f })) } : {}) } });
  assert.equal(runName(named("客户订单.xlsx")), "客户订单");
  assert.equal(runName(named("contract_actions.csv、contracts.csv、vendors.csv", ["contract_actions.csv", "contracts.csv", "vendors.csv"])), "contract_actions 等 3 个文件");
  assert.equal(runName(named("contract_actions.csv、contracts.csv")), "contract_actions 等 2 个文件");   // runs saved before the file list was kept
  const long = "customer_orders_with_returns_and_regional_discounts_2026";
  for (const run of [named(`${long}.csv`), named(`${long}.csv、b.csv`)]) {
    const name = runName(run), cut = name.split("…")[0];
    assert.ok(name.length <= 40, name);
    assert.ok(name.includes("…") && long.startsWith(cut) && long[cut.length] === "_", name);
  }
  assert.equal(runName(named(`${long}.csv、b.csv`)).endsWith(" 等 2 个文件"), true);
  assert.equal(downloadName(named("客户订单.xlsx"), "纪要.md"), "客户订单-纪要.md");
  assert.equal(downloadName(named("客户订单.xlsx"), "本体和评测.json"), "客户订单-本体和评测.json");
});

test("a document has no rows for code to check, so its minutes carry no list of things to settle with the client", () => {
  const doc = run({ file: { name: "制度.md", kind: "document" }, sources: [{ name: "制度.md", paragraphs: 12, chars: 3400 }],
    evaluation: { document_fit: { checks: [{ key: "quotes_found", passed: true }] } } });
  for (const items of [null, [], [ask("不该出现", [])]]) {
    const md = summaryMarkdown(doc, items);
    assert.doesNotMatch(md, /要和客户确认的事|不该出现/);
    assert.match(md, /## 读了什么\n\n- 制度.md（12 段 3400 字）/);
  }
});

test("a fixed question whose basis is written down is said to be settled and no longer asked about", () => {
  const item = { question: "累计付了多少钱？", note: "只算垦务局自己签的合同", status: "answered", changed: null, path: "财务支出行", answer: { total: 1444 },
    query: { start: "financial", where: [{ field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" }] },
    evidence: { filters: [{ field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", before: 1455, after: 1444, not_in_question: true }] } };
  const ontology = { ...run().ontology, object_types: [{ key: "financial", label: "财务支出行" }] };
  const md = summaryMarkdown(run({ ontology, evaluation: { ...run().evaluation, acceptance: { total: 1, answered: 1, items: [item] } } }));
  assert.match(md, /口径：只算垦务局自己签的合同\n\n结果：能回答\n/);
  assert.match(md, /口径里已写明：模型加了条件“awarding_subagency = BUREAU OF RECLAMATION”（筛掉 11 个财务支出行）。\n/);
  assert.doesNotMatch(md, /要核对/);
});

const answeredAt = new Date(2026, 9, 27, 12, 0).toISOString();   // local noon: the same day in every time zone
const answered = [
  { id: "unlinked:a", kind: "unlinked", ask: "现在的问法", answer: { choice: "incomplete", says: "数据没导全", text: "合同授标只导了 FY25Q1 的", by: "张三", basis: "10-27 会议", at: answeredAt, asked: "财务支出行有 1,308 行没连上合同授标，是本来就没有，还是数据没导全？" } },
  { id: "data_gaps", kind: "data_gaps", ask: "客户那边有没有能补上的数据？", answer: { says: "", text: "另一个系统还有", by: "李四", at: answeredAt } }];
const filledCard = () => ({ cells: 3, blank: 1, objects: [{ id: "complete:financial_rows|source_row", label: "财务支出行", answer: { value: "partial", says: "数据里只有一部分", by: "李四", basis: "邮件", at: answeredAt } }],
  tables: [{ source: "financial_rows", rows: 1921, grain: { id: "grain:financial_rows", answer: { value: "event", says: "一行是一次事件或一次修改（同一个东西有多行）", by: "张三", at: answeredAt } },
    dates: [], amounts: [{ id: "amount:financial_rows.gross", field: "gross", answer: { value: "period_to_date", says: "期初到期末的累计值", by: "张三", basis: "10-27 会议", at: answeredAt } }] }] });

test("what the client answered goes in the minutes right after what was still to ask: the question as it was asked, the answer, who, which day and the basis", () => {
  const md = summaryMarkdown(run(), [ask("还没答的事", [])], { answered });
  assert.match(md, /## 要和客户确认的事（1 件）\n\n1\. 还没答的事\n\n## 客户已答复的事（2 件）\n\n/);
  assert.match(md, /1\. 财务支出行有 1,308 行没连上合同授标，是本来就没有，还是数据没导全？\n {3}- 答复：数据没导全：合同授标只导了 FY25Q1 的（张三，10-27，出处：10-27 会议）\n/);
  assert.match(md, /2\. 客户那边有没有能补上的数据？\n {3}- 答复：另一个系统还有（李四，10-27）\n\n## 读了什么/);
});

test("the meanings agreed with the client are listed by table as column, what it means, who and the basis", () => {
  const md = summaryMarkdown(run(), [], { answered: [], card: filledCard() });
  assert.match(md, /## 已和客户确认的口径\n\n### financial_rows\n\n- 一行是什么：一行是一次事件或一次修改（同一个东西有多行）（张三）\n- gross：期初到期末的累计值（张三，出处：10-27 会议）\n- 财务支出行：数据里只有一部分（李四，出处：邮件）\n\n## 读了什么/);
  assert.doesNotMatch(md, /## 客户已答复的事/);
});

test("when the client has answered everything the minutes say so, not that nothing was found", () => {
  const md = summaryMarkdown(run(), [], { answered });
  assert.match(md, /## 要和客户确认的事（0 件）\n\n要确认的事都已有客户答复（2 件，见下方）。\n\n## 客户已答复的事（2 件）/);
  assert.doesNotMatch(md, /代码没有找到要和客户确认的事/);
});

test("a cell's note follows what it says in the agreed meanings", () => {
  const card = filledCard();
  card.objects[0].answer = { value: "partial", says: "数据里只有一部分", note: "合同授标只导了 FY25Q1 签的", by: "测试人", basis: "10-27 会议", at: answeredAt };
  card.tables[0].amounts[0].answer = { ...card.tables[0].amounts[0].answer, note: "按季度末的值" };
  const md = summaryMarkdown(run(), [], { answered: [], card });
  assert.match(md, /- 财务支出行：数据里只有一部分，合同授标只导了 FY25Q1 签的（测试人，出处：10-27 会议）\n/);
  assert.match(md, /- gross：期初到期末的累计值，按季度末的值（张三，出处：10-27 会议）\n/);
  assert.match(md, /- 一行是什么：一行是一次事件或一次修改（同一个东西有多行）（张三）\n/);   // no note, nothing added
});

test("neither section is there when nothing was answered, whatever else was fetched", () => {
  for (const md of [summaryMarkdown(run(), []), summaryMarkdown(run(), [], {}), summaryMarkdown(run(), [], { answered: [], card: null }),
    summaryMarkdown(run(), [], { answered: [], card: { cells: 1, blank: 1, tables: [], objects: [{ id: "complete:a|b", label: "x", answer: null }] } })]) {
    assert.doesNotMatch(md, /客户已答复的事|已和客户确认的口径/);
  }
});

test("a document's minutes carry neither section", () => {
  const doc = run({ file: { name: "制度.md", kind: "document" }, sources: [{ name: "制度.md", paragraphs: 12, chars: 3400 }],
    evaluation: { document_fit: { checks: [{ key: "quotes_found", passed: true }] } } });
  assert.doesNotMatch(summaryMarkdown(doc, [], { answered, card: filledCard() }), /客户已答复的事|已和客户确认的口径/);
});

test("a period-to-date total grouped by its period has no whole in the minutes", () => {
  const md = summaryMarkdown(run({ evaluation: { ...run().evaluation,
    acceptance: { total: 1, answered: 1, items: [{ question: "每期累计付了多少钱？", note: "", status: "answered", changed: null, path: "财务支出行",
      query: { start: "customer", group_by: ["期末日期"], measure: { field: "累计支出", op: "sum" } },
      answer: { groups: [["2024-12-31", 144393033.61, 1213], ["2024-11-30", 24998153.82, 190]], total_groups: 2, without_value: 0 } }] } } }));
  assert.match(md, /- 2024-12-31：144,393,033.61（1213 个值）/);
  assert.match(md, /- 2024-11-30：24,998,153.82（190 个值）/);
  assert.doesNotMatch(md, /全部合计|169,391,187/);
});
