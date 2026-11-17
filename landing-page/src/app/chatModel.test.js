import assert from "node:assert/strict";
import test from "node:test";

import { groupByDay, isThinking, newTurn, savedTurn, sendsOn, settle, suggestions, threadTitle } from "./chatModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("en");
const at = (y, m, d, h = 10) => new Date(y, m - 1, d, h).toISOString();

test("saved questions are grouped by local day, today and yesterday named, newest first", () => {
  const now = new Date(2026, 10, 16, 15);
  const history = [
    { id: 1, question: "a", asked_at: at(2026, 11, 14) },
    { id: 2, question: "b", asked_at: at(2026, 11, 16, 9) },
    { id: 3, question: "c", asked_at: at(2026, 11, 15, 22) },
    { id: 4, question: "d", asked_at: at(2026, 11, 16, 14) },
    { id: 5, question: "e", asked_at: "not a time" },
  ];
  const groups = groupByDay(history, now);
  assert.deepEqual(groups.map((g) => [g.key, g.items.map((h) => h.id)]), [["today", [4, 2]], ["yesterday", [3]], ["2026-11-14", [1]], ["undated", [5]]]);
  assert.deepEqual(groupByDay([], now), []);
  assert.deepEqual(groupByDay(undefined, now), []);
});

test("a day group at the start of a month still finds yesterday", () => {
  const groups = groupByDay([{ id: 1, asked_at: at(2026, 10, 31) }], new Date(2026, 10, 1, 8));
  assert.equal(groups[0].key, "yesterday");
});

test("a turn waits, then settles with its record or its error, without touching the others", () => {
  const a = newTurn("ask", "How many orders?");
  const b = savedTurn(7);
  assert.equal(a.status, "thinking");
  assert.notEqual(a.id, newTurn("ask", "x").id);
  assert.equal(isThinking([a, b]), true);
  const done = settle([a, b], a.id, { status: "done", record: { question: "How many orders?" } });
  assert.deepEqual(done.map((t) => t.status), ["done", "thinking"]);
  assert.equal(isThinking(settle(done, b.id, { status: "error", error: "x" })), false);
  assert.equal(b.savedId, 7);
});

test("Enter sends, Shift+Enter breaks the line, an input method that is composing never sends; the query box runs on Ctrl or Command + Enter", () => {
  assert.equal(sendsOn({ key: "Enter" }), true);
  assert.equal(sendsOn({ key: "Enter", shiftKey: true }), false);
  assert.equal(sendsOn({ key: "Enter", isComposing: true }), false);
  assert.equal(sendsOn({ key: "Enter", keyCode: 229 }), false);
  assert.equal(sendsOn({ key: "a" }), false);
  assert.equal(sendsOn({ key: "Enter" }, "query"), false);
  assert.equal(sendsOn({ key: "Enter", metaKey: true }, "query"), true);
  assert.equal(sendsOn({ key: "Enter", ctrlKey: true }, "query"), true);
});

test("suggestions are the home page's examples for what is in scope", () => {
  const scope = { types: [{ id: "order", name: "Order" }, { id: "customer", name: "Customer" }] };
  assert.equal(suggestions(scope).length, 2);
  assert.deepEqual(suggestions(null), []);
  assert.equal(suggestions({ types: [{ name: "A" }, { name: "B" }, { name: "C" }, { name: "D" }] }, [], 2).length, 2);
});

test("the thread's title is its first question, cut to fit", () => {
  assert.equal(threadTitle([]), "");
  assert.equal(threadTitle([newTurn("ask", "  How many   orders? ")]), "How many orders?");
  assert.equal(threadTitle([{ ...savedTurn(1), record: { question: "x".repeat(80) } }], 10), "xxxxxxxxx…");
});
