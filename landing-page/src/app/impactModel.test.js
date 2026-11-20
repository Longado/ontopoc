import assert from "node:assert/strict";
import test from "node:test";

import { changeCell, figureCell, impactMatters, impactView, receiptMarkdown, summaryMarkdown, summaryView } from "./impactModel.js";
import { setLocale } from "./i18n/index.js";

const valid = { board: { id: 1, name: "订单概览" }, card: { id: "valid_count", title: "有效订单数" },
  now: { status: "ok", value: 107, text: "107", grey: false, why: null }, after: { status: "ok", value: 61, text: "61", grey: false, why: null }, change: { kind: "number", delta: -46 } };
const amount = { board: { id: 1, name: "订单概览" }, card: { id: "valid_amount", title: "有效订单金额" },
  now: { status: "ok", value: 119810, text: "119,810", grey: false, why: null }, after: { status: "ok", value: 70210.5, text: "70,210.5", grey: false, why: null }, change: { kind: "number", delta: -49599.5 } };
const gone = { board: { id: 2, name: "财务|周报" }, card: { id: "all", title: "全部订单金额" },
  now: { status: "ok", value: 162960, text: "162,960", grey: false, why: null }, after: { status: "refused", value: null, text: "没有“金额”这个字段", grey: false, why: null }, change: { kind: "refuses", why: "没有“金额”这个字段" } };
const still = { board: { id: 1, name: "订单概览" }, card: { id: "by_status", title: "按状态" },
  now: { status: "ok", value: 107, text: "Paid 46、Shipped 30", grey: false, why: null }, after: { status: "ok", value: 107, text: "Paid 46、Shipped 30", grey: false, why: null }, change: { kind: "same" } };
const impact = { refused: null, cards: [valid, amount, gone, still], answers: { mine: [{ id: 4, question: "有效订单有多少" }], others: 2 }, checked: { boards: 2, cards: 9, capped: false, left: 0 } };

test("a card's two sides and its change, as the table shows them (WP-B)", () => {
  setLocale("zh");
  assert.deepEqual(figureCell(valid.now), { text: "107", note: "", grey: false, refused: false });
  assert.deepEqual(figureCell(gone.after), { text: "拒答", note: "没有“金额”这个字段", grey: false, refused: true });
  assert.deepEqual(figureCell({ status: "ok", value: 61, text: "61", grey: true, why: "视图「有效订单」：已经提出，还没有另一位确认" }),
    { text: "61", note: "视图「有效订单」：已经提出，还没有另一位确认", grey: true, refused: false });
  assert.equal(figureCell(still.now).note, "Paid 46、Shipped 30");   // a chart's groups beside its total
  assert.deepEqual(changeCell(valid.change), { text: "−46", level: "down" });
  assert.deepEqual(changeCell({ kind: "number", delta: 1200.5 }), { text: "+1,200.5", level: "up" });
  assert.deepEqual(changeCell(gone.change), { text: "变成拒答", level: "refuses" });
  assert.equal(changeCell({ kind: "grey" }).text, "变灰，还在等确认");
  assert.equal(changeCell({ kind: "same" }).text, "不变");
});

test("the table, the sentence over it, and the answers that used it: only the person's own by their question", () => {
  setLocale("zh");
  const view = impactView(impact);
  assert.deepEqual(view.rows.map((r) => [r.board, r.card, r.now.text, r.after.text, r.change.text]), [
    ["订单概览", "有效订单数", "107", "61", "−46"], ["订单概览", "有效订单金额", "119,810", "70,210.5", "−49,599.5"], ["财务|周报", "全部订单金额", "162,960", "拒答", "变成拒答"], ["订单概览", "按状态", "107", "107", "不变"]]);
  assert.equal(view.sentence, "3 张卡片的数会变（在 2 个看板上）");
  assert.equal(view.answers, "已存的回答里，你的 1 个、别人的 2 个用到了它。你的：“有效订单有多少”");
  assert.equal(view.capped, "");
  assert.equal(impactMatters(impact), true);
  const quiet = { ...impact, cards: [still], answers: { mine: [], others: 0 } };
  assert.equal(impactView(quiet).sentence, "看板上的数都不会变（看了你能打开的 2 个看板）");
  assert.equal(impactView({ ...quiet, cards: [] }).sentence, "看板上的数都不会变（看了你能打开的 2 个看板）");
  assert.equal(impactMatters(quiet), false);
  assert.equal(impactView({ ...impact, checked: { boards: 5, cards: 30, capped: true, left: 12 } }).capped, "只算了前 30 张卡片，还有 12 张没有算");
  const refused = impactView({ refused: "你提出或改过这一项，要另一位建设者确认", cards: [] });
  assert.equal(refused.sentence, "现在确认会被拒绝：你提出或改过这一项，要另一位建设者确认");
  assert.equal(impactMatters({ refused: "x", cards: [] }), true);
  setLocale("en");
  assert.equal(impactView(impact).sentence, "3 cards would show a different number (on 2 boards)");
  assert.equal(impactView(quiet).sentence, "No number on a board would change (2 boards you can open were checked)");
  assert.equal(changeCell(gone.change).text, "Refuses");
  setLocale("zh");
});

test("the receipt to copy: what changed, who proposed and confirmed it on which version, the numbers from and to, what now refuses", () => {
  setLocale("zh");
  const receipt = {
    at: "2026-11-20T10:00:00+00:00",
    items: [{ element: "objview:有效订单", kind: "view", title: "有效订单（订单的视图）", before: "status_code 不是 0、4、5", after: "status_code 不是 0、1、4、5",
      proposed_by: "demo-admin", confirmed_by: "Demo builder", confirmed_at: "2026-11-20T09:59:00+00:00", on: { orders: 1 }, on_before: { orders: 1 }, evidence: "dataset:orders@v1" }],
    cards: [valid, gone, still], answers: { mine: [], others: 1 }, checked: { boards: 1, cards: 4, capped: false, left: 0 },
  };
  const md = receiptMarkdown(receipt);
  assert.match(md, /^## 变更回执\n/);
  assert.match(md, /- 视图「有效订单（订单的视图）」\n  - 之前：status_code 不是 0、4、5\n  - 之后：status_code 不是 0、1、4、5\n/);
  assert.match(md, /  - 提出：demo-admin；确认：Demo builder（/);
  assert.match(md, /  - 数据版本：orders 第 1 版\n/);
  assert.match(md, /\| 订单概览 \| 有效订单数 \| 107 \| 61 \| −46 \|/);
  assert.match(md, /\| 财务\\\|周报 \| 全部订单金额 \| 162,960 \| 拒答 \| 变成拒答 \|/);   // a | in a name does not break the table
  assert.doesNotMatch(md, /按状态/);   // a card that does not move is not on the receipt
  assert.match(md, /### 变成拒答的卡片\n- 财务\|周报 · 全部订单金额：没有“金额”这个字段/);
  assert.match(md, /别人的 1 个用到了它/);
  const first = receiptMarkdown({ ...receipt, items: [{ ...receipt.items[0], before: null, on_before: null }], cards: [] });
  assert.match(first, /  - 之前：第一次确认\n/);
  assert.match(first, /看板上没有数因此改变。/);
  setLocale("en");
  assert.match(receiptMarkdown(receipt), /^## Change receipt\n/);
  setLocale("zh");
});

test("the workspace summary: definitions by state, checks, rows covered, who confirmed what on which version", () => {
  setLocale("zh");
  const summary = { at: "2026-11-20T10:00:00+00:00", definitions: { type: { confirmed: 1, checked: 1 }, meaning: { confirmed: 1 }, view: { needs_look: 1 } }, needs_look: { 定义改了: 1 },
    checks: { passed: 2, failed: 0, error: 0, skipped: 0 }, rows: { covered: 120, total: 170, uncovered: 50, datasets: 2, datasets_covered: 1 },
    confirmations: [{ element: "objtype:order", kind: "type", title: "Order", by: "Demo builder", at: "2026-11-20T09:00:00+00:00", on: { orders: 1 } }] };
  const view = summaryView(summary);
  assert.deepEqual(view.kinds, [{ kind: "对象类型", states: "已确认 1、待确认 1" }, { kind: "取值含义", states: "已确认 1" }, { kind: "视图", states: "需要再看 1" }]);
  assert.equal(view.rows, "已确认的类型读了 120 / 170 行（1 / 2 个数据集）");
  assert.equal(view.checks, "确认时的检查：通过 2、没通过 0、出错 0");
  assert.equal(view.needs, "需要再看：定义改了 1");
  assert.equal(summaryView({ ...summary, rows: null }).rows, "你受行规则或列的限制，这里不显示全部数据的行数");
  const md = summaryMarkdown(summary);
  assert.match(md, /^## 工作区回执\n/);
  assert.match(md, /\| 对象类型「Order」 \| Demo builder \| .* \| orders 第 1 版 \|/);
});

test("new data since the last confirmation is said apart from the numbers, in the preview and on the receipt", () => {
  setLocale("zh");
  const moved = [{ name: "订单", from: 1, to: 2 }];
  assert.equal(impactView({ ...impact, data_moved: moved }).dataMoved, "上次确认之后，订单 从第 1 版换成了第 2 版。“现在”和“确认后”都按现在的数据算，表里只有这次改动带来的变化。");
  assert.equal(impactView(impact).dataMoved, "");
  const receipt = { at: "2026-11-20T10:00:00+00:00", cards: [valid], answers: { mine: [], others: 0 }, checked: { boards: 1, cards: 1, capped: false, left: 0 },
    items: [{ element: "objview:有效订单", kind: "view", title: "有效订单", before: "a", after: "b", proposed_by: "Ann", confirmed_by: "Bob", confirmed_at: "2026-11-20T09:59:00+00:00",
      on: { 订单: 2 }, on_before: { 订单: 1 }, evidence: null, data_moved: moved }] };
  const md = receiptMarkdown(receipt);
  assert.match(md, /  - 两次确认之间数据有了新版本：订单 第 1 版 → 第 2 版。这部分数的变化不是这次确认带来的，下面的数都按现在的数据算\n/);
  assert.doesNotMatch(md, /上次确认在/);
  setLocale("en");
  assert.equal(impactView({ ...impact, data_moved: moved }).dataMoved, "Since the last confirmation, 订单 went from version 1 to version 2. \"Now\" and \"after\" are both on the current data, so the table shows only what this change does.");
  setLocale("zh");
});
