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

test("standalone surface defaults to the public recall scenario and keeps the local lookup", async () => {
  const source = await readFile(new URL("./StandaloneDemo.jsx", import.meta.url), "utf8");
  assert.match(source, /useState\("public"\)/);
  assert.match(source, /<PublicRecallReview language=\{language\} \/>/);
  assert.match(source, /<RecallWorkspace language=\{language\} onBusyChange=\{setRecallBusy\} \/>/);
  assert.match(source, /href="\/landing"/);
  assert.doesNotMatch(source, /synthetic_demo|TrialWorkspace/);
});

test("landing page describes the current scenario, not the retired ones", async () => {
  const source = await readFile(new URL("./App.jsx", import.meta.url), "utf8");
  assert.match(source, /召回范围研判/);
  assert.match(source, /href="\/"/);
  assert.doesNotMatch(source, /供应链|SUPPLY CHAIN|synthetic_demo|ImpactTrace|TrialWorkspace/);
});

test("main selects the landing page only for the landing surface", async () => {
  const source = await readFile(new URL("./main.jsx", import.meta.url), "utf8");
  assert.match(source, /resolveAppSurface\(window\.location\.pathname\)/);
  assert.match(source, /surface === "landing" \? <App \/> : <StandaloneDemo \/>/);
});
