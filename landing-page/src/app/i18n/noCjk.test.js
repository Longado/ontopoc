import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { CONVERTED } from "./converted.js";

const CJK = /[㐀-鿿＀-￯　-〿]/;

/** The source with block comments and whole-line or trailing // comments removed (a "//" glued to a word, as in a URL, is not a comment). */
export function withoutComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");
}

test("the comment stripper keeps URLs and strings", () => {
  assert.equal(withoutComments('a("http://x") // 中文'), 'a("http://x") ');
  assert.equal(withoutComments("/** 中文 */ const a = 1;"), " const a = 1;");
  assert.equal(withoutComments("{/* 中文 */}<p>x</p>"), "{}<p>x</p>");
});

test("converted files hold no Chinese outside comments", () => {
  for (const file of CONVERTED) {
    const text = withoutComments(readFileSync(fileURLToPath(new URL(`../${file}`, import.meta.url)), "utf8"));
    const hits = text.split("\n").map((line, i) => [i + 1, line]).filter(([, line]) => CJK.test(line));
    assert.deepEqual(hits.map(([n, l]) => `${file}:${n} ${l.trim().slice(0, 80)}`), [], `${file} still has Chinese literals`);
  }
});
