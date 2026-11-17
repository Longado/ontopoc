import assert from "node:assert/strict";
import test from "node:test";

import { queryOf, searchWord } from "./explorerModel.js";

test("a search word is part of the query only when it says something (W3)", () => {
  assert.deepEqual(queryOf({ type: "order", search: "  KH022 " }), { type: "order", view: null, filters: [], rows: null, pivot: null, search: "KH022" });
  assert.deepEqual(queryOf({ type: "order", search: "   " }), { type: "order", view: null, filters: [], rows: null, pivot: null });
  assert.equal(searchWord({ search: "x" }), "x");
  assert.equal(searchWord(null), "");
});
