import assert from "node:assert/strict";
import test from "node:test";

import { primaryNavTargets, moveStage } from "./storylineModel.js";

test("primary storyline moves the dynamic proof ahead of the mechanism", () => {
  assert.deepEqual(primaryNavTargets, ["why", "proof", "how", "model"]);
  assert.ok(!primaryNavTargets.includes("review"));
});

test("business model keyboard navigation stays inside its three stages", () => {
  assert.equal(moveStage(0, -1, 3), 0);
  assert.equal(moveStage(0, 1, 3), 1);
  assert.equal(moveStage(2, 1, 3), 2);
});
