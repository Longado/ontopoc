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

function requireNonEmptyString(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function requireNonEmptyStrings(value, label) {
  const items = requireArray(value, label);
  if (!items.length || items.some((item) => typeof item !== "string" || !item.trim())) {
    throw new Error(`${label} must contain backend references`);
  }
  return items;
}

function requireUniqueNonEmptyStrings(value, label) {
  const items = requireNonEmptyStrings(value, label);
  if (new Set(items).size !== items.length) {
    throw new Error(`${label} must contain unique backend references`);
  }
  return items;
}

function caseInsensitiveKey(value) {
  return value.toLowerCase();
}

function requireCaseInsensitiveUniqueNonEmptyStrings(value, label) {
  const items = requireNonEmptyStrings(value, label);
  if (new Set(items.map(caseInsensitiveKey)).size !== items.length) {
    throw new Error(`${label} must contain case-insensitively unique backend references`);
  }
  return items;
}

function requireValue(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label} must be ${expected}`);
}

function requireExactReferences(actual, expected, label) {
  const actualRefs = requireUniqueNonEmptyStrings(actual, label);
  const expectedRefs = [...new Set(expected)];
  if (
    actualRefs.length !== expectedRefs.length
    || actualRefs.some((reference) => !expectedRefs.includes(reference))
  ) {
    throw new Error(`${label} must match the rule reference closure`);
  }
  return actualRefs;
}

function collectPackSuggestions(pack, label) {
  return requireArray(pack.knowledge_outcomes, `${label} outcomes`).flatMap((outcome, outcomeIndex) => {
    const outcomeRecord = requireRecord(outcome, `${label} outcome ${outcomeIndex + 1}`);
    return requireArray(outcomeRecord.suggestions, `${label} outcome ${outcomeIndex + 1} suggestions`)
      .map((suggestion, suggestionIndex) => requireRecord(
        suggestion,
        `${label} outcome ${outcomeIndex + 1} suggestion ${suggestionIndex + 1}`,
      ));
  });
}

function collectPackSourceRefs(pack, label) {
  const sourceRefs = requireArray(pack.source_refs, `${label} sources`).map((source, index) => {
    const sourceRecord = requireRecord(source, `${label} source ${index + 1}`);
    return requireNonEmptyString(sourceRecord.source_ref_id, `${label} source ${index + 1} ID`);
  });
  if (new Set(sourceRefs).size !== sourceRefs.length) {
    throw new Error(`${label} source IDs must be unique`);
  }
  return sourceRefs;
}

function indexUniqueRecords(value, idField, label) {
  const records = requireArray(value, `${label}s`);
  const ids = records.map((record, index) => {
    const item = requireRecord(record, `${label} ${index + 1}`);
    return requireNonEmptyString(item[idField], `${label} ${index + 1} ID`);
  });
  if (new Set(ids).size !== ids.length) {
    throw new Error(`${label} IDs must be unique`);
  }
  return { records, ids: new Set(ids) };
}

function validateCandidateReferenceClosure(candidatePack, candidateSpec, suggestions, sourceRefs) {
  const suggestionIds = suggestions.map((suggestion, index) => requireNonEmptyString(
    suggestion.suggestion_id,
    `candidate DecisionPack suggestion ${index + 1} ID`,
  ));
  if (new Set(suggestionIds).size !== suggestionIds.length) {
    throw new Error("candidate DecisionPack suggestion IDs must be unique");
  }
  const sourceRefSet = new Set(sourceRefs);
  suggestions.forEach((suggestion, index) => {
    const suggestionSourceRefs = requireUniqueNonEmptyStrings(
      suggestion.source_ref_ids,
      `candidate DecisionPack suggestion ${index + 1} source refs`,
    );
    if (suggestionSourceRefs.some((sourceRef) => !sourceRefSet.has(sourceRef))) {
      throw new Error("candidate DecisionPack suggestion source refs must resolve in the pack");
    }
  });
  const bindings = indexUniqueRecords(
    candidatePack.input_bindings,
    "binding_id",
    "candidate DecisionPack input binding",
  );
  const scenario = requireRecord(candidatePack.scenario, "candidate DecisionPack scenario");
  const bridges = indexUniqueRecords(
    scenario.declared_bridges,
    "semantic_key",
    "candidate DecisionPack declared bridge",
  );

  const entities = indexUniqueRecords(
    candidateSpec.entity_types,
    "type_id",
    "candidate OntologySpec entity",
  );
  const relations = indexUniqueRecords(
    candidateSpec.relation_types,
    "relation_type_id",
    "candidate OntologySpec relation",
  );
  const properties = indexUniqueRecords(
    candidateSpec.property_types,
    "property_type_id",
    "candidate OntologySpec property",
  );
  const rules = indexUniqueRecords(
    candidateSpec.rule_declarations,
    "rule_id",
    "candidate OntologySpec rule",
  );
  const suggestionIdSet = new Set(suggestionIds);

  entities.records.forEach((entity, index) => {
    const originKind = requireNonEmptyString(
      entity.origin_kind,
      `candidate OntologySpec entity ${index + 1} origin kind`,
    );
    const originRefId = requireNonEmptyString(
      entity.origin_ref_id,
      `candidate OntologySpec entity ${index + 1} origin ref`,
    );
    if (originKind !== "provided_input") {
      throw new Error("candidate OntologySpec entity origin kind is unsupported");
    }
    if (!bindings.ids.has(originRefId)) {
      throw new Error("candidate OntologySpec entity origin binding must resolve in the pack");
    }
  });

  relations.records.forEach((relation, index) => {
    const domainId = requireNonEmptyString(
      relation.domain_type_id,
      `candidate OntologySpec relation ${index + 1} domain`,
    );
    const rangeId = requireNonEmptyString(
      relation.range_type_id,
      `candidate OntologySpec relation ${index + 1} range`,
    );
    if (!entities.ids.has(domainId)) {
      throw new Error("candidate OntologySpec relation domain must resolve to an entity");
    }
    if (!entities.ids.has(rangeId)) {
      throw new Error("candidate OntologySpec relation range must resolve to an entity");
    }
    const originKind = requireNonEmptyString(
      relation.origin_kind,
      `candidate OntologySpec relation ${index + 1} origin kind`,
    );
    const originRefId = requireNonEmptyString(
      relation.origin_ref_id,
      `candidate OntologySpec relation ${index + 1} origin ref`,
    );
    if (originKind === "knowledge_suggestion") {
      if (!suggestionIdSet.has(originRefId)) {
        throw new Error("candidate OntologySpec relation origin suggestion must resolve in the pack");
      }
    } else if (originKind === "provided_input") {
      if (!bridges.ids.has(originRefId)) {
        throw new Error("candidate OntologySpec relation origin bridge must resolve in the pack");
      }
    } else {
      throw new Error("candidate OntologySpec relation origin kind is unsupported");
    }
  });

  properties.records.forEach((property, index) => {
    const domainId = requireNonEmptyString(
      property.domain_type_id,
      `candidate OntologySpec property ${index + 1} domain`,
    );
    if (!entities.ids.has(domainId)) {
      throw new Error("candidate OntologySpec property domain must resolve to an entity");
    }
    const originKind = requireNonEmptyString(
      property.origin_kind,
      `candidate OntologySpec property ${index + 1} origin kind`,
    );
    const originRefId = requireNonEmptyString(
      property.origin_ref_id,
      `candidate OntologySpec property ${index + 1} origin ref`,
    );
    if (originKind !== "knowledge_suggestion") {
      throw new Error("candidate OntologySpec property origin kind is unsupported");
    }
    if (!suggestionIdSet.has(originRefId)) {
      throw new Error("candidate OntologySpec property origin suggestion must resolve in the pack");
    }
  });

  const propertiesById = new Map(
    properties.records.map((property) => [property.property_type_id, property]),
  );
  rules.records.forEach((rule, ruleIndex) => {
    const subjectId = requireNonEmptyString(
      rule.subject_type_id,
      `candidate OntologySpec rule ${ruleIndex + 1} subject`,
    );
    if (!entities.ids.has(subjectId)) {
      throw new Error("candidate OntologySpec rule subject must resolve to an entity");
    }
    requireArray(
      rule.conditions,
      `candidate OntologySpec rule ${ruleIndex + 1} conditions`,
    ).forEach((condition, conditionIndex) => {
      const conditionRecord = requireRecord(
        condition,
        `candidate OntologySpec rule ${ruleIndex + 1} condition ${conditionIndex + 1}`,
      );
      const propertyTypeId = requireNonEmptyString(
        conditionRecord.property_type_id,
        `candidate OntologySpec rule ${ruleIndex + 1} condition ${conditionIndex + 1} property`,
      );
      if (!properties.ids.has(propertyTypeId)) {
        throw new Error("candidate OntologySpec rule condition property must resolve");
      }
      if (propertiesById.get(propertyTypeId).domain_type_id !== subjectId) {
        throw new Error("candidate OntologySpec rule condition property domain must match the subject");
      }
    });
    const originSuggestionId = requireNonEmptyString(
      rule.origin_suggestion_id,
      `candidate OntologySpec rule ${ruleIndex + 1} origin suggestion`,
    );
    if (!suggestionIdSet.has(originSuggestionId)) {
      throw new Error("candidate OntologySpec rule origin suggestion must resolve in the pack");
    }
  });

  return rules.records;
}

function adaptValidationReceipt(envelopeValue, authority, factsHash, facts, label) {
  const envelope = requireRecord(envelopeValue, `${label} receipt envelope`);
  const contentHash = requireHash(envelope.content_hash, `${label} receipt content hash`);
  const receipt = requireRecord(envelope.receipt, `${label} receipt`);
  requireValue(receipt.schema, "validation_receipt.v1", `${label} receipt schema`);

  const decisionPackContentHash = requireHash(
    receipt.decision_pack_content_hash,
    `${label} receipt DecisionPack hash`,
  );
  const ontologySpecContentHash = requireHash(
    receipt.ontology_spec_content_hash,
    `${label} receipt OntologySpec hash`,
  );
  const receiptFactsHash = requireHash(receipt.facts_content_hash, `${label} receipt facts hash`);
  if (decisionPackContentHash !== authority.decisionPackHash) {
    throw new Error(`${label} receipt DecisionPack hash must match validation authority`);
  }
  if (ontologySpecContentHash !== authority.ontologySpecHash) {
    throw new Error(`${label} receipt OntologySpec hash must match validation authority`);
  }
  if (receiptFactsHash !== factsHash) {
    throw new Error(`${label} receipt facts hash must match the case facts hash`);
  }

  const evaluationPairs = new Map([
    ["pass", "in_queue"],
    ["fail", "not_in_queue"],
    ["not_evaluable", "information_insufficient"],
    ["unsupported", "unsupported"],
  ]);
  if (!evaluationPairs.has(receipt.evaluation_status)) {
    throw new Error(`${label} receipt evaluation status is invalid`);
  }
  if (evaluationPairs.get(receipt.evaluation_status) !== receipt.decision_result) {
    throw new Error(`${label} receipt evaluation pair is invalid`);
  }

  const ruleId = requireNonEmptyString(receipt.rule_id, `${label} receipt rule ID`);
  const matchingRules = authority.rules.filter((rule, index) => {
    const ruleRecord = requireRecord(rule, `${label} authority rule ${index + 1}`);
    return requireNonEmptyString(ruleRecord.rule_id, `${label} authority rule ${index + 1} ID`) === ruleId;
  });
  if (matchingRules.length !== 1) {
    throw new Error(`${label} receipt rule ID must resolve exactly once`);
  }
  const rule = matchingRules[0];
  const conditionPropertyIds = requireArray(rule.conditions, `${label} receipt rule conditions`)
    .map((condition, index) => {
      const conditionRecord = requireRecord(condition, `${label} receipt rule condition ${index + 1}`);
      return requireNonEmptyString(
        conditionRecord.property_type_id,
        `${label} receipt rule condition ${index + 1} property type ID`,
      );
    });
  if (!conditionPropertyIds.length || new Set(conditionPropertyIds).size !== conditionPropertyIds.length) {
    throw new Error(`${label} receipt rule condition property type IDs must be unique`);
  }
  const conditionFacts = conditionPropertyIds.map((propertyTypeId) => {
    const matches = facts.filter((fact) => fact.propertyTypeId === propertyTypeId);
    if (matches.length !== 1) {
      throw new Error(`${label} receipt fact refs must close over the rule conditions`);
    }
    return matches[0];
  });
  const factRefs = requireExactReferences(
    receipt.fact_refs,
    conditionFacts.map((fact) => fact.factRef),
    `${label} receipt fact refs`,
  );

  const originSuggestionId = requireNonEmptyString(
    rule.origin_suggestion_id,
    `${label} receipt origin suggestion ID`,
  );
  const originSuggestions = authority.suggestions.filter((suggestion) => (
    requireNonEmptyString(suggestion.suggestion_id, `${label} authority suggestion ID`)
    === originSuggestionId
  ));
  if (originSuggestions.length !== 1) {
    throw new Error(`${label} receipt origin suggestion must resolve exactly once`);
  }
  const suggestionSourceRefs = requireUniqueNonEmptyStrings(
    originSuggestions[0].source_ref_ids,
    `${label} receipt origin suggestion source refs`,
  );
  if (suggestionSourceRefs.some((sourceRef) => !authority.sourceRefs.includes(sourceRef))) {
    throw new Error(`${label} receipt origin suggestion source refs must resolve in the DecisionPack`);
  }
  const expectedEvidenceRefs = [
    ...conditionFacts.flatMap((fact) => fact.evidenceRefs),
    ...suggestionSourceRefs,
  ];
  const evidenceRefs = requireExactReferences(
    receipt.evidence_refs,
    expectedEvidenceRefs,
    `${label} receipt evidence refs`,
  );
  requireValue(receipt.draft_created, false, `${label} receipt draft created`);
  requireValue(receipt.published, false, `${label} receipt published`);
  requireValue(receipt.actions_executed, false, `${label} receipt actions executed`);
  requireValue(receipt.external_write, false, `${label} receipt external write`);

  return {
    schema: receipt.schema,
    contentHash,
    evaluationStatus: receipt.evaluation_status,
    decisionResult: receipt.decision_result,
    ruleId,
    factRefs,
    evidenceRefs,
    decisionPackContentHash,
    ontologySpecContentHash,
    factsContentHash: receiptFactsHash,
    boundaries: {
      draftCreated: receipt.draft_created,
      published: receipt.published,
      actionsExecuted: receipt.actions_executed,
      externalWrite: receipt.external_write,
    },
  };
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
  const baselineSuggestions = collectPackSuggestions(pack, "DecisionPack");
  const baselineSourceRefs = collectPackSourceRefs(pack, "DecisionPack");
  const governanceStatuses = [
    ...new Set(baselineSuggestions.map((suggestion) => suggestion.governance_status)),
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
  const baselineRules = requireArray(spec.rule_declarations, "OntologySpec rules");
  const ontologyWorkspace = projectOntologyWorkspace(artifact);

  const validationRun = requireRecord(artifact.validation_run, "validation run");
  requireValue(validationRun.schema, "validation_run.v1", "validation run schema");
  const runtime = requireRecord(validationRun.runtime, "validation runtime");
  requireValue(runtime.mode, "recorded_deterministic", "validation runtime mode");
  requireValue(runtime.network_access, false, "validation runtime network access");
  requireValue(runtime.external_writes, false, "validation runtime external writes");
  const evaluator = requireNonEmptyString(runtime.evaluator, "validation runtime evaluator");

  const runStatus = requireRecord(validationRun.run_status, "validation run status");
  requireValue(runStatus.validation, "completed", "validation run status");
  requireValue(runStatus.review, "not_started", "validation review status");
  requireValue(runStatus.publication, "not_started", "validation publication status");
  requireValue(runStatus.action, "not_started", "validation action status");
  requireValue(runStatus.external_write, false, "validation run external write");

  const validationAuthority = requireRecord(validationRun.authority, "validation authority");
  requireValue(
    validationAuthority.evidence_scope,
    "synthetic_demo",
    "validation authority evidence scope",
  );
  const baselineAuthority = requireRecord(validationAuthority.baseline, "baseline authority");
  const baselinePackAuthority = requireRecord(
    baselineAuthority.decision_pack,
    "baseline DecisionPack authority",
  );
  const baselineSpecAuthority = requireRecord(
    baselineAuthority.ontology_spec,
    "baseline OntologySpec authority",
  );
  requireValue(baselinePackAuthority.artifact_ref, "#/decision_pack", "baseline DecisionPack ref");
  requireValue(baselineSpecAuthority.artifact_ref, "#/ontology_spec", "baseline OntologySpec ref");
  const baselinePackHash = requireHash(
    baselinePackAuthority.content_hash,
    "baseline DecisionPack hash",
  );
  const baselineSpecHash = requireHash(
    baselineSpecAuthority.content_hash,
    "baseline OntologySpec hash",
  );
  if (baselinePackHash !== packHash) {
    throw new Error("baseline DecisionPack hash must match the top-level DecisionPack hash");
  }
  if (baselineSpecHash !== specHash) {
    throw new Error("baseline OntologySpec hash must match the top-level OntologySpec hash");
  }

  const candidateAuthority = requireRecord(validationAuthority.candidate, "candidate authority");
  const candidatePackAuthority = requireRecord(
    candidateAuthority.decision_pack,
    "candidate DecisionPack authority",
  );
  const candidatePackHash = requireHash(
    candidatePackAuthority.content_hash,
    "candidate DecisionPack hash",
  );
  if (candidatePackHash === baselinePackHash) {
    throw new Error("candidate DecisionPack hash must differ from the baseline hash");
  }
  const candidatePack = requireRecord(candidatePackAuthority.pack, "candidate DecisionPack");
  requireValue(candidatePack.schema, "decision_pack.v1", "candidate DecisionPack schema");
  const candidateSuggestions = collectPackSuggestions(candidatePack, "candidate DecisionPack");
  if (
    !candidateSuggestions.length
    || candidateSuggestions.some((suggestion) => suggestion.governance_status !== "candidate")
  ) {
    throw new Error("candidate DecisionPack knowledge must keep candidate governance");
  }
  const candidateSourceRefs = collectPackSourceRefs(candidatePack, "candidate DecisionPack");
  const candidateSpecAuthority = requireRecord(
    candidateAuthority.ontology_spec,
    "candidate OntologySpec authority",
  );
  const candidateSpecHash = requireHash(
    candidateSpecAuthority.content_hash,
    "candidate OntologySpec hash",
  );
  if (candidateSpecHash === baselineSpecHash) {
    throw new Error("candidate OntologySpec hash must differ from the baseline hash");
  }
  const candidateSpec = requireRecord(candidateSpecAuthority.spec, "candidate OntologySpec");
  requireValue(candidateSpec.schema, "ontology_spec.v1", "candidate OntologySpec schema");
  requireValue(
    candidateSpec.evidence_scope,
    "synthetic_demo",
    "candidate OntologySpec evidence scope",
  );
  requireValue(candidateSpec.stage, "draft", "candidate OntologySpec stage");
  requireValue(
    candidateSpec.governance_status,
    "candidate",
    "candidate OntologySpec governance",
  );
  const candidateSpecPackHash = requireHash(
    candidateSpec.pack_content_hash,
    "candidate OntologySpec pack hash",
  );
  if (candidateSpecPackHash !== candidatePackHash) {
    throw new Error("candidate OntologySpec pack hash must match the candidate DecisionPack hash");
  }
  const candidateRules = validateCandidateReferenceClosure(
    candidatePack,
    candidateSpec,
    candidateSuggestions,
    candidateSourceRefs,
  );

  const cases = requireArray(validationRun.cases, "validation cases");
  if (cases.length !== 4) throw new Error("validation cases must contain exactly four cases");
  const subjectKeys = new Set();
  const validationCases = cases.map((caseValue, index) => {
    const validationCase = requireRecord(caseValue, `validation case ${index + 1}`);
    const subjectId = requireNonEmptyString(
      validationCase.subject_id,
      `validation case ${index + 1} subject`,
    );
    const subjectKey = caseInsensitiveKey(subjectId);
    if (subjectKeys.has(subjectKey)) {
      throw new Error("validation case subjects must be unique");
    }
    subjectKeys.add(subjectKey);
    const factsEnvelope = requireRecord(validationCase.facts, `validation case ${index + 1} facts`);
    const factsHash = requireHash(
      factsEnvelope.content_hash,
      `validation case ${index + 1} facts hash`,
    );
    const factSet = requireRecord(factsEnvelope.fact_set, `validation case ${index + 1} fact set`);
    requireValue(factSet.schema, "synthetic_fact_set.v1", `validation case ${index + 1} facts schema`);
    requireValue(
      factSet.evidence_scope,
      "synthetic_demo",
      `validation case ${index + 1} facts evidence scope`,
    );
    requireValue(factSet.subject_id, subjectId, `validation case ${index + 1} facts subject`);
    const facts = requireArray(factSet.facts, `validation case ${index + 1} facts`);
    const validatedFacts = facts.map((fact, factIndex) => {
      const factRecord = requireRecord(fact, `${subjectId} fact ${factIndex + 1}`);
      const availability = requireNonEmptyString(
        factRecord.availability,
        `${subjectId} fact ${factIndex + 1} availability`,
      );
      if (!["available", "unavailable"].includes(availability)) {
        throw new Error(`${subjectId} fact ${factIndex + 1} availability is invalid`);
      }
      if (availability === "available") {
        requireNonEmptyString(factRecord.value, `${subjectId} fact ${factIndex + 1} value`);
      } else {
        requireValue(factRecord.value, null, `${subjectId} fact ${factIndex + 1} value`);
      }
      return {
        factRef: requireNonEmptyString(factRecord.fact_ref, `${subjectId} fact ${factIndex + 1} ref`),
        propertyTypeId: requireNonEmptyString(
          factRecord.property_type_id,
          `${subjectId} fact ${factIndex + 1} property type ID`,
        ),
        evidenceRefs: requireCaseInsensitiveUniqueNonEmptyStrings(
          factRecord.evidence_refs,
          `${subjectId} fact ${factIndex + 1} evidence refs`,
        ),
        availability,
        value: factRecord.value,
      };
    });
    const factRefs = validatedFacts.map((fact) => fact.factRef);
    if (new Set(factRefs.map(caseInsensitiveKey)).size !== factRefs.length) {
      throw new Error(`${subjectId} fact refs must be unique`);
    }
    const propertyTypeIds = validatedFacts.map((fact) => fact.propertyTypeId);
    if (new Set(propertyTypeIds.map(caseInsensitiveKey)).size !== propertyTypeIds.length) {
      throw new Error(`${subjectId} property type IDs must be unique`);
    }
    const baseline = adaptValidationReceipt(
      validationCase.baseline,
      {
        decisionPackHash: baselinePackHash,
        ontologySpecHash: baselineSpecHash,
        rules: baselineRules,
        suggestions: baselineSuggestions,
        sourceRefs: baselineSourceRefs,
      },
      factsHash,
      validatedFacts,
      `${subjectId} baseline`,
    );
    const candidate = adaptValidationReceipt(
      validationCase.candidate,
      {
        decisionPackHash: candidatePackHash,
        ontologySpecHash: candidateSpecHash,
        rules: candidateRules,
        suggestions: candidateSuggestions,
        sourceRefs: candidateSourceRefs,
      },
      factsHash,
      validatedFacts,
      `${subjectId} candidate`,
    );
    const resultChanged =
      baseline.evaluationStatus !== candidate.evaluationStatus
      || baseline.decisionResult !== candidate.decisionResult;
    const hasAtRiskFact = validatedFacts.some((fact) => fact.value === "at_risk");

    return {
      subjectId,
      facts: {
        schema: factSet.schema,
        evidenceScope: factSet.evidence_scope,
        contentHash: factsHash,
        items: facts,
      },
      baseline,
      candidate,
      atRiskChange: resultChanged && hasAtRiskFact,
    };
  });
  const changedCases = validationCases.filter((validationCase) => (
    validationCase.baseline.evaluationStatus !== validationCase.candidate.evaluationStatus
    || validationCase.baseline.decisionResult !== validationCase.candidate.decisionResult
  ));
  const fixedDelta = changedCases[0];
  if (
    changedCases.length !== 1
    || !fixedDelta.atRiskChange
    || fixedDelta.baseline.evaluationStatus !== "fail"
    || fixedDelta.baseline.decisionResult !== "not_in_queue"
    || fixedDelta.candidate.evaluationStatus !== "pass"
    || fixedDelta.candidate.decisionResult !== "in_queue"
  ) {
    throw new Error("validation delta must be the unique at_risk fail-to-pass transition");
  }

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
        status: "receipt_recorded",
        data: {
          runtimeAuthority: {
            evaluator,
            mode: runtime.mode,
            networkAccess: runtime.network_access,
            externalWrites: runtime.external_writes,
          },
          authority: {
            baseline: {
              decisionPackHash: baselinePackHash,
              ontologySpecHash: baselineSpecHash,
            },
            candidate: {
              decisionPackHash: candidatePackHash,
              ontologySpecHash: candidateSpecHash,
            },
          },
          cases: validationCases,
          boundaries: {
            review: runStatus.review,
            publication: runStatus.publication,
            action: runStatus.action,
            externalWrite: runStatus.external_write,
          },
        },
      },
    ],
  };
}
