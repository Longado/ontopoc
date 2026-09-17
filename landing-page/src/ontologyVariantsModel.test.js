import assert from "node:assert/strict";
import test from "node:test";

import { toggleVariant, variantNote, variantRows } from "./ontologyVariantsModel.js";

const ONTOLOGY = { object_types: [{ key: "department", label: "部门" }, { key: "vendor", label: "供应商" }], relations: [] };
const GROUP = { type: "department", label: "部门", values: ["DEPARTMENT OF FLEET", "DEPT OF FLEET"], records: [67, 12], reasoning: "后者是前者的缩写", verdict: "needs_person" };
const run = (variants) => ({ saved_as: "x.json", ontology: ONTOLOGY, evaluation: variants ? { variants } : {} });

test("a candidate is shown with its records and the model's reason, and starts unaccepted", () => {
  const rows = variantRows(run({ groups: [GROUP], rejected: [] }), { variants: [] });
  assert.deepEqual(rows, [{ ...GROUP, accepted: false, carried: false }]);
});

test("accepting a group records only the object and the spellings, and pressing again undoes it", () => {
  const accepted = toggleVariant({ types: {}, variants: [] }, GROUP);
  assert.deepEqual(accepted.variants, [{ type: "department", values: ["DEPARTMENT OF FLEET", "DEPT OF FLEET"] }]);
  assert.deepEqual(variantRows(run({ groups: [GROUP], rejected: [] }), accepted)[0].accepted, true);
  assert.deepEqual(toggleVariant(accepted, GROUP).variants, []);
});

test("a group accepted last time is shown even before this run looks for candidates, and can be dropped", () => {
  const decisions = { variants: [{ type: "department", values: ["A", "B"] }] };
  const rows = variantRows(run(), decisions);
  assert.deepEqual(rows, [{ type: "department", label: "部门", values: ["A", "B"], records: null, reasoning: "", accepted: true, carried: true }]);
  assert.deepEqual(toggleVariant(decisions, rows[0]).variants, []);
});

test("a group whose object is gone from this run is not shown as if it still applied", () => {
  assert.deepEqual(variantRows(run(), { variants: [{ type: "missing", values: ["A", "B"] }] }), []);
});

test("the note says what the model proposed, what code threw out, and why", () => {
  const found = { model: "deepseek-flash", groups: [GROUP], rejected: [{ type: "vendor", values: ["X", "Y"], reason: "这个值不在数据里：X" }], note: "", error: null };
  assert.deepEqual(variantNote(run(found)), { line: "模型 deepseek-flash 提了 1 组，代码丢掉 1 组。", dropped: ["供应商 X、Y：这个值不在数据里：X"] });
  assert.deepEqual(variantNote(run({ model: null, groups: [], rejected: [], note: "这份数据里没有需要对应写法的对象", error: null })),
    { line: "这份数据里没有需要对应写法的对象", dropped: [] });
  assert.equal(variantNote(run()), null);
});
