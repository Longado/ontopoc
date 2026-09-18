import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { resolveAppSurface } from "./appSurfaceModel.js";

test("root and demo paths open the standalone workspace", () => {
  assert.equal(resolveAppSurface("/"), "demo");
  assert.equal(resolveAppSurface("/demo"), "demo");
  assert.equal(resolveAppSurface("/demo/"), "demo");
});

test("landing path opens the landing page", () => {
  assert.equal(resolveAppSurface("/landing"), "landing");
  assert.equal(resolveAppSurface("/landing/"), "landing");
});

test("unknown paths fall back to the standalone workspace", () => {
  assert.equal(resolveAppSurface("/missing"), "demo");
});

test("standalone surface opens on upload-to-ontology and keeps both recall examples", async () => {
  const source = await readFile(new URL("./StandaloneDemo.jsx", import.meta.url), "utf8");
  assert.match(source, /useState\("studio"\)/);
  assert.match(source, /<OntologyStudio request=\{request\}/);   // the sidebar's run library tells the studio which run to open
  assert.match(source, /<PublicRecallReview language=\{language\} \/>/);
  assert.match(source, /<RecallWorkspace language=\{language\} onBusyChange=\{setRecallBusy\} \/>/);
  assert.match(source, /href="\/landing"/);
  assert.doesNotMatch(source, /synthetic_demo|TrialWorkspace/);
});

test("landing page leads with upload-to-ontology and auto evaluation, recall as an example", async () => {
  const source = await readFile(new URL("./App.jsx", import.meta.url), "utf8");
  assert.match(source, /上传一份业务文件/);
  assert.match(source, /数据体检/);
  assert.match(source, /业务问答/);
  assert.match(source, /对照标准/);
  assert.match(source, /示例场景/);
  assert.match(source, /召回范围研判/);
  assert.match(source, /href="\/"/);
  assert.match(source, /demo_company\.xlsx/);
  assert.doesNotMatch(source, /供应链|SUPPLY CHAIN|synthetic_demo|ImpactTrace|TrialWorkspace/);
});

test("main selects the landing page only for the landing surface", async () => {
  const source = await readFile(new URL("./main.jsx", import.meta.url), "utf8");
  assert.match(source, /resolveAppSurface\(window\.location\.pathname\)/);
  assert.match(source, /surface === "landing" \? <App \/> : <StandaloneDemo \/>/);
});
