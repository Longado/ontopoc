import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  confirmAgentModelingSession,
  createRecordedAgentModelingSession,
} from "./agentModelingSession.js";
import { adaptTrialArtifact } from "./trialWorkspaceModel.js";

const artifact = JSON.parse(
  await readFile(
    new URL("../public/artifacts/supply-chain-recognition.json", import.meta.url),
    "utf8",
  ),
);

test("creates an observable recorded Agent draft from the verified artifact", () => {
  const session = createRecordedAgentModelingSession(artifact);

  assert.equal(session.schema, "agent_modeling_session.v1");
  assert.equal(session.mode, "recorded_deterministic_demo");
  assert.equal(session.realtimeModelCall, false);
  assert.deepEqual(
    session.stages.map(({ id, status }) => [id, status]),
    [
      ["document_received", "complete"],
      ["known_template_recognized", "complete"],
      ["deterministic_candidates_compiled", "complete"],
      ["human_confirmation", "pending"],
    ],
  );
});

test("derives candidate counts and stable IDs from the compiled artifact", () => {
  const session = createRecordedAgentModelingSession(artifact);
  const spec = artifact.ontology_spec.spec;
  const expectedIds = [
    ...spec.entity_types.map(({ type_id }) => type_id),
    ...spec.relation_types.map(({ relation_type_id }) => relation_type_id),
    ...spec.rule_declarations.map(({ rule_id }) => rule_id),
  ].sort();

  assert.equal(session.specHash, artifact.ontology_spec.content_hash);
  assert.deepEqual(session.candidates.counts, {
    entities: 3,
    relations: 3,
    rules: 1,
  });
  assert.deepEqual(session.candidates.stableIds, expectedIds);
  assert.deepEqual(session.boundaries, {
    persisted: false,
    published: false,
    actions_executed: false,
    external_write: false,
  });
});

test("keeps observable stages tied to source, template, and compilation evidence", () => {
  const session = createRecordedAgentModelingSession(artifact);
  const [document, recognition, compilation, confirmation] = session.stages;

  assert.equal(document.data.sourceText, artifact.recording.source_text);
  assert.equal(document.data.evidenceScope, "synthetic_demo");
  assert.equal(recognition.data.profileKey, artifact.recognition.candidate.profile_key);
  assert.equal(recognition.data.matchStatus, "matched");
  assert.equal(compilation.data.specHash, artifact.ontology_spec.content_hash);
  assert.deepEqual(compilation.data.candidateCounts, session.candidates.counts);
  assert.deepEqual(confirmation.data.candidateIds, session.candidates.stableIds);
});

test("confirms only the complete session candidate set and returns a bounded receipt", () => {
  const session = createRecordedAgentModelingSession(artifact);
  const receipt = confirmAgentModelingSession(session, {
    specHash: session.specHash,
    candidateIds: session.candidates.stableIds,
  });

  assert.deepEqual(receipt, {
    schema: "agent_modeling_confirmation_receipt.v1",
    status: "confirmed_for_session",
    mode: "recorded_deterministic_demo",
    specHash: session.specHash,
    candidateIds: session.candidates.stableIds,
    boundaries: {
      persisted: false,
      published: false,
      actions_executed: false,
      external_write: false,
    },
  });
});

test("rejects missing or mismatched confirmation bindings", () => {
  const session = createRecordedAgentModelingSession(artifact);

  assert.throws(
    () => confirmAgentModelingSession(session, { candidateIds: session.candidates.stableIds }),
    /spec hash/i,
  );
  assert.throws(
    () => confirmAgentModelingSession(session, {
      specHash: "a".repeat(64),
      candidateIds: session.candidates.stableIds,
    }),
    /spec hash.*match/i,
  );
  assert.throws(
    () => confirmAgentModelingSession(session, {
      specHash: session.specHash,
      candidateIds: session.candidates.stableIds.slice(1),
    }),
    /candidate ids.*match/i,
  );
});

test("rejects altered recording mode, realtime calls, and projection hash drift", () => {
  const changedMode = structuredClone(artifact);
  changedMode.recording.mode = "live_model";
  assert.throws(() => createRecordedAgentModelingSession(changedMode), /recording mode/i);

  const realtime = structuredClone(artifact);
  realtime.recording.realtime_model_call = true;
  assert.throws(() => createRecordedAgentModelingSession(realtime), /realtime model call/i);

  const missingHash = structuredClone(artifact);
  delete missingHash.ontology_spec.content_hash;
  assert.throws(() => createRecordedAgentModelingSession(missingHash), /OntologySpec hash/i);

  const projectedView = adaptTrialArtifact(artifact);
  const mismatchedView = structuredClone(projectedView);
  mismatchedView.stages[2].data.contentHash = "b".repeat(64);
  assert.throws(
    () => createRecordedAgentModelingSession(artifact, mismatchedView),
    /projected OntologySpec hash.*match/i,
  );
});
