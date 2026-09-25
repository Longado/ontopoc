import assert from "node:assert/strict";
import test from "node:test";

import { fabricLink } from "./fabricModel.js";

const W = "580f410e-733d-43bd-8a87-be12b536f7ff", L = "d0d863bc-48e1-45b2-8f4b-54795c97ba71";

test("with no ids the definition carries the types alone", () => {
  assert.deepEqual(fabricLink("r 1.json", "", ""), { url: "/api/ontology/runs/r%201.json/export/fabric", note: "只含对象和关系；填上两个 ID 才带数据绑定" });
});

test("with both ids it carries the data bindings", () => {
  assert.deepEqual(fabricLink("r.json", ` ${W} `, L), { url: `/api/ontology/runs/r.json/export/fabric?workspace=${W}&lakehouse=${L}`, note: "带数据绑定" });
});

test("one id, or one that is not a GUID, says what to fix instead of downloading an error", () => {
  assert.deepEqual(fabricLink("r.json", W, ""), { url: null, note: "两个 ID 要一起填" });
  assert.deepEqual(fabricLink("r.json", "my workspace", L), { url: null, note: "ID 要写成 GUID，例如 580f410e-733d-43bd-8a87-be12b536f7ff" });
});
