import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// Built CSS follows the order modules are first imported. The shared page styles (.pr-page h2, .pr-page button, ...) have the same
// specificity as many component rules, so they must come in before every component of the earlier screen, or they start winning.
const imports = (name) => [...readFileSync(new URL(name, import.meta.url), "utf8").matchAll(/^import\s+(?:[^"']*?from\s+)?["']([^"']+)["'];/gm)].map((m) => m[1]);

test("the earlier screen's shell imports the shared styles before any component that brings its own", () => {
  const order = imports("./StandaloneDemo.jsx");
  const shared = order.indexOf("./shared.css");
  assert.ok(shared >= 0, "StandaloneDemo.jsx imports ./shared.css");
  const firstComponent = order.findIndex((spec) => /\.jsx$/.test(spec));
  assert.ok(firstComponent > shared, `shared.css comes before ${order[firstComponent]}`);
});

test("only the old landing text loads ahead of the shell, and the base sheet stays last", () => {
  const order = imports("./main.jsx");
  assert.ok(order.indexOf("./App.jsx") < order.indexOf("./StandaloneDemo.jsx"));
  assert.equal(order.at(-1), "./styles.css");
  assert.doesNotMatch(imports("./App.jsx").join(" "), /shared\.css|OntologyStudio/);
});
