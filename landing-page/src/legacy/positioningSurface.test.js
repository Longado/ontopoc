import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("the tagline speaks for the ontology tool", async () => {
  const landing = await read("./App.jsx");
  assert.doesNotMatch(landing, /Trace scope/);
  assert.match(landing, /Draft the ontology\. Check it against the data\./);
});
