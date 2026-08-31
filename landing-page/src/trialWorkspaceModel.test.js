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

test("projects four backend-recorded validation cases without delivery claims", () => {
  const validation = adaptTrialArtifact(artifact).stages[3];

  assert.equal(validation.status, "receipt_recorded");
  assert.deepEqual(validation.data.runtimeAuthority, {
    evaluator: "ontology_poc_generator.rule_runtime.evaluate_synthetic_rule",
    mode: "recorded_deterministic",
    networkAccess: false,
    externalWrites: false,
  });
  assert.equal(validation.data.cases.length, 4);
  assert.deepEqual(
    validation.data.cases.map(({ subjectId, baseline, candidate, atRiskChange }) => ({
      subjectId,
      baseline: [baseline.evaluationStatus, baseline.decisionResult],
      candidate: [candidate.evaluationStatus, candidate.decisionResult],
      atRiskChange,
    })),
    [
      {
        subjectId: "order.synthetic.001",
        baseline: ["pass", "in_queue"],
        candidate: ["pass", "in_queue"],
        atRiskChange: false,
      },
      {
        subjectId: "order.synthetic.002",
        baseline: ["fail", "not_in_queue"],
        candidate: ["pass", "in_queue"],
        atRiskChange: true,
      },
      {
        subjectId: "order.synthetic.003",
        baseline: ["fail", "not_in_queue"],
        candidate: ["fail", "not_in_queue"],
        atRiskChange: false,
      },
      {
        subjectId: "order.synthetic.004",
        baseline: ["not_evaluable", "information_insufficient"],
        candidate: ["not_evaluable", "information_insufficient"],
        atRiskChange: false,
      },
    ],
  );
  assert.deepEqual(validation.data.boundaries, {
    review: "not_started",
    publication: "not_started",
    action: "not_started",
    externalWrite: false,
  });
});

test("keeps every validation receipt and its backend hashes inspectable", () => {
  const validation = adaptTrialArtifact(artifact).stages[3];

  for (const validationCase of validation.data.cases) {
    assert.equal(validationCase.facts.schema, "synthetic_fact_set.v1");
    assert.equal(validationCase.facts.evidenceScope, "synthetic_demo");
    assert.match(validationCase.facts.contentHash, /^[0-9a-f]{64}$/);
    for (const receipt of [validationCase.baseline, validationCase.candidate]) {
      assert.equal(receipt.schema, "validation_receipt.v1");
      assert.match(receipt.contentHash, /^[0-9a-f]{64}$/);
      assert.match(receipt.decisionPackContentHash, /^[0-9a-f]{64}$/);
      assert.match(receipt.ontologySpecContentHash, /^[0-9a-f]{64}$/);
      assert.match(receipt.factsContentHash, /^[0-9a-f]{64}$/);
      assert.match(receipt.ruleId, /^rule_/);
      assert.ok(receipt.factRefs.length > 0);
      assert.ok(receipt.evidenceRefs.length > 0);
      assert.deepEqual(receipt.boundaries, {
        draftCreated: false,
        published: false,
        actionsExecuted: false,
        externalWrite: false,
      });
    }
  }
});

test("rejects a validation baseline pack authority mismatch", () => {
  const changed = structuredClone(artifact);
  changed.validation_run.authority.baseline.decision_pack.content_hash = "a".repeat(64);

  assert.throws(() => adaptTrialArtifact(changed), /baseline DecisionPack hash/);
});

test("rejects a validation receipt facts mismatch", () => {
  const changed = structuredClone(artifact);
  changed.validation_run.cases[0].candidate.receipt.facts_content_hash = "a".repeat(64);

  assert.throws(() => adaptTrialArtifact(changed), /candidate receipt facts hash/);
});

test("rejects an illegal validation status and result pairing", () => {
  const changed = structuredClone(artifact);
  changed.validation_run.cases[0].baseline.receipt.decision_result = "not_in_queue";

  assert.throws(() => adaptTrialArtifact(changed), /baseline receipt evaluation pair/);
});

test("rejects validation receipts with missing evaluation fields", () => {
  for (const removeFields of [
    ["evaluation_status"],
    ["decision_result"],
    ["evaluation_status", "decision_result"],
  ]) {
    const changed = structuredClone(artifact);
    for (const field of removeFields) {
      delete changed.validation_run.cases[0].baseline.receipt[field];
    }
    assert.throws(() => adaptTrialArtifact(changed), /baseline receipt evaluation/);
  }
});

test("rejects validation receipts with unknown evaluation fields", () => {
  for (const mutate of [
    (receipt) => { receipt.evaluation_status = "unknown"; },
    (receipt) => { receipt.decision_result = "unknown"; },
    (receipt) => {
      receipt.evaluation_status = "unknown";
      delete receipt.decision_result;
    },
  ]) {
    const changed = structuredClone(artifact);
    mutate(changed.validation_run.cases[0].candidate.receipt);
    assert.throws(() => adaptTrialArtifact(changed), /candidate receipt evaluation/);
  }
});

test("rejects a receipt that claims publication", () => {
  const changed = structuredClone(artifact);
  changed.validation_run.cases[0].candidate.receipt.published = true;

  assert.throws(() => adaptTrialArtifact(changed), /candidate receipt published/);
});

test("rejects a validation runtime that claims external writes", () => {
  const changed = structuredClone(artifact);
  changed.validation_run.runtime.external_writes = true;

  assert.throws(() => adaptTrialArtifact(changed), /validation runtime external writes/);
});

test("rejects invalid validation authority refs, hashes, and candidate binding", () => {
  for (const [mutate, message] of [
    [(value) => { value.validation_run.authority.baseline.decision_pack.artifact_ref = "#/other"; }, /baseline DecisionPack ref/],
    [(value) => { value.validation_run.authority.baseline.ontology_spec.artifact_ref = "#/other"; }, /baseline OntologySpec ref/],
    [(value) => { value.validation_run.authority.candidate.decision_pack.content_hash = "frontend-hash"; }, /candidate DecisionPack hash/],
    [(value) => { value.validation_run.authority.candidate.ontology_spec.spec.pack_content_hash = "a".repeat(64); }, /candidate OntologySpec pack hash/],
  ]) {
    const changed = structuredClone(artifact);
    mutate(changed);
    assert.throws(() => adaptTrialArtifact(changed), message);
  }
});

test("rejects invalid validation runtime and lifecycle statuses", () => {
  for (const [mutate, message] of [
    [(value) => { value.validation_run.schema = "validation_run.v2"; }, /validation run schema/],
    [(value) => { value.validation_run.runtime.mode = "live"; }, /validation runtime mode/],
    [(value) => { value.validation_run.runtime.network_access = true; }, /validation runtime network access/],
    [(value) => { value.validation_run.run_status.validation = "pending"; }, /validation run status/],
    [(value) => { value.validation_run.run_status.review = "completed"; }, /validation review status/],
    [(value) => { value.validation_run.run_status.external_write = true; }, /validation run external write/],
  ]) {
    const changed = structuredClone(artifact);
    mutate(changed);
    assert.throws(() => adaptTrialArtifact(changed), message);
  }
});

test("rejects invalid validation case and receipt contracts", () => {
  for (const [mutate, message] of [
    [(value) => { value.validation_run.cases.pop(); }, /validation cases/],
    [(value) => { value.validation_run.cases[0].facts.fact_set.schema = "facts.v2"; }, /facts schema/],
    [(value) => { value.validation_run.cases[0].facts.fact_set.evidence_scope = "customer"; }, /facts evidence scope/],
    [(value) => { value.validation_run.cases[0].facts.fact_set.subject_id = "other"; }, /facts subject/],
    [(value) => { value.validation_run.cases[0].baseline.content_hash = "frontend-hash"; }, /baseline receipt content hash/],
    [(value) => { value.validation_run.cases[0].candidate.receipt.schema = "validation_receipt.v2"; }, /candidate receipt schema/],
    [(value) => { value.validation_run.cases[0].baseline.receipt.fact_refs = []; }, /baseline receipt fact refs/],
    [(value) => { value.validation_run.cases[0].candidate.receipt.evidence_refs = []; }, /candidate receipt evidence refs/],
    [(value) => { value.validation_run.cases[0].baseline.receipt.actions_executed = true; }, /baseline receipt actions executed/],
  ]) {
    const changed = structuredClone(artifact);
    mutate(changed);
    assert.throws(() => adaptTrialArtifact(changed), message);
  }
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
