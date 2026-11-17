import assert from "node:assert/strict";
import test from "node:test";
import { allowedMode, commandChoices, datasetSpec, defaultSelected, isNoModel, modesFor, moveDraft, parseCommand, planCard, privacyKey, proposalCard, proposePayload, scopeKind, stashDraft, takeDraft } from "./assistantModel.js";

const store = () => {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), size: () => m.size };
};

test("a builder sees all four modes and a viewer sees Ask only", () => {
  assert.deepEqual(modesFor(true), ["ask", "query", "model", "pipeline"]);
  assert.deepEqual(modesFor(false), ["ask"]);
  assert.equal(allowedMode("pipeline", false), "ask");
  assert.equal(allowedMode("pipeline", true), "pipeline");
  assert.equal(allowedMode("nonsense", true), "ask");
});

test("each mode has its own scope kind and privacy line", () => {
  assert.deepEqual(["ask", "query", "model", "pipeline"].map(scopeKind), ["types", "types", "datasets", "target"]);
  assert.equal(privacyKey("model"), "ask.assistant.privacy.model");
  assert.equal(privacyKey("weird"), "ask.assistant.privacy.ask");
});

test("slash commands switch the mode and keep the rest of the line", () => {
  assert.deepEqual(parseCommand("/pipeline total by customer", true), { mode: "pipeline", text: "total by customer" });
  assert.deepEqual(parseCommand("/model", true), { mode: "model", text: "" });
  assert.deepEqual(parseCommand("  /Query  SELECT 1\nFROM x", true), { mode: "query", text: "SELECT 1\nFROM x" });
  assert.deepEqual(parseCommand("/ask how many", true), { mode: "ask", text: "how many" });
  assert.equal(parseCommand("/models x", true), null);
  assert.equal(parseCommand("how about /model", true), null);
  assert.equal(parseCommand("/model x", false), null);   // a viewer's slash is just text
  assert.deepEqual(parseCommand("/ask hi", false), { mode: "ask", text: "hi" });
});

test("typing a slash offers the commands this person may use", () => {
  assert.deepEqual(commandChoices("/", true), ["ask", "query", "model", "pipeline"]);
  assert.deepEqual(commandChoices("/p", true), ["pipeline"]);
  assert.deepEqual(commandChoices("/p", false), []);
  assert.deepEqual(commandChoices("/", false), ["ask"]);
  assert.deepEqual(commandChoices("/pipeline x", true), []);
  assert.deepEqual(commandChoices("hello", true), []);
});

test("a missing model is recognised from the server's words in either language", () => {
  assert.equal(isNoModel("This server has no model credentials, so the AI assistant is not available"), true);
  assert.equal(isNoModel("本机服务没有模型凭据，AI 助手用不了"), true);
  assert.equal(isNoModel("Dataset not found"), false);
});

const draft = (over = {}) => ({
  label: "Drafted by AI", basis: "filter then sum",
  steps: [
    { id: "ai1", summary: "Drop cancelled", step: { type: "transform" }, rows_in: [160], rows_out: 144, operators: [{ text: "status is not cancelled" }] },
    { id: "ai2", summary: "Total by customer", step: { type: "transform" }, rows_in: [144], rows_out: 38, to_call: 5 },
  ],
  cites: [{ text: "Meaning cancelled is code 2 (confirmed, Bob)" }],
  questions: [], check: { ok: true, dry_run: "Tried on the current data. Nothing was written" }, ...over,
});

test("a plan card shows the step chain with the row counts and what was done and not done", () => {
  const c = planCard(draft());
  assert.deepEqual(c.steps.map((s) => [s.id, s.rowsIn, s.rowsOut]), [["ai1", [160], 144], ["ai2", [144], 38]]);
  assert.deepEqual(c.flow, [160, 144, 38]);
  assert.deepEqual(c.assumptions, [{ text: "Meaning cancelled is code 2 (confirmed, Bob)", state: "confirmed" }]);
  assert.deepEqual(c.done.map((x) => x.key), ["columns", "dry", "counts", "cites"]);
  assert.deepEqual(c.notDone.map((x) => x.key), ["fullRun", "saved"]);
  assert.equal(c.canApply, true);
  assert.equal(c.blocked, "");
});

test("an unanswered question is an open assumption that blocks Apply until it is answered", () => {
  const q = { id: "q1", ask: "Which code means cancelled?", options: [{ value: "2", text: "2" }, { value: "3", text: "3" }] };
  const open = planCard(draft({ cites: [], questions: [q] }));
  assert.deepEqual(open.assumptions, [{ text: q.ask, state: "open", id: "q1", answer: "" }]);
  assert.equal(open.open, 1);
  assert.equal(open.canApply, false);
  assert.equal(open.blocked, "open");
  assert.deepEqual(open.notDone.map((x) => x.key), ["open", "fullRun", "saved"]);
  const answered = planCard(draft({ cites: [], questions: [q] }), { q1: ["2"] });
  assert.deepEqual(answered.assumptions[0], { text: q.ask, state: "answered", id: "q1", answer: "2" });
  assert.equal(answered.canApply, true);
});

test("a draft that failed its check cannot be applied and says why under not done", () => {
  const c = planCard({ steps: [], check: { ok: false, error: "Column x is not there" }, cites: [], questions: [] });
  assert.equal(c.canApply, false);
  assert.equal(c.blocked, "failed");
  assert.deepEqual(c.done, []);
  assert.deepEqual(c.notDone[0], { key: "failed", text: "Column x is not there" });
  assert.deepEqual(c.flow, []);
  assert.equal(planCard(draft({ steps: [] })).blocked, "empty");
});

test("a step with failures is counted under not done and no row flow is claimed without counts", () => {
  const c = planCard(draft({ steps: [{ id: "ai1", summary: "x", step: {}, rows_in: null, rows_out: null, failures: ["bad"] }] }));
  assert.deepEqual(c.flow, []);
  assert.ok(c.notDone.some((x) => x.key === "stepFailures" && x.count === 1));
  assert.ok(!c.done.some((x) => x.key === "counts"));
});

test("a proposal card lists each type with its key, properties and basis, and each rejected one with its reason", () => {
  const c = proposalCard(
    { proposed: [{ id: "order", name: "Order" }, { id: "customer", name: "Customer" }], rejected: [{ name: "Product", reason: "key repeats" }] },
    [{ id: "order", dataset: "orders", key: ["order_no"], basis: "one row per order", version: 3, properties: [{ column: "amount", name: "amount", needed_for: "totals" }, { column: "ship", name: "Ship date" }] }],
  );
  assert.equal(c.types.length, 2);
  assert.deepEqual(c.types[0].properties, [{ column: "amount", name: "", why: "totals" }, { column: "ship", name: "Ship date", why: "" }]);
  assert.equal(c.types[0].basis, "one row per order");
  assert.equal(c.types[1].loaded, false);
  assert.deepEqual(c.rejected, [{ name: "Product", reason: "key repeats" }]);
  assert.deepEqual(c.done.map((x) => x.key), ["checked", "kept"]);
  assert.deepEqual(c.notDone.map((x) => x.key), ["confirmed", "dropped"]);
  assert.equal(c.canPropose, true);
  assert.equal(proposalCard({ proposed: [], rejected: [{ name: "a", reason: "b" }] }).canPropose, false);
  assert.deepEqual(proposalCard({ proposed: [], rejected: [] }).notDone, []);
});

test("proposing a type sends what saving it from its own form sends", () => {
  const ty = { id: "order", name: "Order", description: "d", dataset: "orders", key: ["no"], version: 3, properties: [{ column: "no", name: "no", type: "text" }, { column: "st", name: "Status", type: "integer", enum: true, meanings: { values: [{ value: "1", label: "open" }] } }] };
  assert.deepEqual(proposePayload(ty), {
    id: "order", version: 3, english_name: "order", name: "Order", description: "d", dataset: "orders", key: ["no"],
    properties: [{ column: "no", name: "no", type: "text", enum: false }, { column: "st", name: "Status", type: "integer", enum: true }], enums: { st: [{ value: "1", label: "open" }] },
  });
  assert.equal(proposePayload({ id: "x" }), null);
});

test("a draft waits in session storage for the editor, applies once, and can move to a new pipeline's name", () => {
  const s = store();
  assert.equal(takeDraft(s, "Orders"), null);
  stashDraft(s, "Orders", [{ id: "ai1", step: { type: "transform" } }]);
  assert.deepEqual(takeDraft(s, "Orders"), [{ id: "ai1", step: { type: "transform" } }]);
  assert.equal(takeDraft(s, "Orders"), null);
  stashDraft(s, "new:orders", [{ id: "ai1", step: {} }]);
  moveDraft(s, "new:orders", "Made");
  assert.equal(takeDraft(s, "new:orders"), null);
  assert.equal(takeDraft(s, "Made").length, 1);
  s.setItem("assistant-draft:bad", "{not json");
  assert.equal(takeDraft(s, "bad"), null);
  assert.equal(s.size(), 0);
  moveDraft(s, "nothing", "to");   // moving what is not there does nothing
  assert.equal(s.size(), 0);
});

test("the scope helpers pick the node to draft over", () => {
  assert.equal(defaultSelected({ steps: [{ id: "a", type: "input" }, { id: "b", type: "transform" }, { id: "c", type: "output" }] }), "b");
  assert.equal(defaultSelected({ steps: [] }), null);
  assert.deepEqual(datasetSpec("orders"), { steps: [{ id: "in1", type: "input", dataset: "orders" }] });
});
