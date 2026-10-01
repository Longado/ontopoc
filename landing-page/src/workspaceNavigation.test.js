import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { transformSync } from "esbuild";
import { sectionsFor } from "./workspaceModel.js";

// Exercise the actual shell's rendered controls and handlers; child workspaces are outside this test.
const source = readFileSync(new URL("./StandaloneDemo.jsx", import.meta.url), "utf8");
const compiled = transformSync(source.slice(source.indexOf("const copy =")), {
  loader: "jsx", format: "cjs", jsxFactory: "element", jsxFragment: "fragment",
}).code;
const element = (type, props, ...children) => ({ type, props: { ...props, children } });
const content = (node) => typeof node === "string" ? node : (node?.props?.children || []).flat(Infinity).map(content).join("");
const find = (node, predicate) => predicate(node) ? node
  : (node?.props?.children || []).flat(Infinity).map((child) => find(child, predicate)).find(Boolean);

function shell(open = null) {
  let slot = 0;
  const updates = [];
  const dependencies = { element, fragment: "fragment", sectionsFor, useEffect: () => {}, useCallback: (fn) => fn,
    useState: (initial) => { const key = slot++; return [key === 4 ? open : initial, (value) => updates.push({ key, value })]; },
    RecallWorkspace: "recall", PublicRecallReview: "public", OntologyStudio: "studio", OntologyLibrary: "library",
    folderLabel: (name) => name, groupRuns: () => [], runLabel: () => "", localTime: () => "" };
  const module = { exports: {} };
  new Function("module", ...Object.keys(dependencies), compiled)(module, ...Object.values(dependencies));
  const tree = module.exports.StandaloneDemo();
  const nav = find(tree, (node) => node?.type === "nav" && node.props["aria-label"] === "模块");
  const buttons = nav.props.children.flat(Infinity).filter((node) => node?.type === "button");
  return { tree, updates, buttons, button: (name) => buttons.find((node) => content(node) === name) };
}

test("an empty workspace keeps all five modules visible and explains how to activate them", () => {
  const s = shell();
  assert.deepEqual(s.buttons.map(content), ["本体库", "数据接入", "本体管理", "本体关系", "智能问答", "数据体检"]);
  assert.notEqual(s.button("本体库").props.disabled, true);
  assert.notEqual(s.button("数据接入").props.disabled, true);
  for (const name of ["本体管理", "本体关系", "智能问答", "数据体检"]) assert.equal(s.button(name).props.disabled, true);
  assert.match(content(s.tree), /上传文件.*空间.*已有运行/);
});

test("data access without a workspace opens the upload flow rather than an empty data page", () => {
  const s = shell();
  assert.ok(s.button("数据接入"));
  s.button("数据接入").props.onClick();
  assert.equal(s.updates.find((change) => change.key === 7)?.value.kind, "new");
});

test("an opened table enables its modules and keeps their existing navigation", () => {
  const s = shell({ saved_as: "run.json", file: { name: "orders.csv", kind: "table" } });
  assert.equal(s.buttons.length, 6);
  assert.ok(s.buttons.every((button) => !button.props.disabled));
  s.button("本体管理").props.onClick();
  assert.equal(s.updates.find((change) => change.key === 5)?.value, "objects");
});

test("document workspaces keep only their supported modules", () => {
  assert.deepEqual(shell({ file: { name: "policy.md", kind: "document" } }).buttons.map(content),
    ["本体库", "本体管理", "本体关系", "数据体检"]);
});
