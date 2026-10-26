import assert from "node:assert/strict";
import test from "node:test";

import { ACCEPTANCE_LABELS, acceptItem, acceptanceSummary, canAccept, savedAcceptance } from "./ontologyAcceptanceModel.js";
import * as acceptance from "./ontologyAcceptanceModel.js";
import { localTime } from "./ontologyStudioModel.js";

const item = (over = {}) => ({ question: "每个客户有多少订单？", query: { start: "order" }, status: "answered", ...over });

test("a broken query is named apart from the other ways an answer can be missing", () => {
  assert.equal(ACCEPTANCE_LABELS.broken, "查询失效");
  assert.equal(ACCEPTANCE_LABELS.answered, "能回答");
});

test("only a question a person has seen answered can be fixed, and at most three", () => {
  const run = (items) => ({ saved_as: "x.json", evaluation: { acceptance: items ? { items } : undefined } });
  assert.equal(canAccept(run(), item()), "");
  assert.equal(canAccept(run(), item({ status: "no_data" })), "只能把已经答出来的问题存为验收问题");
  assert.equal(canAccept(run(), item({ query: null })), "只能把已经答出来的问题存为验收问题");
  assert.equal(canAccept({ evaluation: {} }, item()), "这是示例结果，上传自己的文件后可以存");
  assert.equal(canAccept(run([item(), item(), item()]), item({ question: "别的问题" })), "验收问题最多 3 道，先去掉一道");
  assert.equal(canAccept(run([item()]), item()), "这道已经是验收问题了");
});

test("the saved list is what gets sent back, with the note a person wrote", () => {
  const run = { evaluation: { acceptance: { items: [item({ note: "按订单号计数", answer: { total: 3 }, previous: null, changed: null })] } } };
  assert.deepEqual(savedAcceptance(run), [{ question: "每个客户有多少订单？", query: { start: "order" }, note: "按订单号计数", status: "answered", answer: { total: 3 } }]);
  assert.deepEqual(savedAcceptance({ evaluation: {} }), []);
});

test("the summary says how many are answered and how many moved since last time", () => {
  const acceptance = { total: 3, answered: 2, items: [item({ changed: true }), item({ changed: false }), item({ status: "broken", changed: true })] };
  assert.equal(acceptanceSummary(acceptance), "3 道里能答 2 道，2 道和上次不一样");
  assert.equal(acceptanceSummary({ total: 1, answered: 1, items: [item({ changed: null })] }), "1 道里能答 1 道，第一次执行");
});

const bindingSnapshot = {
  types: [{ key: "order", label: "订单", populated_from: [{ source: "订单", identity: { id: "订单编号" } }] }],
  relations: [{ key: "order_customer", from: "order", to: "customer", source: "订单", from_identity: { id: "订单编号" }, to_identity: { id: "客户编号" } }],
};

test("editing another acceptance question retains the original binding and last checked result", () => {
  const existing = item({ query: { start: "order", via: ["order_customer"] }, note: "按订单号计数", snapshot: bindingSnapshot,
    answer: { total: 3 }, path: "订单 → 客户", changed: false, previous: { status: "answered", answer: { total: 2 } } });
  const saved = savedAcceptance({ evaluation: { acceptance: { items: [existing] } } });
  const added = acceptItem(saved, item({ question: "有多少订单？", answer: { total: 9 }, path: "订单", snapshot: { types: [] } }), " 新问题 ");
  assert.deepEqual(added[0], { question: existing.question, query: existing.query, note: existing.note,
    snapshot: bindingSnapshot, answer: { total: 3 }, status: "answered", path: "订单 → 客户" });
  assert.deepEqual(added[1], { question: "有多少订单？", query: { start: "order" }, note: "新问题" });
});

test("removing another question keeps a broken query's original identity evidence and checked status", () => {
  const broken = item({ query: { start: "order", via: ["order_customer"] }, note: "原来的客户编号绑定", snapshot: bindingSnapshot,
    status: "broken", answer: null, path: "订单 → 客户", reason: "编号绑定已变", changed: true });
  const saved = savedAcceptance({ evaluation: { acceptance: { items: [broken, item({ question: "去掉这道" })] } } })
    .filter((s) => s.question !== "去掉这道");
  assert.deepEqual(saved, [{ question: broken.question, query: broken.query, note: broken.note,
    snapshot: bindingSnapshot, answer: null, status: "broken", path: "订单 → 客户" }]);
});

// The service records what the person agreed to; an item compared with it says so in previous.
const agreed = { status: "answered", answer: { total: 2 }, confirmed_at: "2026-10-01T08:00:00.000Z", confirmed_file: "sha-v1" };
const here = (sha) => ({ file: { sha256: sha } });

test("without a confirmation the page still compares with the last run, in the old words", () => {
  const last = { status: "answered", answer: { total: 2 } };
  assert.equal(acceptance.changeLabel(item({ changed: false, previous: last }), here("sha-v1")), "和上次一致");
  assert.equal(acceptance.changeLabel(item({ changed: true, previous: last }), here("sha-v1")), "和上次不一样");
  assert.equal(acceptance.changeLabel(item({ changed: null, previous: null }), here("sha-v1")), "");
  assert.equal(acceptance.previousTitle(item({ changed: true, previous: last })), "上次的答案");
});

test("with a confirmation it says it is compared with what the person agreed to, and when the data is another version", () => {
  assert.equal(acceptance.changeLabel(item({ changed: false, previous: agreed }), here("sha-v1")), "和确认时一致");
  assert.equal(acceptance.changeLabel(item({ changed: true, previous: agreed }), here("sha-v1")), "和确认时不一样");
  assert.equal(acceptance.changeLabel(item({ changed: true, previous: agreed }), here("sha-v2")), "和确认时不一样，数据已换版本");
  assert.equal(acceptance.changeLabel(item({ changed: false, previous: agreed }), here("sha-v2")), "和确认时一致");
  assert.equal(acceptance.previousTitle(item({ changed: true, previous: agreed })), `确认时的答案（${localTime(agreed.confirmed_at)}）`);
});

test("the summary counts against the confirmation only when every compared question has one", () => {
  const withAgreement = (changed) => item({ changed, previous: agreed });
  assert.equal(acceptanceSummary({ total: 2, answered: 2, items: [withAgreement(true), withAgreement(false)] }), "2 道里能答 2 道，1 道和确认时不一样");
  assert.equal(acceptanceSummary({ total: 2, answered: 2, items: [withAgreement(true), item({ changed: true, previous: { status: "answered" } })] }), "2 道里能答 2 道，2 道和上次不一样");
  assert.equal(acceptanceSummary({ total: 2, answered: 2, items: [withAgreement(true), item({ changed: null })] }), "2 道里能答 2 道，1 道和确认时不一样");
  assert.equal(acceptanceSummary({ total: 1, answered: 1, items: [item({ changed: null })] }), "1 道里能答 1 道，第一次执行");
});

test("what the person agreed to is held by the service and is not sent back with the list", () => {
  const run = { evaluation: { acceptance: { items: [item({ answer: { total: 3 }, confirmed: { status: "answered", answer: { total: 2 }, at: agreed.confirmed_at, file: "sha-v1" }, previous: agreed, changed: true })] } } };
  const [saved] = savedAcceptance(run);
  assert.equal(Object.hasOwn(saved, "confirmed"), false);
  assert.equal(Object.hasOwn(saved, "previous"), false);
});
