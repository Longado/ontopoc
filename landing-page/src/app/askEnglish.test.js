import assert from "node:assert/strict";
import test from "node:test";

import { TOOL_GROUPS, connectConfig, endText, firstSentence, groupTools, scopeWord, skillText, toolInfo, tokenPlaceholder, tokenState } from "./agentModel.js";
import { componentKinds, draftProblem, emptyComponent, emptyDraft, expiryText, refreshOptions, refreshText, scopeLabel, scopeText } from "./boardModel.js";
import { timeText } from "./format.js";
import { getLocale, setLocale } from "./i18n/index.js";
import { answerView, criteriaLine, historyView, queryExample, rangeNotes, readText, scopeText as askScope, staleHeading, staleLines, standingText, statusText, timeWarning, timeWord } from "./qaModel.js";

setLocale("en");   // the default; these tests pin the English copy of Ask, Boards, Notifications and AI tool access

const types = [{ id: "order", name: "orders" }];

test("a time in the product's own format follows the language", () => {
  assert.equal(timeText("2026-11-13T14:05:00"), "Nov 13, 2026, 2:05 PM");
  assert.equal(timeText("nope"), "");
});

test("time words are found in English questions as well as Chinese ones", () => {
  for (const [q, w] of [["Cancelled orders this month", "this month"], ["revenue LAST MONTH", "last month"], ["sales this year", "this year"], ["orders today", "today"], ["orders yesterday", "yesterday"], ["signups this week", "this week"], ["customers in the last 30 days", "last 30 days"], ["orders over the last 3 months", "last 3 months"], ["本月已取消订单有多少", "本月"], ["最近30天下单客户", "最近30天"]]) {
    assert.equal(timeWord(q), w, q);
  }
  assert.equal(timeWord("How many cancelled orders are there"), null);
  assert.equal(timeWord("Which customer has the most orders"), null);
  assert.equal(timeWord("Which customer is the most loyal"), null);
});

test("the unused-time-word warning is one English sentence", () => {
  const record = { question: "Cancelled orders this month", status: "answered", query_text: "SELECT count(o) FROM (o:orders) WHERE o.status = 'cancelled'", query: { filters: [] } };
  assert.equal(timeWarning(record), "“this month” was not applied — this number covers all time");
  assert.equal(timeWarning({ ...record, query_text: "SELECT count(o) FROM (o:orders) WHERE o.order_date >= '2026-11-01'" }), null);
});

test("answers read in English", () => {
  assert.deepEqual(answerView({ answer: { total: 16 }, types, status: "answered" }), { big: "16 orders", note: "", table: null });
  assert.equal(answerView({ answer: { total: 160, measure: { field: "amount", op: "sum", value: 1115, counted: 160, skipped: 0 } }, types }).big, "amount total 1,115");
  assert.equal(answerView({ answer: { total: 160, measure: { field: "amount", op: "avg", value: 7, counted: 150, skipped: 10 } }, types }).note, "150 values counted, 10 could not be read");
  assert.equal(answerView({ answer: { total: 160, matched: 16, share: { field: "status", equals: "2" } }, types }).note, "orders where status = 2: 10%");
  const grouped = answerView({ answer: { groups: [["East", 3], ["North", 1]], total_groups: 2, without_value: 0 }, types });
  assert.deepEqual([grouped.big, grouped.table.head], ["2 groups", ["Group", "Count"]]);
  assert.equal(answerView({ status: "no_data", reason: "r", types }).big, "No data");
  assert.deepEqual(["answered", "no_data", "refused"].map(statusText), ["Answered", "No data", "Not answered"]);
});

test("the basis, history and caliber lines read in English", () => {
  assert.deepEqual(readText({ orders: 1, customers: 2 }), ["orders v1", "customers v2"]);
  assert.equal(askScope({ types: [1, 2, 3] }), "Scope: 3 confirmed object types");
  assert.equal(askScope({ types: [1] }), "Scope: 1 confirmed object type");
  assert.equal(criteriaLine({ query_text: "SELECT count(o) FROM (o:orders) WHERE o.status = 'cancelled'" }, "Nov 16, 2026, 8:00 AM"), "Per confirmed definitions: orders.status = cancelled, data as of Nov 16, 2026, 8:00 AM");
  assert.equal(criteriaLine({ query_text: "SELECT count(o) FROM (o:orders)" }, ""), "Per confirmed definitions: all orders");
  assert.deepEqual(historyView({ id: 3, question: "q", status: "answered" }, "T"), { id: 3, question: "q", meta: "T Answered" });
  assert.equal(queryExample({ types: [{ name: "orders" }] }), "SELECT count(x) AS total\nFROM (x:orders)");
  assert.equal(standingText({ state: "proposed" }), "Proposed by the model; nobody has confirmed it yet");
  assert.equal(standingText({ state: "checked", proposed_by: "Ann" }), "Proposed by Ann; a second person has not confirmed it yet");
});

test("a saved answer that is out of date says so in English", () => {
  assert.deepEqual(staleLines({ stale: [{ dataset: "orders", read: 1, now: 2 }], changed: [{ name: "orders", state: "confirmed" }, { name: "gone", state: null }] }),
    ["orders has a newer version: this answer read version 1, now version 2", "orders was confirmed again after the answer", "gone no longer exists"]);
  assert.equal(staleHeading({ changed: [{ name: "x", state: "confirmed" }], stale: [] }), "The definitions behind this answer were confirmed again after it; below is the answer as it was then");
  assert.equal(staleHeading({ changed: [], stale: [{ dataset: "x", read: 1, now: 2 }] }), "The data has a newer version, so this answer is out of date");
});

test("a range says what it could not read, in English", () => {
  const record = { evidence: { filters: [{ range: "amount > 1000", unreadable: 2, unreadable_examples: ["n/a", "tbd"] }] } };
  assert.deepEqual(rangeNotes(record), ["amount > 1000: 2 values could not be read as numbers or dates and were not counted (e.g. n/a, tbd)"]);
  assert.deepEqual(rangeNotes({ answer: { unreadable: { field: "date", count: 3 } } }), ["date: 3 values could not be read as dates and were not placed in a month or year"]);
});

test("boards say who may open them, when they end and how often they read", () => {
  assert.deepEqual(["private", "named", "everyone"].map(scopeLabel), ["Only me", "Named people", "Everyone signed in"]);
  assert.equal(scopeText({ scope: "named", visible_names: ["Vera"] }), "Named people: Vera");
  assert.equal(scopeText({ scope: "named" }), "Named people");
  assert.equal(expiryText({ expires_at: null }), "Never expires");
  assert.equal(expiryText({ expires_at: "2026-12-01", expired: false }), "Until 2026-12-01");
  assert.equal(expiryText({ expires_at: "2026-11-01", expired: true }), "Expired 2026-11-01; only the owner and admins can open it");
  assert.equal(refreshText(0), "Only when opened");
  assert.equal(refreshText(300), "Every 5 minutes");
  assert.equal(refreshText(45), "Every 45 seconds");
  assert.equal(refreshOptions().length, 5);
  assert.equal(componentKinds()[0][1], "Metric card");
});

test("the board form says what is missing in English", () => {
  assert.equal(draftProblem(emptyDraft()), "Name the board");
  assert.equal(draftProblem({ ...emptyDraft(), name: "x" }), "Add at least one component");
  assert.equal(draftProblem({ ...emptyDraft(), name: "x", components: [emptyComponent("order", 1)] }), "Component 1 needs a title");
  const q = { ...emptyDraft(), name: "x", components: [{ ...emptyComponent("order", 1), kind: "query", title: "t", text: "SELECT count(o) FROM (o:orders) WHERE o.c = $who" }] };
  assert.equal(draftProblem(q), "The query uses $who; add it under Parameters with a default value");
  assert.equal(draftProblem({ ...q, params: [{ name: "who", label: "", default: "" }] }), "Parameter $who needs a default value");
});

test("AI tool access reads in English", () => {
  assert.equal(skillText({ types: 6, relations: 5, views: 1, derived: 1 }), "Object types: 6 · Relations: 5 · Views: 1 · Derived properties: 1 — all confirmed, no data rows");
  assert.deepEqual([{ scope: "read" }, { scope: "all" }].map(scopeWord), ["Read-only", "All"]);
  assert.deepEqual([{ expires_at: null }, { expires_at: "2027-02-12T03:00:00+00:00" }, { expires_at: "2026-01-01T00:00:00+00:00", expired: true }].map(endText), ["Never expires", "2027-02-12", "Expired"]);
  assert.deepEqual([{ revoked: true }, { last_used_at: "x" }, { last_used_at: null }, { expired: true }].map(tokenState), ["Revoked", "In use", "Not used yet", "Expired"]);
  assert.equal(firstSentence("Reads the definitions. Only confirmed ones."), "Reads the definitions");
  assert.equal(toolInfo("ontopoc_query").line, "Compute one number straight from an ontology query: no model, fast");
  assert.equal(toolInfo("unknown_tool").known, false);
  const groups = groupTools([{ name: "ask" }, { name: "describe_definitions" }, { name: "build_ontology" }]);
  assert.deepEqual(groups.map((g) => g.group), ["read", "ask", "model"]);
  assert.deepEqual(groups.map((g) => g.label), ["Read", "Ask", "Build"]);
  assert.ok(groups[0].hint.length > 0 && TOOL_GROUPS.includes("export"));
  assert.match(tokenPlaceholder(), /token/);
  assert.equal(JSON.parse(connectConfig({ command: { python: "p", module: "m" }, origin: "o", token: "" })).mcpServers.ontopoc.env.ONTOPOC_TOKEN, tokenPlaceholder());
});

test("the suite leaves the language as English", () => {
  assert.equal(getLocale(), "en");
});
