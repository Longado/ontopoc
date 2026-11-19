import assert from "node:assert/strict";
import test from "node:test";
import { askOff, demoAskOf } from "./demoModel.js";

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
