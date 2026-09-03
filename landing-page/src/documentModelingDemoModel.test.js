import assert from "node:assert/strict";
import test from "node:test";

let model = null;
try {
  model = await import("./documentModelingDemoModel.js");
} catch {
  // RED starts with the production module absent.
}

function requireModel() {
  assert.ok(model, "document modeling demo model must exist");
  return model;
}

test("opens the quality temporary-control Phase 1 scenario by default without removing existing presets", () => {
  const { DOCUMENT_MODELING_PRESETS } = requireModel();

  assert.equal(DOCUMENT_MODELING_PRESETS.length, 4);
  assert.deepEqual(
    DOCUMENT_MODELING_PRESETS.map(({ id }) => id),
    ["quality-temporary-control", "supply-chain-order-intervention", "supplier-qualification-change", "dairy-rd-fallback"],
  );
  assert.equal(DOCUMENT_MODELING_PRESETS[0].productMode, "phase1_decision_modeling");
  assert.equal(DOCUMENT_MODELING_PRESETS[0].decisionOwner, "质量负责人");
  assert.match(DOCUMENT_MODELING_PRESETS[0].decision, /临时控制或复检队列/);
  assert.ok(DOCUMENT_MODELING_PRESETS.every(({ evidenceScope }) => evidenceScope === "synthetic_demo"));
  assert.deepEqual(
    DOCUMENT_MODELING_PRESETS.map(({ mode }) => mode),
    ["scenario_preview", "compiled_artifact", "scenario_preview", "scenario_preview"],
  );
});

test("starts the quality scenario from one event and keeps cross-source records and gaps explicit", () => {
  const { DOCUMENT_MODELING_PRESETS } = requireModel();
  const preset = DOCUMENT_MODELING_PRESETS[0];

  assert.deepEqual(preset.event, {
    id: "QI-DEMO-017",
    signal: "终检发现泄漏率异常",
    status: "待调查",
    detectedAt: "2026-08-04 09:10",
  });
  assert.equal(preset.investigationQuestion, "该异常与哪些批次、在制品和待发运件有关，哪条关键链路仍然缺失？");
  assert.deepEqual(
    preset.sourceRecords.map(({ sourceSystem, status }) => [sourceSystem, status]),
    [
      ["QMS_SYNTHETIC", "available"],
      ["MES_SYNTHETIC", "available"],
      ["WMS_SYNTHETIC", "available"],
      ["PLM_SYNTHETIC", "missing"],
    ],
  );

  const availableRecordIds = new Set(
    preset.sourceRecords
      .filter(({ status }) => status === "available")
      .map(({ id }) => id),
  );
  for (const candidate of [...preset.entityTypes, ...preset.relationTypes]) {
    assert.ok(availableRecordIds.has(candidate.evidenceRef), `${candidate.id} must bind to an available source record`);
  }

  const gaps = preset.sourceRecords.filter(({ status }) => status === "missing");
  assert.equal(gaps.length, 1);
  assert.equal(gaps[0].label, "项目与产品映射");
  assert.doesNotMatch(JSON.stringify(preset.sourceRecords), /confirmed|possible|excluded|not_evaluable/);
});

test("builds a source-grounded Phase 1 candidate DecisionPack from FDE selections", () => {
  const { DOCUMENT_MODELING_PRESETS, buildPhase1DecisionPack } = requireModel();
  const preset = DOCUMENT_MODELING_PRESETS[0];

  const pack = buildPhase1DecisionPack(preset, {
    selectedEntityIds: preset.entityTypes.map(({ id }) => id),
    selectedRelationIds: preset.relationTypes.map(({ id }) => id),
    reviewNote: "保留在制品与待发运件，客户侧对象等待项目映射。",
  });

  assert.equal(pack.schema, "decision_pack.phase1_candidate.v1");
  assert.equal(pack.status, "candidate");
  assert.equal(pack.evidence_scope, "synthetic_demo");
  assert.deepEqual(pack.decision, {
    question: preset.decision,
    owner: preset.decisionOwner,
    trigger: preset.trigger,
  });
  assert.equal(pack.objects.length, 4);
  assert.equal(pack.relations.length, 3);
  assert.ok(pack.objects.every(({ evidence_span }) => preset.documentText.includes(evidence_span)));
  assert.ok(pack.relations.every(({ evidence_span }) => preset.documentText.includes(evidence_span)));
  assert.equal(pack.fde_review.note, "保留在制品与待发运件，客户侧对象等待项目映射。");
  assert.deepEqual(pack.delivery_boundary, {
    session_only: true,
    published: false,
    external_action_created: false,
  });
});

test("rejects a selected relation when its endpoint is excluded", () => {
  const { DOCUMENT_MODELING_PRESETS, buildPhase1DecisionPack } = requireModel();
  const preset = DOCUMENT_MODELING_PRESETS[0];

  assert.throws(
    () => buildPhase1DecisionPack(preset, {
      selectedEntityIds: preset.entityTypes.slice(1).map(({ id }) => id),
      selectedRelationIds: [preset.relationTypes[0].id],
      reviewNote: "",
    }),
    /selected relation endpoints/,
  );
});

test("keeps every candidate relation closed over preset entity endpoints", () => {
  const { DOCUMENT_MODELING_PRESETS } = requireModel();

  for (const preset of DOCUMENT_MODELING_PRESETS) {
    const entityIds = new Set(preset.entityTypes.map(({ id }) => id));
    assert.ok(preset.entityTypes.length > 0);
    assert.ok(preset.relationTypes.length > 0);
    assert.ok(preset.boundary.length > 0);
    for (const relation of preset.relationTypes) {
      assert.ok(entityIds.has(relation.source), `${relation.id} source must exist`);
      assert.ok(entityIds.has(relation.target), `${relation.id} target must exist`);
    }
  }
});

test("resolves each unchanged preset to its explicit route", () => {
  const { DOCUMENT_MODELING_PRESETS, resolveDocumentModelingRequest } = requireModel();

  for (const preset of DOCUMENT_MODELING_PRESETS) {
    const result = resolveDocumentModelingRequest(preset.id, preset.documentText);
    assert.equal(result.status, "resolved");
    assert.equal(result.mode, preset.mode);
    assert.equal(result.preset.id, preset.id);
  }
});

test("normalizes outer whitespace without changing the preset match", () => {
  const { DOCUMENT_MODELING_PRESETS, resolveDocumentModelingRequest } = requireModel();
  const preset = DOCUMENT_MODELING_PRESETS[0];

  const result = resolveDocumentModelingRequest(preset.id, `\n  ${preset.documentText}  \n`);

  assert.equal(result.status, "resolved");
  assert.equal(result.mode, "scenario_preview");
});

test("returns unsupported when preset text is edited", () => {
  const { DOCUMENT_MODELING_PRESETS, resolveDocumentModelingRequest } = requireModel();
  const preset = DOCUMENT_MODELING_PRESETS[0];

  const result = resolveDocumentModelingRequest(preset.id, `${preset.documentText} 已修改`);

  assert.deepEqual(result, { status: "unsupported", mode: "unsupported" });
});

test("returns unsupported for an unknown scenario instead of choosing the closest preset", () => {
  const { DOCUMENT_MODELING_PRESETS, resolveDocumentModelingRequest } = requireModel();

  const result = resolveDocumentModelingRequest("supplier-qualification", DOCUMENT_MODELING_PRESETS[1].documentText);

  assert.deepEqual(result, { status: "unsupported", mode: "unsupported" });
});

test("preview definitions contain no hash or validation receipt claims", () => {
  const { DOCUMENT_MODELING_PRESETS } = requireModel();
  const previewJson = JSON.stringify(DOCUMENT_MODELING_PRESETS.filter(({ mode }) => mode === "scenario_preview"));

  assert.doesNotMatch(previewJson, /hash|validation.?receipt|customer|客户/i);
});
