import assert from "node:assert/strict";
import test from "node:test";
import { actionState, allowedMode, loadThread, nextVersion, saveThread, commandChoices, datasetSpec, defaultSelected, isNoModel, modesFor, moveDraft, parseCommand, planCard, privacyKey, meaningsCard, meaningsPayloads, proposalCard, proposePayload, scopeKind, stashDraft, takeDraft, textOptional } from "./assistantModel.js";

const store = () => {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), size: () => m.size };
};

test("a builder sees all five modes and a viewer sees Ask only", () => {
  assert.deepEqual(modesFor(true), ["ask", "query", "model", "pipeline", "meanings"]);
  assert.equal(allowedMode("meanings", false), "ask");
  assert.deepEqual(modesFor(false), ["ask"]);
  assert.equal(allowedMode("pipeline", false), "ask");
  assert.equal(allowedMode("pipeline", true), "pipeline");
  assert.equal(allowedMode("nonsense", true), "ask");
});

test("each mode has its own scope kind and privacy line", () => {
  assert.deepEqual(["ask", "query", "model", "pipeline", "meanings"].map(scopeKind), ["types", "types", "datasets", "target", "type"]);
  assert.equal(privacyKey("meanings"), "ask.assistant.privacy.meanings");
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
  assert.deepEqual(parseCommand("/meanings the status codes", true), { mode: "meanings", text: "the status codes" });
  assert.equal(parseCommand("/meanings", false), null);
});

test("typing a slash offers the commands this person may use", () => {
  assert.deepEqual(commandChoices("/", true), ["ask", "query", "model", "pipeline", "meanings"]);
  assert.deepEqual(commandChoices("/mea", true), ["meanings"]);
  assert.deepEqual(commandChoices("/mea", false), []);
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
  const c = planCard(draft({ steps: [{ id: "ai1", summary: "x", step: {}, rows_in: null, rows_out: null, failures: { "no_value": 3 } }] }));
  assert.deepEqual(c.flow, []);
  assert.ok(c.notDone.some((x) => x.key === "stepFailures" && x.count === 1));
  assert.ok(!c.done.some((x) => x.key === "counts"));
});

test("a proposal card lists each type with its key, properties and basis, and each rejected one with its reason", () => {
  const c = proposalCard(
    { proposed: [{ id: "order", name: "Order" }, { id: "customer", name: "Customer" }], rejected: [{ name: "Product", reason: "key repeats" }] },
    [{ id: "order", dataset: "orders", key: ["order_no"], basis: "one row per order", version: 3, properties: [{ column: "order_no", name: "order_no", key: true }, { column: "amount", name: "amount", needed_for: "totals" }, { column: "ship", name: "Ship date" }] }],
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
    properties: [{ column: "no", name: "no", type: "text", enum: false }, { column: "st", name: "Status", type: "integer", enum: true }], enums: { st: [{ value: "1", label: "open" }] }, assistant: true,
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

test("the thread survives in the tab's session storage, per user, without anything still waiting", () => {
  const s = store();
  const turns = [
    { id: "t1", kind: "ask", text: "How many?", status: "done", record: { id: 7 } },
    { id: "t2", kind: "pipeline", text: "sum", status: "done", plan: { draft: { steps: [] }, answers: {}, busy: true } },
    { id: "t3", kind: "ask", text: "later", status: "thinking" },
  ];
  saveThread(s, "ann", turns);
  assert.equal(loadThread(s, "bob").length, 0);
  const back = loadThread(s, "ann");
  assert.deepEqual(back.map((x) => x.id), ["t1", "t2"]);   // a turn still waiting for the service cannot be resumed
  assert.equal(back[1].plan.busy, false);
  saveThread(s, "ann", []);
  assert.equal(s.size(), 0);
  s.setItem("assistant-thread:ann", "{nope");
  assert.deepEqual(loadThread(s, "ann"), []);
  assert.deepEqual(loadThread(s, null), []);
});

test("a revised request is a new version of the card: the next number, counting the versions already in the thread", () => {
  const a = { id: "t1", kind: "pipeline", version: 1, plan: {} };
  const b = { id: "t2", kind: "pipeline", version: 2, revises: "t1", plan: {} };
  assert.equal(nextVersion([a], "t1"), 2);
  assert.equal(nextVersion([a, b], "t1"), 3);
  assert.equal(nextVersion([a, b], "t2"), 3);
  assert.equal(nextVersion([a], undefined), 1);
});

test("an open question blocks Apply only, and says why; a frozen card has no actions", () => {
  const open = { canApply: false, blocked: "open" };
  assert.deepEqual(actionState(open, {}), { apply: { enabled: false, reason: "open" }, revise: true, discard: true });
  assert.deepEqual(actionState({ canApply: true, blocked: "" }, {}), { apply: { enabled: true, reason: "" }, revise: true, discard: true });
  assert.deepEqual(actionState({ canApply: false, blocked: "failed" }, {}).apply, { enabled: false, reason: "failed" });
  // after Apply the card is frozen: no second Apply, a change is a new turn
  assert.deepEqual(actionState({ canApply: true, blocked: "" }, { applied: true }), { apply: { enabled: false, reason: "applied" }, revise: true, discard: false });
  assert.deepEqual(actionState({ canApply: true, blocked: "" }, { supersededBy: "t2" }), { apply: { enabled: false, reason: "superseded" }, revise: false, discard: false });
  assert.deepEqual(actionState({ canApply: true, blocked: "" }, { discarded: true }), { apply: { enabled: false, reason: "discarded" }, revise: false, discard: false });
  // busy re-checking stops Apply but never Revise or Discard
  assert.equal(actionState({ canApply: true, blocked: "" }, { busy: true }).apply.enabled, false);
  assert.equal(actionState({ canApply: true, blocked: "" }, { busy: true }).revise, true);
});

test("the proposal card shows what each type stood on and what it left out when the response says", () => {
  const c = proposalCard({ proposed: [{ id: "order", name: "Order", basis: "one row per order", left_out: ["ship_date", "note"], dataset: "orders", key: ["no"] }], rejected: [] }, [{ id: "order", dataset: "orders", key: ["no"], version: 1, properties: [] }]);
  assert.equal(c.types[0].basis, "one row per order");
  assert.deepEqual(c.types[0].leftOut, ["ship_date", "note"]);
  const none = proposalCard({ proposed: [{ id: "x", name: "X" }], rejected: [] }, []);
  assert.deepEqual(none.types[0].leftOut, []);
  assert.equal(none.types[0].basis, "");
});

test("a plan card takes its assumptions and self-check from the service, and an open assumption blocks Apply only", () => {
  const draft = {
    steps: [{ id: "a", summary: "s", step: { type: "transform" }, rows_in: [10], rows_out: 5 }], check: { ok: true },
    assumptions: [
      { id: "meaning:st|x", text: "Confirmed one", status: "confirmed", definition: "enum:order:st" },
      { id: "answer:q", text: "You chose", status: "confirmed", by: "you" },
      { id: "question:q2", question: "q2", text: "Which?", status: "open" },
    ],
    self_check: { done: [{ key: "columns", text: "Columns exist" }], not_done: [{ key: "open", text: "1 open" }, { key: "fullRun", text: "Run on all" }] },
  };
  const c = planCard(draft, {});
  assert.deepEqual(c.assumptions.map((a) => [a.state, a.text, a.definition ?? null]), [["confirmed", "Confirmed one", "enum:order:st"], ["confirmed", "You chose", null], ["open", "Which?", null]]);
  assert.equal(c.open, 1);
  assert.equal(c.canApply, false);
  assert.equal(c.blocked, "open");
  assert.deepEqual(c.done, [{ key: "columns", text: "Columns exist" }]);
  assert.equal(c.notDone[1].text, "Run on all");
  // a service that sends none (an older one): the card works the facts out from the draft as before
  assert.equal(planCard({ ...draft, assumptions: undefined, self_check: undefined }, {}).done[0].key, "columns");
});

test("a type proposal has its assumptions; an open one must be acknowledged before Propose", () => {
  const result = {
    proposed: [{ id: "order", name: "Order", assumptions: [{ id: "key:order", text: "Key unique", status: "confirmed", definition: "objtype:order" }, { id: "meanings:order:st", text: "Nobody confirmed st", status: "open", definition: "enum:order:st" }] }],
    rejected: [], self_check: { done: [{ key: "checked", text: "ok" }], not_done: [{ key: "confirmed", text: "nobody" }] },
  };
  const details = [{ id: "order", dataset: "orders", key: ["no"], version: 1, properties: [] }];
  const c = proposalCard(result, details, {});
  assert.deepEqual(c.assumptions.map((a) => [a.state, a.type]), [["confirmed", "order"], ["open", "order"]]);
  assert.equal(c.open, 1);
  assert.equal(c.canPropose, false);
  assert.equal(c.blocked, "open");
  const seen = proposalCard(result, details, { "meanings:order:st": true });
  assert.equal(seen.open, 0);
  assert.equal(seen.canPropose, true);
  assert.equal(seen.assumptions[1].state, "answered");
  assert.equal(c.done[0].text, "ok");
});

const DRAFT = {
  type: "order", dataset: "订单",
  columns: [
    { column: "状态码", field: "订单.状态码", rows: 160, state: null, confirmed: false, checks: { confirmed: false, no_meaning: ["2"], never_seen: ["9"] }, values: [
      { value: "0", rows: 96, facts: [], pattern: true, current: "", draft: { label: "已交付", description: "", basis: "x" } },
      { value: "1", rows: 48, facts: [], pattern: false, current: "进行中", draft: { label: "生产中", description: "在做", basis: "" } },
      { value: "2", rows: 16, facts: [], pattern: false, current: "", draft: null },
    ] },
    { column: "等级", field: "订单.等级", rows: 160, state: "confirmed", confirmed: true, checks: { confirmed: true, no_meaning: [], never_seen: [] }, values: [
      { value: "A", rows: 80, facts: [], pattern: false, current: "大客户", draft: null },
    ] },
  ],
  skipped: [{ column: "备注", reason: "x" }], rejected: [],
  assumptions: [{ id: "a", text: "t", status: "open", definition: "enum:order:状态码" }],
  self_check: { done: [{ key: "values", text: "ok" }], not_done: [{ key: "saved", text: "no" }] },
};

test("the meanings card lists each code with flags worked out from the checks, and keeps every draft unless skipped", () => {
  const card = meaningsCard(DRAFT);
  const codes = card.columns[0].values;
  assert.deepEqual(codes.map((v) => [v.value, v.label, v.keep]), [["0", "已交付", true], ["1", "生产中", true], ["2", "", false]]);
  assert.deepEqual(codes.map((v) => v.flags), [[], ["differs", "noPattern"], ["unmeant"]]);
  assert.deepEqual(card.columns[0].gone, ["9"]);
  assert.equal(card.columns[1].confirmed, true);
  assert.equal(card.kept, 2);
  assert.equal(card.canApply, true);
  assert.deepEqual(card.assumptions, [{ id: "a", text: "t", state: "open", definition: "enum:order:状态码", by: null }]);
  assert.deepEqual(card.notDone, [{ key: "saved", text: "no" }]);
  const none = meaningsCard(DRAFT, { "状态码|0": false, "状态码|1": false });
  assert.equal(none.canApply, false);
  assert.equal(none.blocked, "none");
});

test("Apply sends the kept meanings per column in the shape of the type's own meanings editor, and nothing for confirmed columns", () => {
  assert.deepEqual(meaningsPayloads(DRAFT), [{ id: "order", column: "状态码", values: [{ value: "0", label: "已交付", description: "" }, { value: "1", label: "生产中", description: "在做" }] }]);
  assert.deepEqual(meaningsPayloads(DRAFT, { "状态码|1": false }), [{ id: "order", column: "状态码", values: [{ value: "0", label: "已交付", description: "" }] }]);
  assert.deepEqual(meaningsPayloads(DRAFT, { "状态码|0": false, "状态码|1": false }), []);
});

test("Model and Meanings may be sent with no message", () => {
  assert.deepEqual(["ask", "query", "model", "pipeline", "meanings"].map(textOptional), [false, false, true, false, true]);
});
