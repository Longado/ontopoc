import assert from "node:assert/strict";
import test from "node:test";

import { setLocale } from "./i18n/index.js";
import { DOC_ACCEPT, answerFromDocuments, docFileProblem, documentHref, documentLine, limitsText, removedLine } from "./documentModel.js";
import { definitionHref, isAnswer, statusText } from "./qaModel.js";

const QUOTE = "每逾期一日，按逾期部分货款的0.5%支付违约金";
const RECORD = {
  status: "from_documents",
  documents: { line: "以下是文档里的原话，由助手挑选，不是来自数据", quotes: [{ passage: "1-p2", quote: QUOTE, document: "供货合同.md", document_id: "document:abc", version: 2, where: "第 2 段" }] },
  definitions: [{ id: "document:abc", kind: "document", name: "供货合同.md", version: 2, confirmed_by: "Demo builder" }],
};

test("an answer from documents is the documents' own words, each with where it comes from, under the service's line; no sentence of the model's, and no number from the data", () => {
  for (const lang of ["zh", "en"]) {
    setLocale(lang);
    const view = answerFromDocuments(RECORD);
    assert.equal(view.line, "以下是文档里的原话，由助手挑选，不是来自数据");   // the service's own sentence, in the asker's language
    assert.deepEqual(Object.keys(view).sort(), ["line", "quotes"]);
    assert.equal(view.quotes[0].quote, QUOTE);
    assert.equal(view.quotes[0].href, "#/documents/document%3Aabc");
    assert.equal(view.quotes[0].source, lang === "zh" ? "供货合同.md，第 2 段" : "供货合同.md, 第 2 段");
    assert.equal(isAnswer(RECORD), false);   // never read as an answer from the data (no figure, no data-as-of line)
    assert.equal(statusText("from_documents"), lang === "zh" ? "来自文档" : "From documents");
  }
  assert.equal(answerFromDocuments({ status: "answered", answer: { total: 3 } }), null);
  assert.equal(answerFromDocuments({ status: "ontology_gap", documents: { found: false, line: "x" } }), null);
});

test("a document's own page, which holds its passages, counts them", () => {
  setLocale("zh");
  const page = documentLine({ id: "document:abc", name: "供货合同.md", state: "confirmed", version: 2, passages: [{ id: "p1" }, { id: "p2" }], passage_count: 2, confirmed_by: "Demo builder" });
  assert.match(page.meta, /^2 段/);
  assert.doesNotMatch(page.meta, /documents\.passages/);
});

test("a document opens on its own page from an answer's basis", () => {
  assert.equal(definitionHref("document:abc"), "#/documents/document%3Aabc");
  assert.equal(documentHref("document:abc"), "#/documents/document%3Aabc");
});

test("a document in the list says where it stands, how many passages it has and whether it is for builders only", () => {
  setLocale("zh");
  const waiting = documentLine({ id: "document:abc", name: "供货合同.md", state: "checked", version: 1, passages: 4, builders_only: true, proposed_by: "demo-admin", who_can_confirm: ["Demo builder"], may_confirm: false, held: null });
  assert.equal(waiting.state, "checked");
  assert.match(waiting.meta, /4 段/);
  assert.match(waiting.meta, /只给搭建者/);
  assert.match(waiting.by, /demo-admin/);
  assert.match(waiting.who, /Demo builder/);
  setLocale("en");
  const confirmed = documentLine({ id: "document:abc", name: "供货合同.md", state: "confirmed", version: 2, passages: 1, builders_only: false, confirmed_by: "Demo builder", confirmed_at: "2026-11-26T00:00:00+00:00" });
  assert.match(confirmed.meta, /1 passage\b/);
  assert.doesNotMatch(confirmed.meta, /builders/i);
  assert.match(confirmed.by, /Demo builder/);
  assert.equal(confirmed.who, "");
});

test("only the kinds of file the service reads are offered, and an empty or other file is refused before it is sent", () => {
  setLocale("en");
  assert.equal(DOC_ACCEPT, ".md,.txt,.docx,.pdf");
  assert.equal(docFileProblem({ name: "合同.docx", size: 10 }), "");
  assert.match(docFileProblem({ name: "表.xlsx", size: 10 }), /\.md/);
  assert.notEqual(docFileProblem({ name: "空.md", size: 0 }), "");
  assert.notEqual(docFileProblem(null), "");
});

test("the limits are said in both languages", () => {
  const limits = { passage_chars: 600, passages_to_model: 5, max_chars: 200000, max_documents: 50 };
  setLocale("zh");
  assert.match(limitsText(limits), /600/);
  assert.match(limitsText(limits), /5 段/);
  setLocale("en");
  assert.match(limitsText(limits), /200,000 characters/);
  assert.match(limitsText(limits), /50 documents/);
});

test("a confirmed document may be sent back or removed by a builder; a sent-back one shows why, a removed one who removed it and why", () => {
  setLocale("zh");
  const confirmed = documentLine({ id: "document:abc", name: "供货合同.md", state: "confirmed", version: 2, passages: 4, builders_only: false, confirmed_by: "Demo builder", confirmed_at: "2026-11-26T00:00:00+00:00" }, { mayBuild: true });
  assert.equal(confirmed.maySendBack, true);
  assert.equal(confirmed.mayRemove, true);
  assert.equal(documentLine({ id: "document:abc", name: "x.md", state: "confirmed", version: 2, passages: 1 }, { mayBuild: false }).maySendBack, false);
  const back = documentLine({ id: "document:abc", name: "供货合同.md", state: "needs_look", version: 3, passages: 4, reason: "比例写错了", proposed_by: "demo-admin", who_can_confirm: ["Demo builder"] }, { mayBuild: true });
  assert.equal(back.maySendBack, false);
  assert.match(back.reason, /比例写错了/);
  setLocale("en");
  const gone = removedLine({ name: "供货合同.md", removed_by: "Demo builder", removed_at: "2026-11-26T00:00:00+00:00", reason: "void" });
  assert.equal(gone.name, "供货合同.md");
  assert.match(gone.text, /Demo builder/);
  assert.match(gone.text, /void/);
});
