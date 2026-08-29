import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { adaptTrialArtifact, moveTrialStage } from "./trialWorkspaceModel.js";

const artifact = JSON.parse(
  await readFile(
    new URL("../public/artifacts/supply-chain-recognition.json", import.meta.url),
    "utf8",
  ),
);

test("adapts the recorded backend envelope into four read-only stages", () => {
  const workspace = adaptTrialArtifact(artifact);

  assert.deepEqual(
    workspace.stages.map(({ id, label }) => [id, label]),
    [
      ["recognition", "Recognition"],
      ["decision-pack", "DecisionPack"],
      ["ontology-spec", "OntologySpec"],
      ["validation", "Validation"],
    ],
  );
  assert.equal(moveTrialStage(0, "ArrowLeft", workspace.stages.length), 0);
  assert.equal(moveTrialStage(0, "ArrowRight", workspace.stages.length), 1);
  assert.equal(moveTrialStage(3, "ArrowRight", workspace.stages.length), 3);
});

test("exposes matched recognition and traceable recorded-demo provenance", () => {
  const recognition = adaptTrialArtifact(artifact).stages[0];

  assert.equal(recognition.status, "matched");
  assert.match(recognition.data.sourceText, /synthetic_demo/);
  assert.equal(recognition.data.profileKey, "order_priority_intervention");
  assert.ok(recognition.data.sourceText.includes(recognition.data.owner));
  assert.match(recognition.data.provider, /recorded.*demo/i);
  assert.match(recognition.data.model, /deterministic.*demo/i);
  assert.equal(recognition.data.realtime, false);
});

test("preserves backend-owned DecisionPack hashes and candidate knowledge", () => {
  const decisionPack = adaptTrialArtifact(artifact).stages[1];

  assert.equal(decisionPack.status, "complete");
  assert.match(decisionPack.data.contentHash, /^[0-9a-f]{64}$/);
  assert.equal(decisionPack.data.businessDecision, "哪些订单进入优先干预队列");
  assert.equal(decisionPack.data.inputBindings.length, 3);
  assert.ok(decisionPack.data.sources.length > 0);
  assert.equal(decisionPack.data.outcomes.length, 2);
  assert.deepEqual(decisionPack.data.governanceStatuses, ["candidate"]);
});

test("bounds complete to compilation and reports synthetic draft candidate spec", () => {
  const ontologySpec = adaptTrialArtifact(artifact).stages[2];

  assert.equal(ontologySpec.status, "complete");
  assert.match(ontologySpec.data.contentHash, /^[0-9a-f]{64}$/);
  assert.match(ontologySpec.data.packContentHash, /^[0-9a-f]{64}$/);
  assert.equal(ontologySpec.data.evidenceScope, "synthetic_demo");
  assert.equal(ontologySpec.data.stage, "draft");
  assert.equal(ontologySpec.data.governanceStatus, "candidate");
  assert.equal(ontologySpec.data.referenceClosure.isClosed, true);
  assert.ok(ontologySpec.data.referenceClosure.checkedReferenceCount > 0);
  assert.deepEqual(ontologySpec.data.counts, {
    entities: 3,
    relations: 3,
    properties: 2,
    rules: 1,
  });
  assert.equal(ontologySpec.data.reviewIssues.length, 5);
  assert.ok(ontologySpec.data.reviewIssues.every(({ severity }) => severity === "requires_review"));
});

test("attaches the deterministic ontology workspace without adding a compiler stage", () => {
  const workspace = adaptTrialArtifact(artifact);
  const ontologySpec = workspace.stages[2];

  assert.equal(workspace.stages.length, 4);
  assert.equal(ontologySpec.id, "ontology-spec");
  assert.equal(ontologySpec.data.ontologyWorkspace.entityNodes.length, 3);
  assert.equal(ontologySpec.data.ontologyWorkspace.relationEdges.length, 3);
  assert.equal(ontologySpec.data.ontologyWorkspace.ruleNodes.length, 1);
  assert.equal(
    ontologySpec.data.ontologyWorkspace.specHash,
    ontologySpec.data.contentHash,
  );
});

test("keeps Validation contract-only with no receipt or delivery claims", () => {
  const validation = adaptTrialArtifact(artifact).stages[3];

  assert.equal(validation.status, "not_implemented");
  assert.equal(validation.data.contractDefined, true);
  assert.equal(validation.data.evaluatorExecuted, false);
  assert.equal(validation.data.receipt, null);
  assert.deepEqual(validation.data.boundaries, {
    draftCreated: false,
    published: false,
    actionsExecuted: false,
    externalWrite: false,
  });
});

test("rejects envelopes that cross schema, match, governance, or hash boundaries", () => {
  for (const [mutate, message] of [
    [(value) => { value.schema = "unknown.v1"; }, /artifact schema/],
    [(value) => { value.recognition.candidate.match_status = "unsupported"; }, /matched recognition/],
    [(value) => { value.ontology_spec.spec.governance_status = "published"; }, /candidate governance/],
    [(value) => { value.decision_pack.content_hash = "frontend-hash"; }, /DecisionPack hash/],
  ]) {
    const changed = structuredClone(artifact);
    mutate(changed);
    assert.throws(() => adaptTrialArtifact(changed), message);
  }
});
