import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("the sidebar starts new work and lists every run kept on this machine", async () => {
  const shell = await readFile(new URL("./StandaloneDemo.jsx", import.meta.url), "utf8");
  assert.match(shell, /新建/);
  assert.match(shell, /运行记录/);
  assert.match(shell, /\/api\/ontology\/runs/);
  assert.match(shell, /groupRuns/);
});

test("an empty workbench asks one question and offers one box, not a page of text", async () => {
  const studio = await readFile(new URL("./OntologyStudio.jsx", import.meta.url), "utf8");
  assert.match(studio, /今天要看哪份数据？/);
  assert.match(studio, /className="os-composer/);
  assert.doesNotMatch(studio, /没有文件？先试示例/);   // the demo card became two small chips under the box
});
