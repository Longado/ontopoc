import assert from "node:assert/strict";
import test from "node:test";
import { estimateText, keyColumnsFrom, runSummary, scheduleBody, scheduleProblem, sourceBody, sourceOrigin, sourceProblem, tlsDefault } from "./sourceModel.js";
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

test("a host with a port or a CA that is not PEM, or a CA without encryption, is named before the form is sent", () => {
  const ok = { name: "库", host: "db.example.com", port: "5432", database: "d", username: "u", password: "p", tls: "required", ca: "" };
  assert.match(sourceProblem({ ...ok, host: "db.example.com:5432" }, false), /端口/);
  assert.equal(sourceProblem({ ...ok, host: "::1" }, false), "");   // an IPv6 address has colons of its own
  assert.match(sourceProblem({ ...ok, ca: "hello" }, false), /PEM/);
  assert.equal(sourceProblem({ ...ok, ca: "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----" }, false), "");
  assert.match(sourceProblem({ ...ok, tls: "none", ca: "-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----" }, false), /加密/);
});

test("the request carries a CA only when one was pasted, an empty one when it is taken away, and none with encryption off", () => {
  const form = { name: "库", kind: "postgresql", host: "db", port: "5432", database: "d", username: "u", password: "", tls: "required", ca: "", dropCa: false };
  assert.equal("ca_pem" in sourceBody(form, "required"), false);   // left alone: the saved one stays
  assert.equal(sourceBody({ ...form, ca: "PEM" }, "required").ca_pem, "PEM");
  assert.equal(sourceBody({ ...form, dropCa: true }, "required").ca_pem, "");
  assert.equal("ca_pem" in sourceBody({ ...form, ca: "PEM" }, "none"), false);
  const body = sourceBody(form, "required");
  assert.equal(body.port, 5432);
  assert.equal("password" in body, false);   // blank keeps the saved password
  assert.equal("ca" in body || "dropCa" in body, false);
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

test("changing where the password goes needs it typed again; encryption starts on except for this machine; row counts say they are estimates", () => {
  const saved = { host: "db.example.com", port: 5432, database: "d", username: "u" };
  const form = { name: "库", host: "db.example.com", port: "5432", database: "d", username: "u", password: "" };
  assert.equal(sourceProblem(form, true, saved), "");
  assert.match(sourceProblem({ ...form, host: "other.example.com" }, true, saved), /改了主机，要重新填密码/);
  assert.match(sourceProblem({ ...form, port: "5433", username: "v" }, true, saved), /端口、账号/);
  assert.equal(sourceProblem({ ...form, host: "other.example.com", password: "p" }, true, saved), "");
  assert.equal(tlsDefault("localhost"), "none");
  assert.equal(tlsDefault("db.example.com"), "required");
  assert.equal(estimateText(1200), "约 1,200（估计）");
  assert.equal(estimateText(null), "没有估计");
});

test("a run is counted, not named, for a person who may not see the definitions it sent back; a hidden one says only that", () => {
  assert.equal(runSummary({ status: "success", rows: 3, version: 2, changed: true, detail: { flagged_count: 2, left_out: [] } }), "3 行，第 2 版，2 项已确认的内容进了“需要再看”");
  assert.equal(runSummary({ status: "success", hidden: true }), "写进了一个你看不到的数据集");
});
