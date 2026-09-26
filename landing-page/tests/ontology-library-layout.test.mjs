// Browser geometry regression. Run against a local server with agent-browser installed:
// ONTOPOC_LAYOUT_URL=http://127.0.0.1:5178 node --test tests/ontology-library-layout.test.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { after, test } from "node:test";

const url = process.env.ONTOPOC_LAYOUT_URL || "http://127.0.0.1:5178";
const browser = process.env.AGENT_BROWSER || `${homedir()}/.local/bin/agent-browser`;
const session = `ontopoc-layout-${process.pid}`;
function ab(...args) {
  const result = JSON.parse(execFileSync(browser, ["--session", session, "--json", ...args], { encoding: "utf8", timeout: 30000 }));
  assert.equal(result.success, true, result.error);
  return result.data;
}
const evaluate = (script) => ab("eval", script).result;
after(() => ab("close"));

function catalogue(width, height) {
  ab("open", url);
  ab("set", "viewport", String(width), String(height));
  ab("find", "role", "button", "click", "--name", "本体库", "--exact");
  ab("wait", ".ol-card");
}
function definition(title) {
  evaluate(`([...document.querySelectorAll('.ol-card')].find(e => e.querySelector('h2').textContent === ${JSON.stringify(title)})).click()`);
  ab("wait", ".ol-page .og-node");
}
function geometry() {
  return evaluate(`(() => {
    const box = e => { const r = e.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, height: r.height, scroll: e.scrollHeight, client: e.clientHeight }; };
    return { main: box(document.querySelector('.app-main')), graph: box(document.querySelector('.ol-page .og-wrap')),
      svg: box(document.querySelector('.ol-page .pz svg')), inspector: box(document.querySelector('.ol-page .og-inspector')),
      viewport: innerHeight, pageWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth };
  })()`);
}
function fits(g) {
  assert.ok(g.main.scroll <= g.main.client + 1, `detail must not scroll the main pane: ${JSON.stringify(g)}`);
  assert.ok(g.graph.top >= 0 && g.graph.bottom <= g.viewport + 1, `entire graph must be visible: ${JSON.stringify(g)}`);
  assert.ok(g.svg.bottom <= g.viewport + 1 && g.svg.height > 200, "graph controls and canvas must fit on screen");
  assert.ok(g.pageWidth <= g.viewportWidth, "no horizontal page overflow");
}

test("definition and long object properties fit the pane at desktop and laptop heights", async () => {
  for (const [width, height] of [[1440, 900], [1280, 720], [1024, 768]]) {
    catalogue(width, height);
    // Arriving from a scrolled catalogue must bring the detail header and graph into view.
    evaluate("document.querySelector('.app-main').scrollTop = 300");
    definition("售后服务工单");
    const d = await (await fetch(`${url}/api/ontology/library/service-order-management`)).json();
    const longest = d.entity_types.reduce((a, b) => a.properties.length >= b.properties.length ? a : b);
    ab("select", ".ol-object select", longest.id);
    const before = geometry();
    fits(before);
    assert.ok(before.inspector.scroll > before.inspector.client, "long property list should scroll inside the inspector");
    evaluate("document.querySelector('.ol-page .og-inspector').scrollTop = 500");
    const after = geometry();
    fits(after);
    assert.equal(after.graph.top, before.graph.top, "reading properties must not move the graph");
    assert.equal(after.graph.height, before.graph.height);
  }
});

test("description, warnings and RDF remain accessible without pushing the graph down", () => {
  catalogue(1280, 720);
  definition("咖啡零售");
  const before = geometry();
  const button = evaluate("[...document.querySelectorAll('.ol-page button')].find(b => b.textContent.includes('说明与原文'))?.textContent");
  assert.ok(button, "detail should offer description and original RDF on demand");
  ab("find", "role", "button", "click", "--name", button.trim(), "--exact");
  assert.equal(evaluate("document.querySelector('.ol-page dialog').open"), true);
  assert.ok(evaluate("document.querySelector('.ol-page dialog').innerText.includes('数据绑定声明')"));
  assert.ok(evaluate("document.querySelector('.ol-page dialog pre').textContent.includes('owl:Class')"));
  const after = geometry();
  assert.equal(after.graph.top, before.graph.top);
  assert.equal(after.graph.height, before.graph.height);
  ab("press", "Escape");
  assert.equal(evaluate("document.querySelector('.ol-page dialog').open"), false);
  fits(geometry());
});

test("leaving a definition restores normal mobile workbench scrolling", () => {
  catalogue(390, 844);
  definition("咖啡零售");
  ab("click", ".app-new");
  assert.equal(evaluate("document.querySelector('.ol-page').parentElement.hidden"), true);
  assert.equal(evaluate("getComputedStyle(document.querySelector('.app-main')).overflowY"), "visible",
    "a hidden library definition must not clip the existing mobile workbench");
});
