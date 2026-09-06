import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { resolveAppSurface } from "./appSurfaceModel.js";

test("root and demo paths open the standalone workspace", () => {
  assert.equal(resolveAppSurface("/"), "demo");
  assert.equal(resolveAppSurface("/demo"), "demo");
  assert.equal(resolveAppSurface("/demo/"), "demo");
});

test("landing path preserves the existing landing page", () => {
  assert.equal(resolveAppSurface("/landing"), "landing");
  assert.equal(resolveAppSurface("/landing/"), "landing");
});

test("unknown paths fall back to the standalone workspace", () => {
  assert.equal(resolveAppSurface("/missing"), "demo");
});

test("standalone surface mounts the existing workspace with a local language control", async () => {
  const source = await readFile(new URL("./StandaloneDemo.jsx", import.meta.url), "utf8").catch(() => "");

  assert.match(source, /<TrialWorkspace language=\{language\} \/>/);
  assert.match(source, /className="standalone-demo"/);
  assert.match(source, /setLanguage/);
  assert.match(source, /href="\/landing"/);
  assert.match(source, /synthetic_demo · SESSION ONLY/);
  assert.doesNotMatch(source, /synthetic_demo · READ ONLY/);
});

test("main selects the landing page only for the landing surface", async () => {
  const source = await readFile(new URL("./main.jsx", import.meta.url), "utf8");

  assert.match(source, /resolveAppSurface\(window\.location\.pathname\)/);
  assert.match(source, /surface === "landing" \? <App \/> : <StandaloneDemo \/>/);
});
