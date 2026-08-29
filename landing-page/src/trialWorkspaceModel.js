import { projectOntologyWorkspace } from "./ontologyWorkspaceModel.js";

const SHA256 = /^[0-9a-f]{64}$/;

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
    throw new Error(`${label} must be a backend SHA-256 hash`);
  }
  return value;
}

function requireValue(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label} must be ${expected}`);
}

export function moveTrialStage(current, key, stageCount) {
  if (key === "ArrowLeft") return Math.max(0, current - 1);
  if (key === "ArrowRight") return Math.min(stageCount - 1, current + 1);
  return current;
}

export function adaptTrialArtifact(input) {
  const artifact = requireRecord(input, "artifact");
  requireValue(artifact.schema, "model_recognition_demo.v1", "artifact schema");

  const recognition = requireRecord(artifact.recognition, "recognition");
  const candidate = requireRecord(recognition.candidate, "recognition candidate");
  requireValue(candidate.schema, "scenario_intake_candidate.v1", "recognition candidate schema");
  requireValue(candidate.match_status, "matched", "matched recognition");

  const recording = requireRecord(artifact.recording, "recording");
  requireValue(recording.mode, "recorded_deterministic_demo", "recording mode");
  requireValue(recording.realtime_model_call, false, "realtime model call");
  if (typeof recording.source_text !== "string" || !recording.source_text.includes("synthetic_demo")) {
    throw new Error("recorded source text must be synthetic_demo");
  }
  if (!recording.source_text.includes(candidate.decision_owner)) {
    throw new Error("recorded source text must contain the decision owner");
  }

  const decisionPackEnvelope = requireRecord(artifact.decision_pack, "DecisionPack envelope");
  const packHash = requireHash(decisionPackEnvelope.content_hash, "DecisionPack hash");
  const pack = requireRecord(decisionPackEnvelope.pack, "DecisionPack");
  requireValue(pack.schema, "decision_pack.v1", "DecisionPack schema");
  const inputBindings = requireArray(pack.input_bindings, "DecisionPack input bindings");
  const sources = requireArray(pack.source_refs, "DecisionPack sources");
  const outcomes = requireArray(pack.knowledge_outcomes, "DecisionPack outcomes");
  const governanceStatuses = [
    ...new Set(
      outcomes.flatMap((outcome) =>
        requireArray(outcome.suggestions, "DecisionPack suggestions").map(
          (suggestion) => suggestion.governance_status,
        ),
      ),
    ),
  ].sort();
  if (!governanceStatuses.length || governanceStatuses.some((status) => status !== "candidate")) {
    throw new Error("DecisionPack knowledge must keep candidate governance");
  }

  const specEnvelope = requireRecord(artifact.ontology_spec, "OntologySpec envelope");
  const specHash = requireHash(specEnvelope.content_hash, "OntologySpec hash");
  requireValue(specEnvelope.compilation_status, "complete", "OntologySpec compilation status");
  const closure = requireRecord(specEnvelope.reference_closure, "reference closure");
  requireValue(closure.is_closed, true, "reference closure");
  if (!Number.isInteger(closure.checked_reference_count) || closure.checked_reference_count < 1) {
    throw new Error("reference closure must report checked references");
  }
  const spec = requireRecord(specEnvelope.spec, "OntologySpec");
  requireValue(spec.schema, "ontology_spec.v1", "OntologySpec schema");
  requireValue(spec.evidence_scope, "synthetic_demo", "OntologySpec evidence scope");
  requireValue(spec.stage, "draft", "OntologySpec stage");
  requireValue(spec.governance_status, "candidate", "candidate governance");
  const specPackHash = requireHash(spec.pack_content_hash, "OntologySpec pack hash");
  if (specPackHash !== packHash) throw new Error("OntologySpec pack hash must match the backend DecisionPack hash");
  const compilationIssues = requireArray(spec.compilation_issues, "OntologySpec compilation issues");
  const reviewIssues = compilationIssues.filter((issue) => issue.severity === "requires_review");
  const ontologyWorkspace = projectOntologyWorkspace(artifact);

  return {
    schema: artifact.schema,
    stages: [
      {
        id: "recognition",
        label: "Recognition",
        status: candidate.match_status,
        data: {
          sourceText: recording.source_text,
          profileKey: candidate.profile_key,
          owner: candidate.decision_owner,
          trigger: candidate.trigger,
          provider: recognition.provider,
          model: recognition.model,
          promptVersion: recognition.prompt_version,
          realtime: recording.realtime_model_call,
        },
      },
      {
        id: "decision-pack",
        label: "DecisionPack",
        status: "complete",
        data: {
          contentHash: packHash,
          businessDecision: pack.scenario.business_decision,
          inputBindings,
          sources,
          outcomes,
          governanceStatuses,
        },
      },
      {
        id: "ontology-spec",
        label: "OntologySpec",
        status: specEnvelope.compilation_status,
        data: {
          contentHash: specHash,
          packContentHash: specPackHash,
          evidenceScope: spec.evidence_scope,
          stage: spec.stage,
          governanceStatus: spec.governance_status,
          referenceClosure: {
            isClosed: closure.is_closed,
            checkedReferenceCount: closure.checked_reference_count,
          },
          counts: {
            entities: requireArray(spec.entity_types, "OntologySpec entities").length,
            relations: requireArray(spec.relation_types, "OntologySpec relations").length,
            properties: requireArray(spec.property_types, "OntologySpec properties").length,
            rules: requireArray(spec.rule_declarations, "OntologySpec rules").length,
          },
          reviewIssues,
          ontologyWorkspace,
        },
      },
      {
        id: "validation",
        label: "Validation",
        status: "not_implemented",
        data: {
          contractDefined: true,
          evaluatorExecuted: false,
          receipt: null,
          boundaries: {
            draftCreated: false,
            published: false,
            actionsExecuted: false,
            externalWrite: false,
          },
        },
      },
    ],
  };
}
