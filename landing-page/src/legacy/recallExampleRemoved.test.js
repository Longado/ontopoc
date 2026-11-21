import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";

// The public recall example (vehicle recalls, a food recall event) is gone from the earlier screen; its shared card styles stay.
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const gone = /recall|召回|nhtsa|openfda/i;

test("the earlier screen has no recall example left, and no 'more examples' list to hold one", () => {
  const shell = read("./StandaloneDemo.jsx");
  assert.doesNotMatch(shell, gone);
  assert.doesNotMatch(shell, /更多示例|More examples|app-more/);
  assert.doesNotMatch(read("./App.jsx"), gone);
  assert.deepEqual(readdirSync(new URL(".", import.meta.url)).filter((name) => gone.test(name) && name !== "recallExampleRemoved.test.js"), []);
});

test("the page build ships only the two demo results as data, and the dev server forwards no recall service", () => {
  assert.deepEqual(readdirSync(new URL("../../public/data", import.meta.url)).sort(), ["demo-company-result.json", "demo-document-result.json"]);
  assert.doesNotMatch(read("../../vite.config.mjs"), gone);
});

test("the card styles the earlier screen uses still load, from a sheet of their own", () => {
  const studio = read("./OntologyStudio.jsx");
  assert.match(studio, /import "\.\/shared\.css";/);
  assert.doesNotMatch(studio, gone);
  const sheet = read("./shared.css");
  const used = new Set();
  for (const name of readdirSync(new URL(".", import.meta.url)).filter((n) => /\.jsx$/.test(n))) {
    for (const [, cls] of read(`./${name}`).matchAll(/\b(pr-[a-z][a-z0-9_-]*)/g)) used.add(cls);
  }
  assert.ok(used.size > 10);
  for (const cls of used) assert.match(sheet, new RegExp(`\\.${cls}(?![\\w-])`), cls);
});
