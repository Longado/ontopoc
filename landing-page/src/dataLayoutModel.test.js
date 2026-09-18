import assert from "node:assert/strict";
import test from "node:test";

import { askSuggestions, bridgeLines, layoutTables, latestAsked } from "./dataLayoutModel.js";

const bridge = { from_source: "tw_company_directors", from_field: "統一編號", to_source: "tw_company_registry", to_field: "統一編號", rows: 1573, linked_rows: 1573 };

function run(extra = {}) {
  return {
    sources: [{ name: "tw_company_registry", rows: 150, fields: 18 }, { name: "tw_company_directors", rows: 1573, fields: 5, skipped_rows: ["董監事名單"] }],
    evaluation: { data_fit: { source_groups: [["tw_company_registry"], ["tw_company_directors"]], bridges: [bridge] },
      handover: { sources: [
        { name: "tw_company_registry", rows: 150, skipped_rows: [], fields: [{ path: "統一編號", type: "VARCHAR", length: 8, empty: 0 }] },
        { name: "tw_company_directors", rows: 1573, skipped_rows: ["董監事名單"], fields: [{ path: "持有股份數", type: "INTEGER", length: 10, empty: 12 }] }] } },
    ...extra,
  };
}

test("a bridge is said with both tables, both columns and how many rows connect", () => {
  assert.deepEqual(bridgeLines(run()), ["tw_company_directors 的「統一編號」有 1573 / 1573 行，能在 tw_company_registry 的「統一編號」里找到"]);
  const connected = run();
  connected.evaluation.data_fit = { source_groups: [["a", "b"]] };   // an older run, or tables already joined
  assert.deepEqual(bridgeLines(connected), []);
});

test("each table is laid out with its size, skipped title lines and column shapes", () => {
  const [first, second] = layoutTables(run());
  assert.deepEqual([first.name, first.rows, first.fields.length, first.skipped], ["tw_company_registry", 150, 1, []]);
  assert.deepEqual(second.skipped, ["董監事名單"]);
  assert.deepEqual(second.fields[0], { path: "持有股份數", type: "INTEGER", length: 10, empty: 12 });
  assert.equal(second.group, 1);   // which connected group it sits in, so unconnected tables can be shown apart
});

test("a run saved before columns were profiled still lists its tables, with no column detail", () => {
  const old = run();
  delete old.evaluation.handover;
  const tables = layoutTables(old);
  assert.deepEqual(tables.map((t) => [t.name, t.rows, t.fields]), [["tw_company_registry", 150, null], ["tw_company_directors", 1573, null]]);
  assert.deepEqual(tables[1].skipped, ["董監事名單"]);
});

const item = (question, status = "answered") => ({ question, status, query: { start: "order", via: [] }, answer: { total: 1 } });

test("suggestions are this run's own answered questions, at most three, not generic examples", () => {
  const withQs = run();
  withQs.evaluation.questions = { items: [item("甲"), item("乙", "query_limit"), item("丙"), item("丁"), item("戊")] };
  assert.deepEqual(askSuggestions(withQs).map((i) => i.question), ["甲", "丙", "丁"]);
  assert.deepEqual(askSuggestions(run()), []);
});

test("the answer to show under the box is the last question asked", () => {
  const asked = run();
  asked.evaluation.asked = [{ items: [item("第一问")] }, { items: [item("第二问")] }];
  assert.equal(latestAsked(asked).question, "第二问");
  asked.evaluation.asked.push({ items: [], error: "模型请求失败：timed out" });
  assert.deepEqual(latestAsked(asked), { error: "模型请求失败：timed out" });
  assert.equal(latestAsked(run()), null);
});
