import assert from "node:assert/strict";
import test from "node:test";

import { postAndReread } from "./codeSaveModel.js";

const reply = (status, body) => ({ ok: status < 400, status, json: async () => body });

test("a save posts the run name and the body, then reads the run again, and hands back both", async () => {
  const calls = [];
  const send = async (url, options) => {
    calls.push([url, options.method || "GET", options.body ? JSON.parse(options.body) : null]);
    return url.endsWith("/code-meanings") ? reply(200, { items: [], answered: [], meanings: {} }) : reply(200, { saved_as: "r.json", evaluation: {} });
  };
  const got = await postAndReread({ send, url: "/api/ontology/code-meanings", body: { id: "code_meaning:订单.状态码", values: [{ value: "2", label: "已取消" }] }, runName: "r.json" });
  assert.deepEqual(calls, [["/api/ontology/code-meanings", "POST", { saved_as: "r.json", id: "code_meaning:订单.状态码", values: [{ value: "2", label: "已取消" }] }],
    ["/api/ontology/runs/r.json", "GET", null]]);
  assert.deepEqual([got.lists.items, got.run.saved_as, got.warning], [[], "r.json", ""]);
});

test("what the service says it could not finish comes back as a warning, and a refusal throws its own words", async () => {
  const warned = await postAndReread({ send: async (url) => reply(200, url.includes("/runs/") ? {} : { items: [], warning: "含义已保存，但答案没能重算" }), url: "/x", body: {}, runName: "r.json" });
  assert.equal(warned.warning, "含义已保存，但答案没能重算");
  await assert.rejects(postAndReread({ send: async () => reply(400, { error: "这一列已经不在清单上了" }), url: "/x", body: {}, runName: "r.json" }), /这一列已经不在清单上了/);
  await assert.rejects(postAndReread({ send: async (url) => (url.includes("/runs/") ? reply(500, { error: "坏了" }) : reply(200, { items: [] })), url: "/x", body: {}, runName: "r.json" }), /已记下，但没能读到重算后的答案：坏了/);
});
