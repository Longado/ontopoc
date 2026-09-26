// Run only with an isolated trial server and a saved public-data run:
// ONTOPOC_REFERENCE_URL=http://127.0.0.1:5179 ONTOPOC_REFERENCE_RUN=<saved_as> node --test tests/ontology-reference.test.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { after, test } from "node:test";

const url = process.env.ONTOPOC_REFERENCE_URL;
const savedAs = process.env.ONTOPOC_REFERENCE_RUN;
assert.ok(url && savedAs, "supply an isolated trial URL and run; this test saves a domain mapping");
const session = `ontopoc-reference-${process.pid}`;
const browser = process.env.AGENT_BROWSER || `${homedir()}/.local/bin/agent-browser`;
function ab(...args) {
  const reply = JSON.parse(execFileSync(browser, ["--session", session, "--json", ...args], { encoding: "utf8", timeout: 30000 }));
  assert.equal(reply.success, true, reply.error);
  return reply.data;
}
const evaluate = script => ab("eval", script).result;
const click = name => { evaluate(`([...document.querySelectorAll('button')].find(e => (e.getAttribute('aria-label') || e.textContent.trim()) === ${JSON.stringify(name)} && !e.disabled)).focus()`); ab("press", "Enter"); };
const get = async path => { const r = await fetch(url + path, { headers: { Connection: "close" } }); assert.ok(r.ok); return r.json(); };
after(() => ab("close"));

test("select, map, inspect, confirm, reload and cancel keep the user's actual answers intact", async () => {
  const run = await get(`/api/ontology/runs/${savedAs}`);
  const definition = await get("/api/ontology/library/ecommerce");
  const customer = run.ontology.object_types.find(t => t.populated_from.some(p => Object.values(p.identity).includes("customerID")));
  const order = run.ontology.object_types.find(t => t.populated_from.some(p => Object.values(p.identity).includes("orderID")));
  const buyer = definition.entity_types.find(e => e.name === "Buyer");
  const referenceOrder = definition.entity_types.find(e => e.name === "Order");
  assert.ok(customer && order && buyer && referenceOrder);
  const property = buyer.properties.find(p => p.name === "buyerId");
  const relation = definition.relationships.find(r => r.from === buyer.id && r.to === referenceOrder.id);
  const localRelation = run.ontology.relations.find(r => new Set([r.from, r.to]).has(customer.key) && new Set([r.from, r.to]).has(order.key));
  assert.ok(property && relation && localRelation);
  const customerSource = customer.populated_from.find(p => Object.values(p.identity).includes("customerID")).source;

  function openReference() {
    ab("open", url);
    evaluate(`localStorage.setItem('ontopoc.studio.last-result', ${JSON.stringify(JSON.stringify(run))})`);
    ab("open", url);
    ab("wait", ".os-overview-file");
    click("数据体检");
    evaluate("[...document.querySelectorAll('.os-segments [role=tab]')].find(e=>e.textContent.includes('对照标准')).click()");
  }
  openReference();
  ab("set", "viewport", "1280", "720");
  assert.equal(evaluate("Boolean(document.querySelector('[aria-label=选择领域参考]'))"), true, "domain reference picker should be available");
  ab("wait", "[aria-label=选择领域参考]:not(:disabled)");
  ab("select", "[aria-label=选择领域参考]", "ecommerce");
  ab("wait", ".dr-mapping-row");
  ab("select", '[aria-label="Buyer 对应对象"]', customer.key);
  ab("select", '[aria-label="Order 对应对象"]', order.key);
  click("属性对应");
  ab("select", '[aria-label="选择参考对象的属性"]', buyer.id);
  ab("select", '[aria-label="buyerId 对应属性"]', JSON.stringify([customerSource, "customerID"]));
  click("关系对应");
  ab("select", `[aria-label=${JSON.stringify(relation.name + " 对应关系")}]`, localRelation.key);
  click("预览差异");
  ab("wait", ".dr-differences");
  assert.match(evaluate("document.querySelector('.dr-differences').innerText"), /已对应/);
  assert.equal(evaluate("Boolean(document.querySelector('.dr-mappings'))"), false, "review should replace the mapping list rather than stack below it");
  assert.ok(evaluate("document.querySelector('.dr-actions').getBoundingClientRect().bottom <= innerHeight"), "save controls must fit in the laptop viewport");
  assert.deepEqual((await get(`/api/ontology/runs/${savedAs}`)).evaluation, run.evaluation, "preview must not write a result");
  click("确认对应并保存");
  ab("wait", ".dr-saved");
  const context = await get(`/api/ontology/runs/${savedAs}/reference`);
  assert.equal(context.record.mappings.filter(m => m.local).length, 4);
  const persisted = await get(`/api/ontology/runs/${savedAs}`);
  assert.deepEqual(persisted.ontology, run.ontology);
  assert.deepEqual(persisted.evaluation.asked, run.evaluation.asked);

  openReference();
  ab("wait", ".dr-saved");
  assert.equal(evaluate("document.querySelector('[aria-label=\"Buyer 对应对象\"]').value"), customer.key);
  ab("select", '[aria-label="Buyer 对应对象"]', "");
  click("取消修改");
  assert.equal(evaluate("document.querySelector('[aria-label=\"Buyer 对应对象\"]').value"), customer.key);
  click("查看参考 Buyer");
  ab("wait", ".dr-graph-dialog[open] .og-node");
  const geometry = evaluate("(() => {const r=document.querySelector('.dr-graph-dialog .og-wrap').getBoundingClientRect(); return {bottom:r.bottom,height:r.height,viewport:innerHeight};})()");
  assert.ok(geometry.bottom <= geometry.viewport && geometry.height > 200, "graph must fit without scrolling the whole page");
  ab("press", "Escape");
  ab("set", "viewport", "390", "844");
  assert.ok(evaluate("document.documentElement.scrollWidth <= innerWidth"), "narrow screen must not overflow horizontally");
});
