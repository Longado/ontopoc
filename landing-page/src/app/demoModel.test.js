import assert from "node:assert/strict";
import test from "node:test";
import { askOff, demoAskOf, holdAsk, readAgain } from "./demoModel.js";

test("demoAskOf reads a boolean only", () => {
  assert.equal(demoAskOf({ demo: true, demo_ask: false }), false);
  assert.equal(demoAskOf({ demo_ask: true }), true);
  assert.equal(demoAskOf({ demo: true }), undefined);
  assert.equal(demoAskOf(null), undefined);
  assert.equal(demoAskOf({ demo_ask: "no" }), undefined);
});

test("askOff only for a guest when demo_ask is false", () => {
  const guest = { provider: "demo", role: "viewer" };
  assert.equal(askOff(guest, false), true);
  assert.equal(askOff(guest, true), false);
  assert.equal(askOff(guest, undefined), false);
  assert.equal(askOff({ provider: "local", role: "viewer" }, false), false);
  assert.equal(askOff(null, false), false);
});

test("holdAsk: a guest's question from a link waits until the demo says asking is on", () => {
  const guest = { provider: "demo", role: "viewer" };
  assert.equal(holdAsk(guest, undefined), true);   // health not read yet, or unreadable
  assert.equal(holdAsk(guest, false), true);
  assert.equal(holdAsk(guest, true), false);
  assert.equal(holdAsk({ provider: "local", role: "viewer" }, undefined), false);
});

test("readAgain tries again after a failure and gives up after the last try", async () => {
  let calls = 0;
  const flaky = () => (++calls < 3 ? Promise.reject(new Error("down")) : Promise.resolve("ok"));
  assert.equal(await readAgain(flaky, { tries: 3, wait: 0 }), "ok");
  assert.equal(calls, 3);
  calls = 0;
  await assert.rejects(readAgain(() => { calls += 1; return Promise.reject(new Error("down")); }, { tries: 2, wait: 0 }), /down/);
  assert.equal(calls, 2);
});
