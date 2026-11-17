import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { OP_WORD, KIND_WORD, actionProblem, lastRecordText, recordStateText } from "./actionModel.js";
import { KIND, groupTitle, resultLines } from "./batchModel.js";
import { approveWarning, batchSummary, queueCounts, queueRow } from "./confirmModel.js";
import { CONVERTED } from "./i18n/converted.js";
import { AREAS, getLocale, setLocale } from "./i18n/index.js";
import { OP_LABEL, derivedProblem, hopText, usedByText, waitingText as derivedWaiting } from "./derivedModel.js";
import { CHART_KINDS, GROUP_TOPS, chartMissing, leftOutLines } from "./explorerModel.js";
import { graphNote } from "./objectGraphModel.js";
import { relatedCard, unconfirmedNote } from "./objectModel.js";
import { CARDINALITY_LABEL, matchRateText, previewText, relationProblem, sentBackLine, waitingText } from "./relationModel.js";
import { STATE_LABEL, codeCell, confirmersText, limitedNote, logText, meaningsSummary, reconfirmText, stateLine, stateText, typeSub } from "./typeModel.js";
import { confirmWords, newValueText, rowsText, viewProblem } from "./viewModel.js";

setLocale("en");   // the default; these tests pin the English words of the modelling pages

test("an object type's states and the line under its title read in English", () => {
  assert.deepEqual(["proposed", "checked", "confirmed", "needs_look", "rejected"].map((s) => STATE_LABEL[s]), ["Proposed", "Checked", "Confirmed", "Needs review", "Sent back"]);
  assert.equal(stateText({ model_draft: true }), "Model draft");
  assert.equal(stateText({}), "No meanings yet");
  assert.equal(typeSub({ dataset: "orders", dataset_version: 2, rows: 160 }), "From orders v2 · 160 objects");
  assert.equal(typeSub({ dataset: "orders", dataset_version: 2, rows: 1, rows_limited: true }, "3 days ago, Ann"), "From orders v2 (uploaded 3 days ago, Ann) · you can see 1 object");
  assert.equal(meaningsSummary({ values: [{ label: "a" }, { label: "" }] }), "2 values, 1 with a meaning");
  assert.equal(stateLine({ state: "proposed", proposed_by: "ann", can_confirm: false }, "This object type"), "Proposed by ann. Needs another builder to confirm");
  assert.equal(stateLine({ state: "rejected" }, "x"), "Sent back; fix it and save again, then another builder confirms");
  assert.equal(reconfirmText(["ann", "bob"]), "The data was updated; waiting for ann, bob to confirm again");
  assert.equal(confirmersText({ confirmers: ["ann"], can_confirm: false }), "Can confirm: ann");
  assert.equal(limitedNote({ rows_limited: true, rows: 40 }), "A row rule limits you: only the 40 rows you can read are counted");
  assert.equal(codeCell("1", { state: "needs_look", labels: {} }).note, "Meaning needs review");
});

test("the log reads as English sentences", () => {
  assert.deepEqual(logText({ who: "ann", element: "type", change: "confirmed" }), { who: "ann", text: "Confirmed the object type" });
  assert.deepEqual(logText({ who: "ann", element: "meaning", column: "status", change: "sent_back", reason: "wrong" }), { who: "ann", text: "Sent back the meanings of “status”: wrong" });
  assert.equal(logText({ who: "bob", element: "dataset", change: "import v3" }).text, "Uploaded v3");
  assert.equal(logText({ who: "x", element: "view", change: "weird" }).text, "The view: weird");
  assert.equal(logText({ who: "x", element: "type", change: "needs_look", reason: "data moved" }).who, "System");
});

test("derived properties and views say what is missing", () => {
  assert.equal(derivedProblem({ name: "", english_name: "", kind: "function", expression: "" }), "Write a name");
  assert.equal(derivedProblem({ name: "x", english_name: "1", kind: "function", expression: "" }), "The identifier may use only letters, digits and underscores, and must start with a letter");
  assert.equal(hopText({ name: "Order belongs to customer", toward: "one" }), "Order belongs to customer: to the “one” side (each object has just one)");
  assert.equal(usedByText({ answers: 2, views: 0, actions: 1 }), "Used by 2 answers / 0 views / 1 actions");
  assert.equal(derivedWaiting({ waiting_on: [{ name: "Order" }, { name: "Customer" }] }), "Confirm “Order”, “Customer” first; then this derived property can be confirmed");
  assert.deepEqual([OP_LABEL.is, OP_LABEL.is_not], ["is", "is not"]);
  assert.equal(viewProblem({ name: "", filters: [], latest: { on: false, key: [], order: "" } }), "Write a name for the view");
  assert.equal(rowsText({ rows: 144, of: 160 }), "144 / 160 rows");
  assert.equal(newValueText({ column: "status", value: "3", label: "Shipped", rows: 5 }), "“status” has a new value 3 (Shipped), 5 rows: include it?");
  assert.equal(confirmWords([{ choice: "out" }]), "Add this condition and hand it to another builder to confirm");
});

test("actions read in English", () => {
  assert.deepEqual(["eq", "empty"].map((k) => OP_WORD[k]), ["equals", "is empty"]);
  assert.deepEqual(Object.values(KIND_WORD), ["Edit an object", "Create an object", "Delete an object"]);
  assert.equal(actionProblem({ name: "", kind: "edit", properties: [] }), "Write a name for the action");
  assert.equal(recordStateText({ state: "pending", stale: true }), "Awaiting approval (data changed)");
  assert.equal(recordStateText({ state: "approved", undo_of: 4 }), "Approved (undoes #4)");
  assert.equal(lastRecordText([]), "Nothing submitted yet");
});

test("the review queue speaks English: approve a data change, confirm a definition, send back with a reason", () => {
  assert.equal(KIND.approval, "Data change");
  assert.equal(groupTitle("orders", 2, 4), "orders v2 moved these 4 items, which need another look");
  assert.equal(approveWarning({ kind: "approval", dataset: "orders", readers: 3 }), "Once approved, the “orders” dataset gets a new version, and the 3 confirmed definitions that use it are checked again and may need review.");
  assert.equal(approveWarning({ kind: "approval", readers: 0 }), "Once approved, the dataset gets a new version. No confirmed definition uses it now.");
  assert.equal(queueCounts({ items: [{ can_confirm: true }, { can_confirm: false }] }).text, "2 items, 1 of which you can confirm now");
  assert.equal(queueCounts({ items: [] }).text, "Nothing to review");
  assert.equal(batchSummary([{ ok: true, title: "a" }, { ok: false, title: "b", error: "gone" }]), "Confirmed 1 item; 1 did not go through: b (gone)");
  assert.equal(queueRow({ kind: "approval", can_confirm: true, lines: [], title: "t" }).verb, "Approve");
  assert.equal(queueRow({ kind: "type", can_confirm: true, lines: [], title: "t" }).verb, "Confirm");
  assert.deepEqual(resultLines({ confirmed: [{ title: "a" }, { title: "b" }], sent_on: [], left_out: [{ title: "c", why: "it changed" }] }), ["Confirmed 2: a, b", "c: not confirmed, it changed"]);
});

test("relations read in English", () => {
  assert.deepEqual(Object.values(CARDINALITY_LABEL), ["Many to one", "One to many", "One to one"]);
  assert.equal(matchRateText({ connected: 157, of: 160 }), "157 / 160 rows connected (98%)");
  assert.equal(matchRateText({ connected: null }), "Can't be checked right now");
  assert.equal(previewText({ rows: 160, matched: 157, unmatched: 3, empty: 0, samples: [{ key: "A1" }] }), "157/160 rows can connect, 3 rows have no match (A1)");
  assert.equal(previewText({ rows: 5, matched: 5 }), "All 5 rows can connect");
  assert.equal(sentBackLine({ state: "rejected", reason: "wrong key" }), "Sent back: wrong key");
  assert.equal(waitingText({ waiting_on: [{ name: "Order" }] }), "Confirm object type “Order” first; then this relation can be confirmed");
  assert.equal(relationProblem({ name: "", english: "", from: "", to: "" }, false), "Write a name");
});

test("the explorer and the object page read in English", () => {
  assert.deepEqual(CHART_KINDS.map(([, label]) => label), ["Number", "Bar", "Pie", "Histogram", "Summary table"]);
  assert.deepEqual(GROUP_TOPS.map(([, label]) => label), ["All", "Top 5", "Top 10", "Top 20"]);
  assert.equal(chartMissing({ kind: "bar", group: "" }), "Choose the column to group by");
  assert.deepEqual(leftOutLines({ groups_hidden: 2, hidden_groups: [{ label: "A", rows: 3 }, { label: "B", rows: 1 }], rows_hidden: 4 }), ["Not drawn: A (3 rows), B (1 row)"]);
  assert.equal(graphNote({ nodes: [{ start: true }, {}, {}], starts: 1, shown: 1, cut: true }), "Showing all 1 start objects, and the 2 objects they connect to; too many objects connect, so only some are drawn");
  assert.equal(relatedCard({ count: 12, objects: [{ n: 1, text: "K1", name: "Acme" }] }).more, "and 12 more");
  assert.equal(unconfirmedNote([{ confirmed: false, name: "Order belongs to customer" }]), "1 relation is not confirmed yet: Order belongs to customer. The related objects may change.");
});

test("every modelling file is in the no-Chinese check, and every key it uses exists in both languages", () => {
  const files = ["ConfirmGroupPage.jsx", "ConfirmPage.jsx", "Explorer.jsx", "ObjectGraph.jsx", "ObjectPage.jsx", "RelationForm.jsx", "RelationGraph.jsx", "RelationsPage.jsx", "TypeActions.jsx", "TypeDerived.jsx", "TypeForm.jsx", "TypePage.jsx", "TypeViews.jsx", "TypesPage.jsx",
    "actionModel.js", "batchModel.js", "confirmModel.js", "derivedModel.js", "explorerModel.js", "objectGraphModel.js", "objectModel.js", "relationModel.js", "typeModel.js", "viewModel.js"];
  const missing = [];
  for (const file of files) {
    assert.ok(CONVERTED.includes(file), `${file} is missing from converted.js`);
    const text = readFileSync(fileURLToPath(new URL(`./${file}`, import.meta.url)), "utf8");
    for (const [, area, key] of text.matchAll(/"(types|actions|review|relations|objects)\.([A-Za-z_][A-Za-z0-9_.]*)"/g)) {
      for (const loc of ["en", "zh"]) {
        const dict = AREAS[loc][area];
        const prefix = Object.keys(dict).some((k) => k.startsWith(`${key}.`));   // a group of words read one by one
        if (!prefix && !(key in dict) && !(`${key}_one` in dict && `${key}_other` in dict)) missing.push(`${loc}: ${area}.${key} (${file})`);
      }
    }
  }
  assert.deepEqual(missing, []);
  assert.equal(getLocale(), "en");
});
