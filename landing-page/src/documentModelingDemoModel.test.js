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

test("defines exactly three synthetic presets with one compiled route and two previews", () => {
  const { DOCUMENT_MODELING_PRESETS } = requireModel();

  assert.equal(DOCUMENT_MODELING_PRESETS.length, 3);
  assert.deepEqual(
    DOCUMENT_MODELING_PRESETS.map(({ id }) => id),
    ["supply-chain-order-intervention", "supplier-qualification-change", "dairy-rd-fallback"],
  );
  assert.ok(DOCUMENT_MODELING_PRESETS.every(({ evidenceScope }) => evidenceScope === "synthetic_demo"));
  assert.deepEqual(
    DOCUMENT_MODELING_PRESETS.map(({ mode }) => mode),
    ["compiled_artifact", "scenario_preview", "scenario_preview"],
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
  const preset = DOCUMENT_MODELING_PRESETS[1];

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
