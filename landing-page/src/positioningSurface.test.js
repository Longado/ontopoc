import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("the recall examples sit under 'more examples', not beside the main entry", async () => {
  const source = await read("./StandaloneDemo.jsx");
  assert.match(source, /更多示例/);
  assert.match(source, /More examples/);
  assert.match(source, /<details className="app-more"/);
});

test("the tagline speaks for the ontology tool", async () => {
  const landing = await read("./App.jsx");
  assert.doesNotMatch(landing, /Trace scope/);
  assert.match(landing, /Draft the ontology\. Show the evidence\./);
});
