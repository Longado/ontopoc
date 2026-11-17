import assert from "node:assert/strict";
import test from "node:test";
import { STATUS_KEYS, statusOf } from "./statusModel.js";

test("the five words and their colours", () => {
  assert.deepEqual(STATUS_KEYS.map((k) => [k, statusOf(k).label, statusOf(k).tone]), [
    ["draft", "草稿", "grey"], ["pending", "待确认", "blue"], ["confirmed", "已确认", "green"], ["look", "需再看", "orange"], ["failed", "失败", "red"],
  ]);
});

test("every state the app already uses maps onto one of them", () => {
  const want = { proposed: "pending", checked: "pending", pending: "pending", confirmed: "confirmed", approved: "confirmed", needs_look: "look", stale: "look", rejected: "failed", failed: "failed", error: "failed", draft: "draft", model_draft: "draft", withdrawn: "draft", success: "confirmed", done: "confirmed" };
  for (const [raw, key] of Object.entries(want)) assert.equal(statusOf(raw).key, key, raw);
});

test("a model's draft is a draft even when its state says proposed", () => {
  assert.equal(statusOf("proposed", { modelDraft: true }).key, "draft");
});

test("a returned item keeps its own word as a hint, and an unknown state is a grey chip with its own text", () => {
  assert.equal(statusOf("rejected").hint, "已退回");
  const odd = statusOf("whatever");
  assert.deepEqual([odd.key, odd.label, odd.tone], ["draft", "whatever", "grey"]);
  assert.equal(statusOf(null).label, "草稿");
});

test("running work is blue and says so", () => {
  const r = statusOf("running");
  assert.deepEqual([r.label, r.tone], ["进行中", "blue"]);
});
