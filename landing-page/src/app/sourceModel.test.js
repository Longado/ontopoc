import assert from "node:assert/strict";
import test from "node:test";
import { keyColumnsFrom, runSummary, scheduleBody, scheduleProblem, sourceOrigin, sourceProblem } from "./sourceModel.js";
import { originText } from "./format.js";
import { parseRoute, hrefFor, NAV } from "./routeModel.js";

test("a source origin names the source and the table; an upload does not", () => {
  assert.deepEqual(sourceOrigin("source:订单库/public.orders"), { source: "订单库", table: "public.orders" });
  assert.equal(sourceOrigin("upload"), null);
  assert.equal(originText("source:订单库/orders"), "数据源“订单库”的表 orders");
  assert.equal(originText("upload"), "上传");
});

test("the source and schedule addresses open their pages and the sidebar item is built", () => {
  assert.deepEqual(parseRoute("#/sources"), { page: "sources" });
  assert.deepEqual(parseRoute("#/sources/%E8%AE%A2%E5%8D%95%E5%BA%93"), { page: "source", name: "订单库" });
  assert.equal(hrefFor({ page: "source", name: "订单库" }), "#/sources/%E8%AE%A2%E5%8D%95%E5%BA%93");
  assert.deepEqual(parseRoute("#/schedules"), { page: "schedules" });
  const items = NAV.flatMap((g) => g.items);
  assert.equal(items.find((i) => i.key === "sources").built, true);
});

test("a source form says what is missing; editing may leave the password blank", () => {
  const ok = { name: "库", host: "db.example.com", port: "5432", database: "d", username: "u", password: "p" };
  assert.equal(sourceProblem(ok, false), "");
  assert.equal(sourceProblem({ ...ok, password: "" }, false), "要填密码");
  assert.equal(sourceProblem({ ...ok, password: "" }, true), "");
  assert.match(sourceProblem({ ...ok, host: "postgres://u:p@h/d" }, false), /不要带协议/);
  assert.match(sourceProblem({ ...ok, port: "70000" }, false), /端口/);
});

test("a schedule form becomes the request the service takes", () => {
  const sources = [{ name: "库", tables: [{ table: "orders", dataset: "订单" }] }];
  const form = { name: "每天", kind: "source", target: "库", cadence: "weekly", minute: "0", time: "08:30", weekday: "4", tz: "Asia/Taipei", scope: [] };
  assert.equal(scheduleProblem(form, sources, []), "");
  assert.deepEqual(scheduleBody(form), { name: "每天", kind: "source", target: "库", cadence: "weekly", tz: "Asia/Taipei", time: "08:30", weekday: 4 });
  assert.match(scheduleProblem({ ...form, time: "8:30" }, sources, []), /08:30/);
  assert.match(scheduleProblem({ ...form, target: "库", kind: "source" }, [{ name: "库", tables: [] }], []), /还没有读成数据集/);
  assert.deepEqual(scheduleBody({ ...form, cadence: "hourly", minute: "15", scope: ["orders"] }).minute, 15);
});

test("a run in one line: what it did, or why it did not", () => {
  assert.equal(runSummary({ status: "success", rows: 12, version: 2, changed: true, detail: { flagged: ["a", "b"], left_out: [] } }), "12 行，第 2 版，2 项已确认的内容进了“需要再看”");
  assert.equal(runSummary({ status: "success", rows: 12, version: 1, changed: false }), "12 行，第 1 版，和上一版一样，没有写新版本");
  assert.equal(runSummary({ status: "failed", error: "连不上" }), "连不上");
  assert.deepEqual(keyColumnsFrom("订单号, 行号、版本"), ["订单号", "行号", "版本"]);
});
