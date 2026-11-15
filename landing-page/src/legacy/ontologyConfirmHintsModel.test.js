import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

import { otherRunTypes } from "./ontologyConfirmModel.js";

test("objects other runs built are offered for adding, unless already added", () => {
  const run = { evaluation: { stability: { runs: 3, elsewhere: { types: [{ label: "产品", count: 1 }, { label: "国家", count: 2 }], relations: [] } } } };
  assert.deepEqual(otherRunTypes(run, { added: ["国家"] }), [{ label: "产品", count: 1, runs: 3 }]);
  assert.deepEqual(otherRunTypes({ evaluation: {} }, { added: [] }), []);
});

test("the landing page says who the tool is for and exactly what is sent to the model", async () => {
  const source = await readFile(new URL("./App.jsx", import.meta.url), "utf8");
  assert.match(source, /给实施顾问和本体团队/);
  assert.match(source, /每列最多 3 个示例值/);
});
