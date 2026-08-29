const SHA256 = /^[0-9a-f]{64}$/;

const ENTITY_POSITIONS = {
  supplier: { x: 54, y: 72 },
  material: { x: 384, y: 184 },
  customer_order: { x: 54, y: 304 },
};

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

function requireString(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} must be a string`);
  return value;
}

function requireHash(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new Error(`${label} must be a backend SHA-256 hash`);
  }
  return value;
}

function sorted(values, field, label) {
  const result = [...requireArray(values, label)].sort((left, right) =>
    requireString(left[field], `${label} ${field}`).localeCompare(
      requireString(right[field], `${label} ${field}`),
    ),
  );
  const ids = result.map((item) => item[field]);
  if (new Set(ids).size !== ids.length) throw new Error(`${label} must have unique ${field}`);
  return result;
}

function originalIndexById(values, field, label) {
  const indexes = new Map();
  requireArray(values, label).forEach((item, index) => {
    const id = requireString(item[field], `${label} ${field}`);
    if (indexes.has(id)) throw new Error(`${label} must have unique ${field}`);
    indexes.set(id, index);
  });
  return indexes;
}

function canonicalPointer(collection, index) {
  return `/ontology_spec/spec/${collection}/${index}`;
}

function sourceHandle(predicate) {
  return `source-${predicate.toLowerCase().replaceAll("_", "-")}`;
}

function targetHandle(predicate) {
  return `target-${predicate.toLowerCase().replaceAll("_", "-")}`;
}

function sourceStatus(originKind) {
  return originKind === "provided_input" ? "provided_scenario_input" : "resolved_source";
}

function providedCaveat(kind) {
  if (kind === "relation") {
    return "No external source; declared by the provided scenario bridge.";
  }
  return "No external source; declared by the provided scenario input.";
}

function resolveOriginSources(originKind, originRefId, suggestionsById, bindingsById, kind) {
  if (originKind === "knowledge_suggestion") {
    const suggestion = suggestionsById.get(originRefId);
    if (!suggestion) throw new Error(`${kind} origin suggestion ${originRefId} is missing`);
    return {
      sourceStatus: "resolved_source",
      sourceCaveat: suggestion.sources.map(({ caveat }) => caveat).join(" "),
      sources: suggestion.sources,
    };
  }

  if (originKind === "provided_input") {
    if (kind === "entity" && !bindingsById.has(originRefId)) {
      throw new Error(`entity origin binding ${originRefId} is missing`);
    }
    return {
      sourceStatus: kind === "relation" ? "provided_scenario_bridge" : sourceStatus(originKind),
      sourceCaveat: providedCaveat(kind),
      sources: [],
    };
  }

  throw new Error(`${kind} origin_kind ${originKind} is unsupported`);
}

function createSourceIndex(pack) {
  const sourceIndexes = originalIndexById(
    pack.source_refs,
    "source_ref_id",
    "DecisionPack source refs",
  );
  const sourceRefs = sorted(pack.source_refs, "source_ref_id", "DecisionPack source refs");
  const sourcesById = new Map(
    sourceRefs.map((source) => {
      const sourceRefId = requireString(source.source_ref_id, "source_ref_id");
      return [sourceRefId, {
        id: sourceRefId,
        kind: requireString(source.source_kind, `source ${sourceRefId} kind`),
        title: requireString(source.title, `source ${sourceRefId} title`),
        caveat: requireString(source.caveat, `source ${sourceRefId} caveat`),
        locator: requireString(source.locator, `source ${sourceRefId} locator`),
        revision: requireString(source.revision, `source ${sourceRefId} revision`),
        pointer: `/decision_pack/pack/source_refs/${sourceIndexes.get(sourceRefId)}`,
      }];
    }),
  );

  const outcomes = requireArray(pack.knowledge_outcomes, "DecisionPack outcomes");
  const suggestions = outcomes.flatMap((outcome, outcomeIndex) =>
    requireArray(outcome.suggestions, "DecisionPack outcome suggestions")
      .map((suggestion, suggestionIndex) => ({
        suggestion,
        pointer: `/decision_pack/pack/knowledge_outcomes/${outcomeIndex}/suggestions/${suggestionIndex}`,
      })),
  ).sort((left, right) => left.suggestion.suggestion_id.localeCompare(right.suggestion.suggestion_id));
  const suggestionIds = suggestions.map(({ suggestion: { suggestion_id: id } }) => id);
  if (new Set(suggestionIds).size !== suggestionIds.length) {
    throw new Error("DecisionPack suggestions must have unique suggestion_id");
  }

  const suggestionsById = new Map(suggestions.map(({ suggestion, pointer }) => {
    const suggestionId = requireString(suggestion.suggestion_id, "suggestion_id");
    const sources = requireArray(
      suggestion.source_ref_ids,
      `suggestion ${suggestionId} source refs`,
    ).map((sourceRefId) => {
      const source = sourcesById.get(sourceRefId);
      if (!source) throw new Error(`suggestion ${suggestionId} source reference ${sourceRefId} is missing`);
      return source;
    }).sort((left, right) => left.id.localeCompare(right.id));
    return [suggestionId, {
      id: suggestionId,
      semanticKey: requireString(suggestion.semantic_key, `suggestion ${suggestionId} semantic key`),
      pointer,
      sources,
    }];
  }));

  return { suggestionsById };
}

function refusal(reason, workspace, language) {
  const answers = {
    zh: {
      missing_runtime_facts: "当前 artifact 只有类型、关系与 candidate rule，没有订单或供应商实例、运行事实或 Validation 结果，因此不能回答该问题。",
      unsupported_question: "该问题不属于当前 artifact 可确定性回答的实体/关系、candidate rule 或需复核内容，系统不会猜测。",
      prompt_injection: "该输入要求越过确定性 artifact 查询边界，已拒绝执行；系统不会披露提示或编造业务结论。",
    },
    en: {
      missing_runtime_facts: "This artifact contains types, relations, and a candidate rule only. It has no order or supplier instances, runtime facts, or Validation result, so the question cannot be answered.",
      unsupported_question: "This question is outside the entity/relation, candidate-rule, and review-item intents supported by the artifact. No answer will be guessed.",
      prompt_injection: "The input attempts to cross the deterministic artifact-query boundary. It was refused; prompts and business conclusions will not be fabricated.",
    },
  };
  return {
    answerable: false,
    intent: null,
    reason,
    answer: answers[language]?.[reason] ?? answers.en[reason],
    packHash: workspace.packHash,
    specHash: workspace.specHash,
    evidence: [],
  };
}

export function projectOntologyWorkspace(input) {
  const artifact = requireRecord(input, "artifact");
  const packEnvelope = requireRecord(artifact.decision_pack, "DecisionPack envelope");
  const packHash = requireHash(packEnvelope.content_hash, "DecisionPack hash");
  const pack = requireRecord(packEnvelope.pack, "DecisionPack");
  const specEnvelope = requireRecord(artifact.ontology_spec, "OntologySpec envelope");
  const specHash = requireHash(specEnvelope.content_hash, "OntologySpec hash");
  const spec = requireRecord(specEnvelope.spec, "OntologySpec");
  if (spec.schema !== "ontology_spec.v1") throw new Error("OntologySpec schema must be ontology_spec.v1");
  if (spec.pack_content_hash !== packHash) throw new Error("OntologySpec pack hash must match DecisionPack hash");

  const { suggestionsById } = createSourceIndex(pack);
  const bindings = sorted(pack.input_bindings, "binding_id", "DecisionPack input bindings");
  const bindingsById = new Map(bindings.map((binding) => [binding.binding_id, binding]));
  const entityTypeIndexes = originalIndexById(spec.entity_types, "type_id", "OntologySpec entity types");
  const relationTypeIndexes = originalIndexById(spec.relation_types, "relation_type_id", "OntologySpec relation types");
  const propertyTypeIndexes = originalIndexById(spec.property_types, "property_type_id", "OntologySpec property types");
  const ruleIndexes = originalIndexById(spec.rule_declarations, "rule_id", "OntologySpec rules");
  const compilationIssueIndexes = originalIndexById(
    spec.compilation_issues,
    "issue_id",
    "OntologySpec compilation issues",
  );
  const entityTypes = sorted(spec.entity_types, "type_id", "OntologySpec entity types");
  const relationTypes = sorted(spec.relation_types, "relation_type_id", "OntologySpec relation types");
  const propertyTypes = sorted(spec.property_types, "property_type_id", "OntologySpec property types");
  const ruleDeclarations = sorted(spec.rule_declarations, "rule_id", "OntologySpec rules");
  const compilationIssues = sorted(
    spec.compilation_issues,
    "issue_id",
    "OntologySpec compilation issues",
  );
  const entityIds = new Set(entityTypes.map(({ type_id: id }) => id));

  for (const relation of relationTypes) {
    if (!entityIds.has(relation.domain_type_id) || !entityIds.has(relation.range_type_id)) {
      throw new Error(`relation endpoint is missing for ${relation.relation_type_id}`);
    }
  }
  for (const property of propertyTypes) {
    if (!entityIds.has(property.domain_type_id)) {
      throw new Error(`property domain is missing for ${property.property_type_id}`);
    }
  }
  for (const rule of ruleDeclarations) {
    if (!entityIds.has(rule.subject_type_id)) {
      throw new Error(`rule subject is missing for ${rule.rule_id}`);
    }
  }

  const entityNodes = entityTypes.map((entity, index) => {
    const typeId = requireString(entity.type_id, "entity type id");
    const originKind = requireString(entity.origin_kind, `entity ${typeId} origin kind`);
    const originRefId = requireString(entity.origin_ref_id, `entity ${typeId} origin ref`);
    const origin = resolveOriginSources(
      originKind,
      originRefId,
      suggestionsById,
      bindingsById,
      "entity",
    );
    const properties = propertyTypes.filter(({ domain_type_id: domain }) => domain === typeId)
      .map((property, propertyIndex) => ({
        id: property.property_type_id,
        semanticKey: property.semantic_key,
        valueType: property.value_type,
        governanceStatus: property.governance_status,
        originKind: property.origin_kind,
        originRefId: property.origin_ref_id,
        pointer: canonicalPointer("property_types", propertyTypeIndexes.get(property.property_type_id)),
        order: propertyIndex,
      }));
    return {
      id: typeId,
      type: "ontologyEntity",
      position: ENTITY_POSITIONS[entity.role_key] ?? { x: 54 + index * 240, y: 184 },
      draggable: false,
      connectable: false,
      selectable: true,
      data: {
        kind: "entity",
        label: requireString(entity.label, `entity ${typeId} label`),
        roleKey: requireString(entity.role_key, `entity ${typeId} role key`),
        semanticKey: requireString(entity.semantic_key, `entity ${typeId} semantic key`),
        governanceStatus: requireString(entity.governance_status, `entity ${typeId} governance`),
        originKind,
        originRefId,
        pointer: canonicalPointer("entity_types", entityTypeIndexes.get(typeId)),
        properties,
        inputHandles: [],
        outputHandles: [],
        ...origin,
      },
    };
  });

  const entitiesById = new Map(entityNodes.map((node) => [node.id, node]));
  const relationEdges = relationTypes.map((relation, index) => {
    const relationId = requireString(relation.relation_type_id, "relation type id");
    const predicate = requireString(relation.predicate, `relation ${relationId} predicate`);
    const originKind = requireString(relation.origin_kind, `relation ${relationId} origin kind`);
    const originRefId = requireString(relation.origin_ref_id, `relation ${relationId} origin ref`);
    const origin = resolveOriginSources(
      originKind,
      originRefId,
      suggestionsById,
      bindingsById,
      "relation",
    );
    return {
      id: relationId,
      source: relation.domain_type_id,
      target: relation.range_type_id,
      sourceHandle: sourceHandle(predicate),
      targetHandle: targetHandle(predicate),
      type: "smoothstep",
      label: predicate,
      selectable: true,
      focusable: true,
      deletable: false,
      animated: false,
      markerEnd: { type: "arrowclosed", color: "#1757dc" },
      style: { stroke: "#1757dc", strokeWidth: 1.7 },
      labelStyle: { fill: "#0a0b0d", fontSize: 9, fontWeight: 800 },
      labelBgStyle: { fill: "#f8f7f1", fillOpacity: 0.96 },
      data: {
        kind: "relation",
        readOnly: true,
        predicate,
        semanticKey: requireString(relation.semantic_key, `relation ${relationId} semantic key`),
        description: requireString(relation.description, `relation ${relationId} description`),
        governanceStatus: requireString(relation.governance_status, `relation ${relationId} governance`),
        originKind,
        originRefId,
        pointer: canonicalPointer("relation_types", relationTypeIndexes.get(relationId)),
        triple: `${entitiesById.get(relation.domain_type_id).data.label} -[${predicate}]-> ${entitiesById.get(relation.range_type_id).data.label}`,
        ...origin,
      },
    };
  }).sort((left, right) => left.data.predicate.localeCompare(right.data.predicate));

  const propertiesById = new Map(propertyTypes.map((property) => [property.property_type_id, property]));
  const ruleNodes = ruleDeclarations.map((rule, index) => {
    const ruleId = requireString(rule.rule_id, "rule id");
    const originRefId = requireString(rule.origin_suggestion_id, `rule ${ruleId} origin suggestion`);
    const origin = resolveOriginSources(
      "knowledge_suggestion",
      originRefId,
      suggestionsById,
      bindingsById,
      "rule",
    );
    const conditions = [...requireArray(rule.conditions, `rule ${ruleId} conditions`)].map((condition) => {
      const property = propertiesById.get(condition.property_type_id);
      if (!property) throw new Error(`rule condition property ${condition.property_type_id} is missing`);
      return {
        propertyTypeId: condition.property_type_id,
        semanticKey: property.semantic_key,
        operator: condition.operator,
        allowedValues: [...requireArray(condition.allowed_values, "rule allowed values")].sort(),
      };
    }).sort((left, right) => left.semanticKey.localeCompare(right.semanticKey));
    return {
      id: ruleId,
      type: "ontologyRule",
      position: { x: 378, y: 342 + index * 148 },
      draggable: false,
      connectable: false,
      selectable: true,
      data: {
        kind: "rule",
        label: "CANDIDATE RULE",
        semanticKey: requireString(rule.semantic_key, `rule ${ruleId} semantic key`),
        ruleKind: requireString(rule.rule_kind, `rule ${ruleId} kind`),
        governanceStatus: requireString(rule.governance_status, `rule ${ruleId} governance`),
        originKind: "knowledge_suggestion",
        originRefId,
        pointer: canonicalPointer("rule_declarations", ruleIndexes.get(ruleId)),
        subjectTypeId: rule.subject_type_id,
        conditions,
        outputConclusionKey: rule.output_conclusion_key,
        positiveConclusionValue: rule.positive_conclusion_value,
        negativeConclusionValue: rule.negative_conclusion_value,
        description: rule.description,
        inputHandles: ["target-rule-subject"],
        outputHandles: [],
        ...origin,
      },
    };
  });

  const ruleEdges = ruleNodes.map((ruleNode) => ({
    id: `declares-${ruleNode.id}`,
    source: ruleNode.data.subjectTypeId,
    target: ruleNode.id,
    sourceHandle: "source-rule-declaration",
    targetHandle: "target-rule-subject",
    type: "smoothstep",
    label: "SUBJECT / RULE",
    selectable: true,
    focusable: true,
    deletable: false,
    animated: false,
    markerEnd: { type: "arrowclosed", color: "#0a0b0d" },
    style: { stroke: "#0a0b0d", strokeWidth: 1.4, strokeDasharray: "5 4" },
    labelStyle: { fill: "#0a0b0d", fontSize: 8, fontWeight: 800 },
    labelBgStyle: { fill: "#f8f7f1", fillOpacity: 0.96 },
    data: {
      kind: "rule_declaration",
      readOnly: true,
      semanticKey: ruleNode.data.semanticKey,
      governanceStatus: ruleNode.data.governanceStatus,
      originKind: ruleNode.data.originKind,
      originRefId: ruleNode.data.originRefId,
      pointer: ruleNode.data.pointer,
      triple: `${entitiesById.get(ruleNode.data.subjectTypeId).data.label} -[DECLARES_RULE]-> ${ruleNode.data.semanticKey}`,
      sourceStatus: ruleNode.data.sourceStatus,
      sourceCaveat: ruleNode.data.sourceCaveat,
      sources: ruleNode.data.sources,
    },
  }));

  for (const edge of [...relationEdges, ...ruleEdges]) {
    entitiesById.get(edge.source)?.data.outputHandles.push(edge.sourceHandle);
    entitiesById.get(edge.target)?.data.inputHandles.push(edge.targetHandle);
  }
  for (const node of entityNodes) {
    node.data.inputHandles.sort();
    node.data.outputHandles.sort();
  }

  const reviewIssues = compilationIssues.map((issue, index) => ({
    id: requireString(issue.issue_id, "compilation issue id"),
    code: requireString(issue.code, `compilation issue ${issue.issue_id} code`),
    message: requireString(issue.message, `compilation issue ${issue.issue_id} message`),
    payloadSchema: requireString(issue.payload_schema, `compilation issue ${issue.issue_id} payload schema`),
    severity: requireString(issue.severity, `compilation issue ${issue.issue_id} severity`),
    suggestionId: requireString(issue.suggestion_id, `compilation issue ${issue.issue_id} suggestion`),
    pointer: canonicalPointer("compilation_issues", compilationIssueIndexes.get(issue.issue_id)),
  }));
  const edges = [...relationEdges, ...ruleEdges];
  const nodes = [...entityNodes, ...ruleNodes];

  return {
    schema: "ontology_workspace.v1",
    packHash,
    specHash,
    evidenceScope: requireString(spec.evidence_scope, "OntologySpec evidence scope"),
    stage: requireString(spec.stage, "OntologySpec stage"),
    governanceStatus: requireString(spec.governance_status, "OntologySpec governance status"),
    entityNodes,
    relationEdges,
    ruleNodes,
    ruleEdges,
    nodes,
    edges,
    reviewIssues,
  };
}

export function answerArtifactQuestion(question, workspace, language = "zh") {
  requireRecord(workspace, "ontology workspace");
  const text = typeof question === "string" ? question.trim() : "";
  const normalized = text.toLowerCase();

  if (/忽略|系统提示|提示词|越过|jailbreak|ignore\s+(all|previous)|system\s+prompt|reveal\s+prompt/.test(normalized)) {
    return refusal("prompt_injection", workspace, language);
  }
  if (/执行|运行|校验|验证|发布|上线|部署|生效|持久化|存储|保存|落库|动作|写回|回写|\berp\b|\bactions?\b|\b(?:run|ran)\b|\bexecut(?:e|ed|es|ing|ion)\b|\bvalidat(?:e|ed|es|ing|ion)\b|\bpublish(?:ed|es|ing)?\b|\bpublication\b|\breleas(?:e|ed|es|ing)\b|\bdeploy(?:ed|ment|ing)?\b|\bpersist(?:ed|ence|ent|ing)?\b|\bstor(?:e|ed|age|ing)\b|\bsav(?:e|ed|ing)\b|\btak(?:e|en|ing)\s+effect\b|write[ -]?back/.test(normalized)) {
    return refusal("missing_runtime_facts", workspace, language);
  }
  if (/\b(?:rule|relation|schema)\b.{0,32}\blive\b|\blive\b.{0,32}\b(?:rule|relation|schema)\b/.test(normalized)) {
    return refusal("missing_runtime_facts", workspace, language);
  }
  if (/哪些.*订单|订单.*队列|供应商\s*[a-z0-9]+.*合格|实例|运行时|实时|实际|which\s+orders|supplier\s+[a-z0-9]+.*qualified|runtime|instance/.test(normalized)) {
    return refusal("missing_runtime_facts", workspace, language);
  }

  if (/复核|审查|需确认|review|compilation\s+issue/.test(normalized)) {
    const evidence = workspace.reviewIssues.map((issue) => ({
      pointer: issue.pointer,
      stableId: issue.id,
    }));
    const items = workspace.reviewIssues.map((issue) => `${issue.code}: ${issue.message}`).join("; ");
    const answer = language === "en"
      ? `${workspace.reviewIssues.length} compilation items require review: ${items}`
      : `共有 ${workspace.reviewIssues.length} 个编译项需要复核：${items}`;
    return {
      answerable: true,
      intent: "review_items",
      reason: null,
      answer,
      packHash: workspace.packHash,
      specHash: workspace.specHash,
      evidence,
    };
  }

  if (/candidate\s*rule|候选规则|规则是什么|规则|\brule\b/.test(normalized)) {
    const rule = workspace.ruleNodes[0];
    if (!rule) return refusal("unsupported_question", workspace, language);
    const conditions = rule.data.conditions.map((condition) =>
      `${condition.semanticKey} ${condition.operator} [${condition.allowedValues.join(", ")}]`,
    ).join(" AND ");
    const answer = language === "en"
      ? `The artifact declares one candidate ${rule.data.ruleKind} rule for the customer-order subject: ${conditions}; output ${rule.data.outputConclusionKey} becomes ${rule.data.positiveConclusionValue} when all conditions match, otherwise ${rule.data.negativeConclusionValue}.`
      : `artifact 声明了 1 条面向客户订单 subject 的 candidate ${rule.data.ruleKind} 规则：${conditions}；全部命中时 ${rule.data.outputConclusionKey} = ${rule.data.positiveConclusionValue}，否则为 ${rule.data.negativeConclusionValue}。`;
    return {
      answerable: true,
      intent: "candidate_rule",
      reason: null,
      answer,
      packHash: workspace.packHash,
      specHash: workspace.specHash,
      evidence: [{
        pointer: rule.data.pointer,
        stableId: rule.id,
        triple: workspace.ruleEdges[0]?.data.triple,
      }],
    };
  }

  if (/实体|关系|本体结构|entity|entities|relation|relations|schema/.test(normalized)) {
    const entities = workspace.entityNodes.map((node) => node.data.label).join("、");
    const triples = workspace.relationEdges.map((edge) => edge.data.triple).join("；");
    const answer = language === "en"
      ? `The draft contains ${workspace.entityNodes.length} entity types (${entities}) and ${workspace.relationEdges.length} relation types: ${triples}. These are schema declarations, not runtime instances.`
      : `该草案包含 ${workspace.entityNodes.length} 个实体类型（${entities}）和 ${workspace.relationEdges.length} 个关系类型：${triples}。这些是 schema 声明，不是运行实例。`;
    return {
      answerable: true,
      intent: "schema_overview",
      reason: null,
      answer,
      packHash: workspace.packHash,
      specHash: workspace.specHash,
      evidence: [
        ...workspace.entityNodes.map((node) => ({
          pointer: node.data.pointer,
          stableId: node.id,
        })),
        ...workspace.relationEdges.map((edge) => ({
          pointer: edge.data.pointer,
          stableId: edge.id,
          triple: edge.data.triple,
        })),
      ],
    };
  }

  return refusal("unsupported_question", workspace, language);
}
