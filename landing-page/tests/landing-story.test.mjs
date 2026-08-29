import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

test("landing story has one full operational surface and the accepted section order", () => {
  assert.equal(app.includes('className="trial-section"'), false);
  assert.match(app, /<DecisionMoment[\s\S]*onOpenTrial/);

  const review = app.indexOf('id="review"');
  const how = app.indexOf('id="how"');
  const model = app.indexOf('id="model"');
  const build = app.indexOf('id="build"');
  assert.ok(review < how && how < model && model < build);
});

test("landing teaser and Four Gates do not duplicate Trial approval controls", () => {
  assert.equal(app.includes("replayState"), false);
  assert.match(app, /function ApproveScene\(\{ copy \}\)/);
  assert.match(app, /className="approval-mechanism"/);
});

test("workbench and gate tabs expose controlled panels and roving focus", () => {
  assert.match(app, /id={`model-tab-\$\{index\}`}/);
  assert.match(app, /aria-controls={`model-panel-\$\{index\}`}/);
  assert.match(app, /id={`gate-tab-\$\{index\}`}/);
  assert.match(app, /aria-controls={`gate-panel-\$\{index\}`}/);
  assert.match(app, /tabIndex={activeStage === index \? 0 : -1}/);
  assert.match(app, /tabIndex={activeGate === index \? 0 : -1}/);
});

test("modal traps focus and restores it to the opener", () => {
  assert.match(app, /previousFocusRef/);
  assert.match(app, /closeButtonRef/);
  assert.match(app, /focusableElements/);
  assert.match(app, /previousFocusRef\.current\?\.focus/);
});

test("model embeds three reusable product primitives with an accessible detail switcher", () => {
  assert.match(app, /<ProductPrimitives copy={experience\.primitives} \/>/);
  assert.match(app, /function ProductPrimitives\(\{ copy \}\)/);
  assert.match(app, /CHANGE EVENT/);
  assert.match(app, /IMPACT TRACE/);
  assert.match(app, /APPROVAL RECEIPT/);
  assert.match(app, /id={`primitive-tab-\$\{index\}`}/);
  assert.match(app, /aria-controls={`primitive-panel-\$\{index\}`}/);
  assert.match(app, /tabIndex={activePrimitive === index \? 0 : -1}/);
});
