import assert from "node:assert/strict";
import { test } from "node:test";

let model;
try { model = await import("./ontologyReferenceModel.js"); } catch (error) { if (error.code !== "ERR_MODULE_NOT_FOUND") throw error; }

test("changing an object mapping clears its dependent fields and relationships, leaving other judgements intact", () => {
  assert.ok(model, "domain mapping draft model is not implemented");
  const definition = { relationships: [{ id: "link", from: "a", to: "b" }] };
  const a = { kind: "object", reference: "a", local: "customer" };
  const b = { kind: "object", reference: "b", local: "order" };
  const mappings = [a, b, { kind: "property", owner: "a", reference: "name", local: { source: "customers", path: "name" } },
    { kind: "relation", reference: "link", local: "places" }];
  const before = structuredClone(mappings);
  assert.deepEqual(model.updateMapping(mappings, a, { ...a, local: "other" }, definition), [b, { ...a, local: "other" }]);
  assert.deepEqual(mappings, before);
});

test("property identities include their owning reference object and clearing a choice removes the decision", () => {
  assert.ok(model, "domain mapping draft model is not implemented");
  const a = { kind: "property", reference: "p", owner: "a" };
  const b = { kind: "property", reference: "p", owner: "b" };
  assert.notEqual(model.mappingKey(a), model.mappingKey(b));
  assert.deepEqual(model.updateMapping([a, b], a, null, { relationships: [] }), [b]);
});

test("graph location refuses unresolved reference edges and locates a property's owner", () => {
  assert.equal(typeof model?.graphSelection, "function", "graph location must check whether the element was parsed");
  const run = { ontology: { object_types: [{ key: "a" }], relations: [] } };
  assert.equal(model.graphSelection(run, { kind: "relation", reference: "unresolved" }, "reference"), null);
  assert.deepEqual(model.graphSelection(run, { kind: "property", owner: "a", reference: "p" }, "reference"), { kind: "node", key: "a" });
  assert.equal(model.graphSelection(run, { kind: "object", local: "removed" }, "local"), null);
});
