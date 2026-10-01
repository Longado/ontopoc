import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { transformSync } from "esbuild";

import * as upload from "./ontologyUploadModel.js";

// Execute the actual UploadTab with queued state updates, without a browser or model service.
const source = readFileSync(new URL("./OntologyStudio.jsx", import.meta.url), "utf8");
const component = source.slice(source.indexOf("function UploadTab("), source.indexOf("\nfunction Hint("));
const compiled = transformSync(component, { loader: "jsx", jsxFactory: "element", jsxFragment: "fragment" }).code;
const element = (type, props, ...children) => ({ type, props: { ...props, children } });
const file = (name, size) => ({ name, size });
const find = (node, type) => node?.type === type ? node
  : (node?.props?.children || []).flat(Infinity).map((child) => find(child, type)).find(Boolean);

function uploadInput(initial = []) {
  let files = initial;
  const pending = [];
  let stateIndex = 0;
  const useState = (value) => stateIndex++ === 0 ? [files, (update) => pending.push(update)] : [value, () => {}];
  const dependencies = { ...upload, useState, useEffect: () => {}, element, fragment: "fragment",
    earlierVersionOf: () => null, EXAMPLE_QUESTIONS: [], SendPreview: "preview", Progress: "progress" };
  const UploadTab = new Function(...Object.keys(dependencies), `${compiled}\nreturn UploadTab;`)(...Object.values(dependencies));
  const tree = UploadTab({ health: "ready", busy: false, runs: [] });
  return { input: find(tree, "input"), flush: () => { for (const update of pending.splice(0)) files = update(files); return files; } };
}

function liveInput(selected) {
  let contents = selected;
  return {
    files: { *[Symbol.iterator]() { yield* contents; } },
    set value(value) { assert.equal(value, ""); contents = []; },
  };
}

test("the file input keeps its live selection after resetting the input before a queued update", () => {
  const selected = [file("客户.csv", 10), file("订单.csv", 20)];
  const { input, flush } = uploadInput();
  const target = liveInput(selected);
  input.props.onChange({ target });
  assert.deepEqual([...target.files], [], "input reset empties the live selection before React applies the update");
  assert.deepEqual(flush(), selected);
});

test("successive selections add multiple files while deduplicating a reselected file", () => {
  const first = file("客户.csv", 10), second = file("订单.csv", 20), third = file("明细.xlsx", 30);
  const { input, flush } = uploadInput([first]);
  input.props.onChange({ target: liveInput([file("客户.csv", 10), second]) });
  input.props.onChange({ target: liveInput([third]) });
  assert.deepEqual(flush(), [first, second, third]);
});

test("a removed file can be selected again and files sharing a name but differing in size remain distinct", () => {
  const selected = [file("客户.csv", 10), file("客户.csv", 12)];
  const { input, flush } = uploadInput();
  input.props.onChange({ target: liveInput(selected) });
  assert.deepEqual(flush(), selected);
});
