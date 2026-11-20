import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { AREAS, formatDate, formatDateTime, formatNumber, getLocale, pickLocale, setLocale, t } from "./index.js";

test("t: plain keys, interpolation and a missing variable", () => {
  setLocale("en");
  assert.equal(t("common.save"), "Save");
  assert.equal(t("common.signedInAs", { name: "Ann" }), "Signed in as Ann");
  assert.equal(t("common.signedInAs"), "Signed in as {name}");
});

test("t: plural by count with _one and _other", () => {
  setLocale("en");
  assert.equal(t("common.items", { count: 1 }), "1 item");
  assert.equal(t("common.items", { count: 0 }), "0 items");
  assert.equal(t("common.items", { count: 5 }), "5 items");
  setLocale("zh");
  assert.equal(t("common.items", { count: 1 }), "1 项");
  assert.equal(t("common.items", { count: 5 }), "5 项");
  setLocale("en");
});

test("t: a key missing in zh falls back to en; a key missing everywhere returns the key", () => {
  AREAS.en.probe = { only: "English only" };
  AREAS.zh.probe = {};
  setLocale("zh");
  assert.equal(t("probe.only"), "English only");
  assert.equal(t("nope.nothing"), "nope.nothing");
  assert.equal(t("common.nothing"), "common.nothing");
  delete AREAS.en.probe;
  delete AREAS.zh.probe;
  setLocale("en");
});

test("locale: default en, setLocale switches, unknown locales are refused", () => {
  setLocale("en");
  assert.equal(getLocale(), "en");
  setLocale("zh");
  assert.equal(getLocale(), "zh");
  setLocale("fr");
  assert.equal(getLocale(), "zh");
  setLocale("en");
});

test("locale on first open: a stored choice wins, else the browser's first language the app has, else en", () => {
  assert.equal(pickLocale(null, ["zh-CN", "en-US"]), "zh");
  assert.equal(pickLocale(null, ["zh-TW"]), "zh");
  assert.equal(pickLocale(null, ["fr-FR", "zh-CN"]), "zh");
  assert.equal(pickLocale(null, ["en-GB", "zh-CN"]), "en");
  assert.equal(pickLocale(null, ["fr-FR"]), "en");
  assert.equal(pickLocale(null, []), "en");
  assert.equal(pickLocale(null, undefined), "en");
  assert.equal(pickLocale("en", ["zh-CN"]), "en");   // the person's own choice, kept
  assert.equal(pickLocale("zh", ["en-US"]), "zh");
  assert.equal(pickLocale("fr", ["zh-CN"]), "zh");   // a stored value the app does not have is ignored
});

test("formatters follow the locale", () => {
  const d = new Date(2026, 10, 16, 14, 5);
  setLocale("en");
  assert.match(formatDate(d), /Nov 16, 2026/);
  assert.match(formatDateTime(d), /Nov 16, 2026/);
  assert.equal(formatNumber(1234567), "1,234,567");
  setLocale("zh");
  assert.match(formatDate(d), /2026/);
  assert.equal(formatDate("not a date"), "");
  setLocale("en");
});

test("en and zh hold the same files and the same keys per area, and every area is registered", () => {
  const dir = (l) => readdirSync(fileURLToPath(new URL(`./${l}/`, import.meta.url))).filter((f) => f.endsWith(".js")).map((f) => f.slice(0, -3)).sort();
  assert.deepEqual(dir("zh"), dir("en"));
  assert.deepEqual(Object.keys(AREAS.en).sort(), dir("en"));
  assert.deepEqual(Object.keys(AREAS.zh).sort(), dir("en"));
  for (const area of dir("en")) {
    assert.deepEqual(Object.keys(AREAS.zh[area]).sort(), Object.keys(AREAS.en[area]).sort(), `${area}: key sets differ`);
  }
});
