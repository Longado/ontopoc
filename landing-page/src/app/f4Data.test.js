import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { TOOL_GROUPS, groupTools, toolInfo } from "./agentModel.js";
import { fitView } from "./graphModel.js";
import { aggAutoName, newOperator, retargetAgg } from "./pipelineModel.js";
import { hrefFor, parseRoute } from "./routeModel.js";
import { zoneChoices, zoneLabel } from "./scheduleTime.js";
import { suggestEnglish } from "./typeModel.js";

test("an aggregate's default name follows its function and column", () => {
  assert.equal(aggAutoName({ fn: "count" }), "行数");
  assert.equal(aggAutoName({ fn: "sum", column: "金额" }), "金额合计");
  assert.equal(aggAutoName({ fn: "avg", column: "金额" }), "金额平均");
  assert.equal(aggAutoName({ fn: "count_distinct", column: "客户" }), "客户去重数");
  assert.equal(aggAutoName({ fn: "max", column: "日期" }), "日期最大值");
});

test("changing the function or column renames the result unless the person typed their own name", () => {
  const fresh = newOperator("aggregate").aggregations[0];
  assert.equal(fresh.as, "行数");
  assert.deepEqual(retargetAgg(fresh, { column: "金额", fn: "sum" }), { fn: "sum", column: "金额", as: "金额合计" });
  assert.deepEqual(retargetAgg({ fn: "sum", column: "金额", as: "金额合计" }, { fn: "avg" }), { fn: "avg", column: "金额", as: "金额平均" });
  assert.deepEqual(retargetAgg({ fn: "sum", column: "金额", as: "总收入" }, { fn: "avg" }), { fn: "avg", column: "金额", as: "总收入" });
  assert.deepEqual(retargetAgg({ fn: "sum", column: "金额", as: "金额合计" }, { column: "", fn: "count" }), { fn: "count", as: "行数" });
  assert.deepEqual(retargetAgg({ fn: "count" }, { column: "金额", fn: "sum" }), { fn: "sum", column: "金额", as: "金额合计" });
});

test("the zone list holds the common zones, the browser's first when it is not among them", () => {
  const plain = zoneChoices("Asia/Shanghai");
  assert.equal(plain[0], "Asia/Shanghai");
  assert.equal(plain.filter((z) => z === "Asia/Shanghai").length, 1);
  for (const z of ["Asia/Hong_Kong", "Asia/Singapore", "Asia/Tokyo", "UTC", "Europe/London", "America/New_York", "America/Los_Angeles"]) assert.ok(plain.includes(z), z);
  assert.equal(zoneChoices("Europe/Paris")[0], "Europe/Paris");
  assert.equal(zoneChoices("Europe/Paris").length, plain.length + 1);
});

test("a zone is labelled in Chinese, and a strange one keeps its own name", () => {
  assert.equal(zoneLabel("Asia/Shanghai"), "北京时间（Asia/Shanghai）");
  assert.equal(zoneLabel("UTC"), "世界协调时间（UTC）");
  assert.equal(zoneLabel("Europe/Paris"), "Europe/Paris");
});

test("a pipeline or an object type can start from a dataset named in the address", () => {
  assert.deepEqual(parseRoute("#/pipelines/new?dataset=%E8%AE%A2%E5%8D%95"), { page: "pipelinenew", dataset: "订单" });
  assert.deepEqual(parseRoute("#/pipelines/new"), { page: "pipelinenew" });
  assert.deepEqual(parseRoute("#/types/new?dataset=%E8%AE%A2%E5%8D%95"), { page: "typenew", dataset: "订单" });
  assert.equal(hrefFor({ page: "pipelinenew", dataset: "订单" }), "#/pipelines/new?dataset=%E8%AE%A2%E5%8D%95");
  assert.equal(hrefFor({ page: "typenew", dataset: "订单" }), "#/types/new?dataset=%E8%AE%A2%E5%8D%95");
  assert.equal(hrefFor({ page: "typenew" }), "#/types/new");
});

test("the English name is suggested from known words, and left for the person when a word is unknown", () => {
  assert.equal(suggestEnglish("订单"), "order");
  assert.equal(suggestEnglish("售后工单"), "after_sales_ticket");
  assert.equal(suggestEnglish("客户表"), "customer");
  assert.equal(suggestEnglish("Order Items"), "order_items");
  assert.equal(suggestEnglish("神秘东西"), "");
  assert.equal(suggestEnglish(""), "");
});

test("every tool the MCP server offers has a Chinese line and a group", () => {
  const source = readFileSync(new URL("../../../src/ontology_poc_generator/mcp_server.py", import.meta.url), "utf8");
  const names = [...source.matchAll(/^\s+_tool\((\w+),/gm)].map((m) => m[1]);
  assert.ok(names.length > 30);
  for (const n of names) {
    assert.ok(toolInfo(n).known, `${n} has no Chinese line`);
    assert.ok(TOOL_GROUPS.includes(toolInfo(n).group), n);
  }
  assert.equal(toolInfo("ontopoc_query").group, "问");
  assert.equal(toolInfo("describe_definitions").group, "读");
  assert.equal(toolInfo("not_a_tool").known, false);
});

test("tools are grouped in the group order and keep their order inside a group", () => {
  const groups = groupTools([{ name: "ask" }, { name: "describe_definitions" }, { name: "ontopoc_query" }, { name: "mystery" }]);
  assert.deepEqual(groups.map((g) => [g.group, g.tools.map((t) => t.name)]), [["读", ["describe_definitions"]], ["问", ["ask", "ontopoc_query"]], ["其他", ["mystery"]]]);
});

test("a wide picture is fitted to the width of the page and a small one is not blown up past the cap", () => {
  assert.deepEqual(fitView({ w: 1200, h: 500 }, { width: 2400, height: 400 }, "width"), { k: 0.5, x: 0, y: 44 });
  assert.equal(fitView({ w: 1200, h: 500 }, { width: 600, height: 300 }, "width").k, 1.5);
  assert.deepEqual(fitView({ w: 1200, h: 500 }, { width: 600, height: 300 }, "all"), { k: 1, x: 300, y: 100 });
});
