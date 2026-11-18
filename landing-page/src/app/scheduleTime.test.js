import assert from "node:assert/strict";
import test from "node:test";
import { browserZone, hourOptions, minuteOptions, timeFromParts, timeParts } from "./scheduleTime.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

test("the schedule time zone starts as the browser's, UTC when the browser says nothing", () => {
  assert.equal(browserZone(() => ({ resolvedOptions: () => ({ timeZone: "Asia/Shanghai" }) })), "Asia/Shanghai");
  assert.equal(browserZone(() => ({ resolvedOptions: () => ({}) })), "UTC");
  assert.equal(browserZone(() => { throw new Error("no Intl"); }), "UTC");
});

test("a 24-hour time is picked as hour and minute and put back together", () => {
  assert.deepEqual(timeParts("08:30"), { h: "08", m: "30" });
  assert.deepEqual(timeParts("bad"), { h: "08", m: "00" });
  assert.equal(timeFromParts("07", "05"), "07:05");
  assert.equal(hourOptions.length, 24);
  assert.equal(hourOptions[0], "00");
  assert.equal(hourOptions[23], "23");
  assert.deepEqual(minuteOptions, ["00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"]);
});

test("a minute that is not on the five-minute grid is still kept", () => {
  assert.deepEqual(timeParts("09:07"), { h: "09", m: "07" });
});
