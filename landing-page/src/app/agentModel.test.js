import assert from "node:assert/strict";
import test from "node:test";

import { TOKEN_PLACEHOLDER, connectConfig, firstSentence, skillText, tokenState } from "./agentModel.js";

const COMMAND = { python: "python3", module: "ontology_poc_generator.mcp_server", src: "/repo/src" };

test("the connect entry starts the server with the read-only tools as the token's person, and a placeholder until there is a token", () => {
  const config = JSON.parse(connectConfig({ command: COMMAND, origin: "http://127.0.0.1:5302", token: "" }));
  assert.deepEqual(config.mcpServers.ontopoc.args, ["-m", "ontology_poc_generator.mcp_server"]);
  assert.deepEqual(config.mcpServers.ontopoc.env, { PYTHONPATH: "/repo/src", ONTOPOC_URL: "http://127.0.0.1:5302", ONTOPOC_TOOLSET: "read", ONTOPOC_TOKEN: TOKEN_PLACEHOLDER });
  assert.equal(JSON.parse(connectConfig({ command: COMMAND, origin: "x", token: "otp_abc" })).mcpServers.ontopoc.env.ONTOPOC_TOKEN, "otp_abc");
});

test("a tool is described by its first sentence, the skill by what it holds, a token by its state", () => {
  assert.equal(firstSentence("团队已经确认的业务定义：对象类型。只有已确认的。"), "团队已经确认的业务定义：对象类型");
  assert.equal(skillText({ types: 6, relations: 5, views: 1, derived: 1 }), "6 个对象类型、5 条关系、1 个视图、1 个派生属性；都是已确认的，没有数据行");
  assert.deepEqual([{ revoked: true }, { revoked: false, last_used_at: "2026-11-14" }, { revoked: false, last_used_at: null }].map(tokenState), ["已撤销", "在用", "还没用过"]);
});
