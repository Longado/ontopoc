import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("the local library has an entry even without an uploaded run", async () => {
  const shell = await readFile(new URL("./StandaloneDemo.jsx", import.meta.url), "utf8");
  assert.match(shell, /OntologyLibrary/);
  assert.match(shell, /本体库/);
});

test("references can be found by Chinese title, original name, author and category", async () => {
  const { libraryEntries } = await import("./ontologyLibraryModel.js");
  const entries = [{ id: "a", title: "零售供应链", name: "Retail", author: "Microsoft", category: "零售", tags: ["inventory"] },
    { id: "b", title: "制造", name: "Manufacturing", author: "Community", category: "制造", tags: [] }];
  for (const query of ["供应链", "retail", "microsoft", "inventory"]) assert.deepEqual(libraryEntries(entries, query, ""), [entries[0]]);
  assert.deepEqual(libraryEntries(entries, "", "制造"), [entries[1]]);
});

test("the definition graph keeps IRIs and never manufactures data verification or instance counts", async () => {
  const { definitionRun } = await import("./ontologyLibraryModel.js");
  const definition = { schema: "ontology_definition.v1", name: "参考", entity_types: [
    { id: "https://a/Customer", name: "客户", description: "购买者", properties: [{ id: "https://a/id", name: "编号", type: "string", isIdentifier: true }] },
    { id: "https://b/Customer", name: "客户 B", properties: [] }], relationships: [
    { id: "https://a/r", name: "关联", from: "https://a/Customer", to: "https://b/Customer" },
    { id: "https://a/missing", from: "https://a/Customer", to: "https://a/Missing" }] };
  const run = definitionRun(definition);
  assert.equal(run.schema, "ontology_definition.v1");
  assert.deepEqual(run.ontology.object_types.map((t) => t.key), definition.entity_types.map((e) => e.id));
  assert.equal(run.ontology.object_types[0].attributes[0].definition.type, "string");
  assert.equal(run.ontology.relations.length, 1);
  assert.equal(run.ontology.verification, undefined);
  assert.deepEqual(run.evaluation, {});
  assert.equal(run.saved_as, undefined);
});

test("the graph describes reference definitions without suggesting they were checked against data", async () => {
  const graph = await readFile(new URL("./OntologyGraph.jsx", import.meta.url), "utf8");
  assert.match(graph, /ontology_definition\.v1/);
  assert.match(graph, /定义图.*不含实例数据/);
});
