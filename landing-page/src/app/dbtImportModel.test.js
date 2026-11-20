import assert from "node:assert/strict";
import test from "node:test";

import { MANIFEST_LIMIT_MB, codeLine, fileProblem, importSections, importSummary, relationLine, typeLine } from "./dbtImportModel.js";
import { logText } from "./typeModel.js";
import { setLocale } from "./i18n/index.js";

// What the service answers for the orders/customers manifest (tests/test_dbt_import.py), trimmed to what the dialog reads.
const ORDERS = { model: "orders", id: "orders", name: "orders", dataset: "orders", key: ["order_id"], properties: ["order_id", "customer_id", "status"], codes: ["status"], status: "new", state: "checked", key_rows: 6, warnings: [] };
const CUSTOMERS = { ...ORDERS, model: "customers", id: "customers", name: "customers", dataset: "customers", key: ["customer_id"], properties: ["customer_id"], codes: [], key_rows: 3 };
const RELATION = { id: "orders_customer_id", model: "orders", from: "orders", to: "customers", from_column: "customer_id", to_column: "customer_id", cardinality: "many_to_one",
  status: "new", state: "checked", numbers: { rows: 6, matched: 4, unmatched: 1, empty: 1, fan_keys: 0 }, cardinality_holds: true, warnings: [] };
const STATUS_CODES = { type: "orders", column: "status", values: ["placed", "shipped", "completed", "returned"], code_column: true, note: null };
const PREVIEW = {
  applied: false, manifest: { schema_version: 12, dbt_version: "1.8.0", project: "shop", models: 4, tests: 11, note: null },
  types: [CUSTOMERS, ORDERS], relations: [RELATION], codes: [STATUS_CODES], unmatched_models: ["payments"],
  skipped: [{ model: "order_items", what: "object type", reason: "No key in the tests: ..." }], left_out: [], failed: [], not_attempted: [], stopped: false, more: { types: 0, relations: 0, codes: 0, unmatched_models: 0, skipped: 0, left_out: 0 }, limits: { proposals: 50, megabytes: 20 },
};

test("a file over the service's limit is refused before it is sent; one within it is not", () => {
  setLocale("en");
  assert.equal(MANIFEST_LIMIT_MB, 20);
  assert.equal(fileProblem({ name: "manifest.json", size: 21 * 1024 * 1024 }), "This file is 21 MB; at most 20 MB is read. Use the manifest.json dbt writes to target/.");
  assert.equal(fileProblem({ name: "manifest.json", size: 900_000 }), "");
  assert.equal(fileProblem(null), "");
});

test("each proposal reads as one line: the key and the full-data check for a type, the connected rows for a relation, the codes still to mean something", () => {
  setLocale("en");
  assert.equal(typeLine(ORDERS), "orders (dataset orders): key order_id, unique and filled on all 6 rows; properties order_id, customer_id, status");
  assert.equal(typeLine({ ...ORDERS, status: "already_there", state: "confirmed" }), "orders: already there (Confirmed), left as it is");
  assert.equal(relationLine(RELATION), "orders.customer_id → customers.customer_id, many to one: 4 of 6 rows connect; 1 points to nothing in customers; 1 empty");
  assert.equal(relationLine({ ...RELATION, status: "already_there", numbers: null }), "orders_customer_id: already there (Checked), left as it is");
  assert.equal(codeLine(STATUS_CODES), "orders.status: placed, shipped, completed, returned. dbt lists the values, not what they mean: write the meanings on the type's page");
  assert.match(codeLine({ ...STATUS_CODES, code_column: false, note: "Not a code column here" }), /Not a code column here$/);
});

test("the preview says what would be proposed and offers Apply only when something is new; after Apply it says what was put forward", () => {
  setLocale("en");
  assert.deepEqual(importSummary(PREVIEW), { fresh: 3, already: 0, canApply: true, headline: "Would propose 2 object types and 1 relation. Nothing is written until you apply." });
  const again = { ...PREVIEW, types: PREVIEW.types.map((x) => ({ ...x, status: "already_there" })), relations: [{ ...RELATION, status: "already_there" }], codes: [] };
  assert.deepEqual(importSummary(again), { fresh: 0, already: 3, canApply: false, headline: "Nothing new to propose: 3 are already there." });
  assert.equal(importSummary({ ...PREVIEW, applied: true }).headline, "Proposed 2 object types and 1 relation. Each waits for another builder to confirm.");
  assert.equal(importSummary({ ...PREVIEW, applied: true }).canApply, false);
  const sections = importSections(PREVIEW);
  assert.deepEqual(sections.map((s) => s.id), ["types", "relations", "codes", "unmatched", "skipped"]);
  assert.equal(sections[0].items[1].href, "#/types/orders/props");
  assert.equal(sections[1].items[0].href, "#/relations/orders_customer_id");
  assert.equal(sections[3].items[0].text, "payments");
  assert.equal(sections[4].items[0].text, "order_items, object type: No key in the tests: ...");
  assert.equal(importSections({ ...PREVIEW, more: { skipped: 4 } }).find((s) => s.id === "skipped").more, "And 4 more not listed");
  assert.equal(importSections({ ...PREVIEW, more: { unmatched_models: 1 } }).find((s) => s.id === "unmatched").more, "And 1 more not listed");
  assert.deepEqual(importSections({ ...PREVIEW, left_out: [{ what: "relation x", reason: "One import proposes at most 50" }] }).map((s) => s.id).at(-1), "leftOut");
});

test("after a failure mid-run the dialog says what was written, what failed and why, and what was not tried", () => {
  setLocale("en");
  const stopped = { ...PREVIEW, applied: true, stopped: true, types: [CUSTOMERS], relations: [], codes: [],
    failed: [{ what: "object type orders", reason: "It failed (RecursionError: deep); this one was not written and the import stopped here" }],
    not_attempted: [{ what: "relationships orders.customer_id → customers" }] };
  const summary = importSummary(stopped);
  assert.equal(summary.headline, "Stopped on an error. Proposed 1 object type before it; what follows was not tried.");
  assert.equal(summary.canApply, false);
  const sections = importSections(stopped);
  assert.deepEqual(sections.map((s) => s.id), ["types", "failed", "notAttempted", "unmatched", "skipped"]);
  assert.equal(sections[1].items[0].text, "object type orders: It failed (RecursionError: deep); this one was not written and the import stopped here");
  assert.equal(sections[2].items[0].text, "relationships orders.customer_id → customers");
  assert.equal(sections[1].note, "Skipped means a check refused one item and the import went on; failed means an unexpected error stopped the import there.");
  const previewStopped = { ...stopped, applied: false };
  assert.equal(importSummary(previewStopped).headline, "Stopped on an error. It would have proposed 1 object type before it; nothing was written.");
  assert.equal(importSummary(previewStopped).canApply, false);
  setLocale("zh");
  assert.equal(importSummary(stopped).headline, "出错停下了。之前提出了 1 个对象类型；后面的没有做。");
  assert.equal(importSummary(previewStopped).headline, "出错停下了。出错之前本会提出 1 个对象类型；什么都没有写入。");
  setLocale("en");
});

test("a proposal written whose details could not be read back, or whose counts a limit keeps, reads as written, with no numbers", () => {
  setLocale("en");
  assert.equal(typeLine({ id: "customers", name: "customers", dataset: null, key: [], properties: [], status: "new" }), "customers: written; its details are on its page");
  assert.equal(relationLine({ ...RELATION, numbers: null }), "orders_customer_id: written; its details are on its page");
  setLocale("zh");
  assert.equal(relationLine({ ...RELATION, numbers: null }), "orders_customer_id：已经写入，详情见它自己的页面");
  setLocale("en");
});

test("no line of a stopped preview says written, in either language", () => {
  const preview = { ...PREVIEW, applied: false, stopped: true,
    types: [CUSTOMERS, { id: "orders", name: "orders", dataset: null, key: [], properties: [], codes: [], status: "new" }], relations: [{ ...RELATION, numbers: null }],
    failed: [{ what: "object type orders", reason: "(the service's sentence)" }], not_attempted: [{ what: "relationships orders.customer_id → customers" }] };
  for (const locale of ["en", "zh"]) {
    setLocale(locale);
    const lines = [importSummary(preview).headline, importSummary({ ...preview, stopped: false }).headline,
      ...importSections(preview).flatMap((s) => [s.title, s.note ?? "", s.more ?? "", ...s.items.map((i) => i.text)])];
    for (const line of lines) {
      assert.doesNotMatch(line, /written/i, line);
      assert.doesNotMatch(line, /写入/, line);
    }
  }
  setLocale("en");
});

test("the type's log names the import as where a definition came from", () => {
  setLocale("en");
  assert.equal(logText({ element: "type", change: "dbt_import", who: "Ann" }).text, "Proposed the object type from a dbt manifest");
  setLocale("zh");
  assert.equal(logText({ element: "relation", change: "dbt_import", who: "Ann" }).text, "从 dbt manifest 导入，提出了关系");
  assert.equal(importSummary(PREVIEW).headline, "会提出 2 个对象类型、1 个关系。点“应用”之前什么都不会写入。");
  setLocale("en");
});
