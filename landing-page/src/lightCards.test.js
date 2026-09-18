import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const studio = await readFile(new URL("./OntologyStudio.jsx", import.meta.url), "utf8");
const before = (text) => studio.slice(Math.max(0, studio.indexOf(text) - 40), studio.indexOf(text));

test("long explanations sit behind a hint, so a card opens on its result", () => {
  assert.match(studio, /function Hint\(/);
  for (const text of ["上面那项检查管的是同一个编号被写歪", "前面的检查只能说明本体和数据对得上", "标准答案有两种来源", "模型每次出的题都不一样", "模型每次搭的本体会有出入"]) {
    assert.ok(studio.includes(text), text);
    assert.match(before(text), /<Hint>\s*$/, `${text} should open inside <Hint>`);
  }
});

test("a sentence that stops a misreading stays on the card", () => {
  assert.match(before("判\"对\"的意思是"), /<p className="pr-muted">$/);
});

test("the data check is a grid of cells, not a list of sentences", () => {
  assert.match(studio, /className="os-check-grid"/);
});
