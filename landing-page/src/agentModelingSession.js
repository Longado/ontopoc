import { adaptTrialArtifact } from "./trialWorkspaceModel.js";

const SHA256 = /^[0-9a-f]{64}$/;
const RECORDED_MODE = "recorded_deterministic_demo";

function boundaries() {
  return {
    persisted: false,
    published: false,
    actions_executed: false,
    external_write: false,
  };
}

function requireRecord(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value;
}

function requireArray(value, label) {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function requireHash(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new Error(`${label} must be a SHA-256 hash`);
  }
  return value;
}

function requireValue(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label} must be ${expected}`);
}

function stableCandidateIds(spec) {
  const ids = [
    ...requireArray(spec.entity_types, "OntologySpec entity types").map(({ type_id }) => type_id),
    ...requireArray(spec.relation_types, "OntologySpec relation types").map(
      ({ relation_type_id }) => relation_type_id,
    ),
    ...requireArray(spec.rule_declarations, "OntologySpec rule declarations").map(
      ({ rule_id }) => rule_id,
    ),
  ];
  if (ids.some((id) => typeof id !== "string" || !id)) {
    throw new Error("candidate IDs must be stable non-empty strings");
  }
  if (new Set(ids).size !== ids.length) throw new Error("candidate IDs must be unique");
  return ids.sort();
}

function sameIds(actual, expected) {
  return actual.length === expected.length
    && actual.every((id, index) => id === expected[index]);
}

export function createRecordedAgentModelingSession(artifactInput, projectedViewInput) {
  const artifact = requireRecord(artifactInput, "artifact");
  const projectedView = projectedViewInput ?? adaptTrialArtifact(artifact);
  if (projectedViewInput) adaptTrialArtifact(artifact);

  const recording = requireRecord(artifact.recording, "recording");
  requireValue(recording.mode, RECORDED_MODE, "recording mode");
  requireValue(recording.realtime_model_call, false, "realtime model call");

  const recognition = requireRecord(artifact.recognition, "recognition");
  const recognitionCandidate = requireRecord(recognition.candidate, "recognition candidate");
  const specEnvelope = requireRecord(artifact.ontology_spec, "OntologySpec envelope");
  const specHash = requireHash(specEnvelope.content_hash, "OntologySpec hash");
  const spec = requireRecord(specEnvelope.spec, "OntologySpec");

  const view = requireRecord(projectedView, "projected view");
  const ontologyStage = requireArray(view.stages, "projected stages").find(
    ({ id }) => id === "ontology-spec",
  );
  const projectedHash = requireHash(
    requireRecord(ontologyStage?.data, "projected OntologySpec stage").contentHash,
    "projected OntologySpec hash",
  );
  if (projectedHash !== specHash) {
    throw new Error("projected OntologySpec hash must match the artifact spec hash");
  }

  const counts = {
    entities: requireArray(spec.entity_types, "OntologySpec entity types").length,
    relations: requireArray(spec.relation_types, "OntologySpec relation types").length,
    rules: requireArray(spec.rule_declarations, "OntologySpec rule declarations").length,
  };
  const projectedCounts = requireRecord(ontologyStage.data.counts, "projected candidate counts");
  for (const [kind, count] of Object.entries(counts)) {
    if (projectedCounts[kind] !== count) {
      throw new Error(`projected ${kind} count must match the artifact`);
    }
  }
  const candidateIds = stableCandidateIds(spec);

  return {
    schema: "agent_modeling_session.v1",
    mode: RECORDED_MODE,
    realtimeModelCall: false,
    specHash,
    candidates: { counts, stableIds: candidateIds },
    stages: [
      {
        id: "document_received",
        status: "complete",
        data: { sourceText: recording.source_text, evidenceScope: spec.evidence_scope },
      },
      {
        id: "known_template_recognized",
        status: "complete",
        data: {
          profileKey: recognitionCandidate.profile_key,
          matchStatus: recognitionCandidate.match_status,
        },
      },
      {
        id: "deterministic_candidates_compiled",
        status: "complete",
        data: { specHash, candidateCounts: counts },
      },
      {
        id: "human_confirmation",
        status: "pending",
        data: { candidateIds },
      },
    ],
    boundaries: boundaries(),
  };
}

export function confirmAgentModelingSession(sessionInput, bindingInput) {
  const session = requireRecord(sessionInput, "Agent modeling session");
  requireValue(session.schema, "agent_modeling_session.v1", "Agent modeling session schema");
  requireValue(session.mode, RECORDED_MODE, "Agent modeling session mode");
  requireValue(session.realtimeModelCall, false, "Agent modeling realtime model call");

  const binding = requireRecord(bindingInput, "confirmation binding");
  const sessionHash = requireHash(session.specHash, "session spec hash");
  const bindingHash = requireHash(binding.specHash, "confirmation spec hash");
  if (bindingHash !== sessionHash) throw new Error("confirmation spec hash must match the session");

  const candidates = requireRecord(session.candidates, "session candidates");
  const expectedIds = [...requireArray(candidates.stableIds, "session candidate IDs")].sort();
  const actualIds = [...requireArray(binding.candidateIds, "confirmation candidate IDs")].sort();
  if (new Set(actualIds).size !== actualIds.length || !sameIds(actualIds, expectedIds)) {
    throw new Error("confirmation candidate IDs must match the complete session candidate set");
  }

  return {
    schema: "agent_modeling_confirmation_receipt.v1",
    status: "confirmed_for_session",
    mode: RECORDED_MODE,
    specHash: sessionHash,
    candidateIds: expectedIds,
    boundaries: boundaries(),
  };
}
