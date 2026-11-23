import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { getLocale, setLocale } from "./i18n/index.js";
import { refusalBranch } from "./qaModel.js";

// A refusal of a kind the card has no branch for says why in the service's own sentence (in the asker's language), so a new kind is never a bare "No answer".
test("a refusal whose kind has no branch of its own shows the service's reason, in either language", () => {
  const zh = "“amount”是管道“P1”关联后写出的数：关联把一行变成了几行，这个数重复了，加起来会把同一笔算好几次，所以不算。";
  const before = getLocale();
  const en = "\"amount\" was written by the pipeline \"P1\" after a join turned one row into several: the figure repeats, and adding it up would count the same amount several times";
  for (const language of ["zh", "en"]) {
    setLocale(language);
    const reason = language === "zh" ? zh : en;
    for (const refusal of [{ kind: "repeated" }, { kind: "not_measured", dataset: "line_amounts", version: 1 }, { kind: "unwalkable" }, { kind: "a_kind_not_written_yet" }, undefined]) {
      assert.deepEqual(refusalBranch({ status: "query_limit", reason, refusal }), { kind: "reason", text: reason }, JSON.stringify(refusal));
    }
    for (const kind of ["unsettled", "not_in_scope", "definition_unmet"]) {
      assert.equal(refusalBranch({ status: "refused", reason, refusal: { kind } }).kind, kind);
    }
  }
  setLocale(before);
});

test("the Q&A refusal card reads its branch from the model: no kind falls through without a reason", () => {
  const page = readFileSync(new URL("./QaPage.jsx", import.meta.url), "utf8");
  const card = page.slice(page.indexOf("function Refusal("), page.indexOf("export function Answer("));
  assert.match(card, /refusalBranch\(record\)/);
  assert.doesNotMatch(card, /\{!r && /);
});
