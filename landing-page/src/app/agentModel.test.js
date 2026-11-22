import assert from "node:assert/strict";
import test from "node:test";

import { tokenPlaceholder, connectConfig, endText, firstSentence, scopeWord, skillText, tokenState, toolInfo } from "./agentModel.js";
import { SCHEMA_HREF, STANDING_CSV_HREF } from "./api.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in askEnglish.test.js

const COMMAND = { python: "python3", module: "ontology_poc_generator.mcp_server" };

test("the connect entry starts the installed package's server as the token's person with the service address, and a placeholder until there is a token", () => {
  const config = JSON.parse(connectConfig({ command: COMMAND, origin: "http://127.0.0.1:5302", token: "" }));
  assert.equal(config.mcpServers.ontopoc.command, "python3");
  assert.deepEqual(config.mcpServers.ontopoc.args, ["-m", "ontology_poc_generator.mcp_server"]);
  assert.deepEqual(config.mcpServers.ontopoc.env, { ONTOPOC_URL: "http://127.0.0.1:5302", ONTOPOC_TOKEN: tokenPlaceholder() });
  assert.equal(JSON.parse(connectConfig({ command: COMMAND, origin: "x", token: "otp_abc" })).mcpServers.ontopoc.env.ONTOPOC_TOKEN, "otp_abc");
});

test("the entry for this machine adds where the code sits, and only when it is given one", () => {
  const local = JSON.parse(connectConfig({ command: { ...COMMAND, local_src: "/repo/src" }, origin: "http://127.0.0.1:5302", token: "", local: true }));
  assert.equal(local.mcpServers.ontopoc.env.PYTHONPATH, "/repo/src");
  const generic = connectConfig({ command: { ...COMMAND, local_src: "/repo/src" }, origin: "http://127.0.0.1:5302", token: "" });
  assert.ok(!generic.includes("/repo/src"));
});

test("a tool is described by its first sentence, the skill by what it holds, a token by its state", () => {
  assert.equal(firstSentence("团队已经确认的业务定义：对象类型。只有已确认的。"), "团队已经确认的业务定义：对象类型");
  assert.equal(skillText({ types: 6, relations: 5, views: 1, derived: 1 }), "6 个对象类型、5 条关系、1 个视图、1 个派生属性；都是已确认的，没有数据行");
  assert.deepEqual([{ revoked: true }, { revoked: false, last_used_at: "2026-11-14" }, { revoked: false, last_used_at: null }].map(tokenState), ["已撤销", "在用", "还没用过"]);
  assert.equal(tokenState({ revoked: false, expired: true, last_used_at: "2026-11-14" }), "已过期");
});

test("a token's reach and end are said in words", () => {
  assert.deepEqual([{ scope: "read" }, { scope: "all" }, { scope: null }].map(scopeWord), ["只读", "全部", "只读"]);
  assert.deepEqual([{ expires_at: null }, { expires_at: "2027-02-12T03:00:00+00:00" }, { expires_at: "2026-01-01T00:00:00+00:00", expired: true }].map(endText), ["不过期", "2027-02-12", "已过期"]);
});

test("the standing tool reads, and the sheet of confirmed definitions is the live address as CSV", () => {
  assert.deepEqual(toolInfo("definition_standing"), { group: "read", line: "每条定义现在是不是已确认、谁确认的、在哪个数据版本上；没确认的写明原因", known: true });
  assert.equal(STANDING_CSV_HREF, "/api/workspace/agent/standing?format=csv");
});

test("the same confirmed definitions download as OWL and SHACL files from the schema address", () => {
  assert.equal(SCHEMA_HREF, "/api/workspace/agent/schema");
});
