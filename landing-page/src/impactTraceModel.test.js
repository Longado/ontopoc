import assert from "node:assert/strict";
import test from "node:test";

import {
  impactTraceEdges,
  impactTraceNodes,
  getImpactTraceFrame,
} from "./impactTraceModel.js";

test("impact trace ends at a human release gate", () => {
  assert.equal(impactTraceNodes.length, 6);
  assert.equal(impactTraceNodes.at(-1).id, "human-gate");
  assert.equal(impactTraceNodes.at(-1).kind, "gate");
});

test("each replay frame advances the active path without crossing the gate", () => {
  const firstFrame = getImpactTraceFrame(0);
  const lastFrame = getImpactTraceFrame(impactTraceEdges.length);

  assert.deepEqual(firstFrame.activeNodeIds, ["change"]);
  assert.equal(firstFrame.activeEdgeIds.length, 0);
  assert.deepEqual(lastFrame.activeEdgeIds, impactTraceEdges.map((edge) => edge.id));
  assert.equal(lastFrame.status, "awaiting_approval");
  assert.equal(lastFrame.activeNodeIds.at(-1), "human-gate");
});

test("replay frames clamp outside the valid range", () => {
  assert.equal(getImpactTraceFrame(-3).step, 0);
  assert.equal(getImpactTraceFrame(99).step, impactTraceEdges.length);
});
