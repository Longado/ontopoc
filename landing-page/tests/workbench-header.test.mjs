// ONTOPOC_LAYOUT_URL=http://127.0.0.1:5178 node --test tests/workbench-header.test.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { after, test } from "node:test";

const browser = process.env.AGENT_BROWSER || `${homedir()}/.local/bin/agent-browser`;
const session = `ontopoc-header-${process.pid}`;
function ab(...args) {
  const result = JSON.parse(execFileSync(browser, ["--session", session, "--json", ...args], { encoding: "utf8", timeout: 30000 }));
  assert.equal(result.success, true, result.error);
  return result.data;
}
const evaluate = (script) => ab("eval", script).result;
const click = (role, name) => ab("find", "role", role, "click", "--name", name, "--exact");
after(() => ab("close"));

test("workbench header stays focused while evaluations remain accessible in their own pages", () => {
  ab("open", process.env.ONTOPOC_LAYOUT_URL || "http://127.0.0.1:5178");
  ab("set", "viewport", "1280", "720");
  click("button", "打开示例数据表");
  ab("wait", ".os-overview-file");
  const header = evaluate("document.querySelector('.os-overview').closest('header').innerText");
  assert.match(header, /本体管理/);
  for (const label of ["数据体检", "业务问答", "对照标准", "本体稳定性", "个对象"]) {
    assert.ok(!header.includes(label), `header must not repeat global status: ${label}`);
  }
  assert.match(header, /搜索/);
  assert.match(header, /纪要/);
  assert.match(header, /JSON/);
  assert.ok(evaluate("document.querySelector('.os-panel').innerText.includes('业务对象 (4)')"));

  click("button", "稳定性3 次");
  assert.match(evaluate("document.querySelector('.os-panel').innerText"), /3|三次/);
  click("button", "智能问答");
  click("button", "模型出的题6 / 6");
  assert.match(evaluate("document.querySelector('.os-panel').innerText"), /能回答 7 \/ 7/);
  click("button", "数据体检");
  assert.match(evaluate("document.querySelector('.os-panel').innerText"), /通过 4 \/ 6/);
  click("tab", "对照标准命中 4 / 5");
  assert.match(evaluate("document.querySelector('.os-panel').innerText"), /命中 4 \/ 5/);
  assert.ok(!evaluate("document.querySelector('.os-overview').closest('header').innerText").includes("通过 4 / 6"));
});
