import assert from "node:assert/strict";
import test from "node:test";

import { blankView, codedColumns, setViewChoice, viewBody, viewLine, viewProblem } from "./viewsModel.js";

const meanings = { "订单.状态码": { labels: { 0: "进行中", 1: "已交付", 2: "已取消" } }, "订单.客户等级": { labels: {} }, "客户.客户等级": { labels: { A: "大客户", B: "大客户" } } };

test("only the code columns with a confirmed meaning are offered, each with its meanings once", () => {
  assert.deepEqual(codedColumns(meanings, "订单"), [{ column: "状态码", labels: ["进行中", "已交付", "已取消"] }]);
  assert.deepEqual(codedColumns(meanings, "客户"), [{ column: "客户等级", labels: ["大客户"] }]);
  assert.deepEqual(codedColumns(null, "订单"), []);
});

test("the form asks for what its kind needs, and a new table or kind clears what hung on the old one", () => {
  const form = blankView([{ name: "订单" }]);
  assert.equal(viewProblem(form), "给视图起个名字");
  assert.equal(viewProblem({ ...form, name: "有效订单" }), "选一个有已确认含义的代码列");
  assert.equal(viewProblem({ ...form, name: "有效订单", column: "状态码" }), "选一个含义");
  assert.equal(viewProblem({ ...form, name: "有效订单", column: "状态码", label: "已取消" }), "");
  const latest = { ...form, name: "最新快照", kind: "latest", base: "库存快照" };
  assert.equal(viewProblem(latest), "选用来认出同一个对象的列");
  assert.equal(viewProblem({ ...latest, key: "产品编号", order: "产品编号" }), "编号列和比先后的列要不同");
  assert.equal(viewProblem({ ...latest, key: "产品编号", order: "快照月份" }), "");
  assert.deepEqual(setViewChoice({ ...form, column: "状态码", label: "已取消" }, { column: "客户等级" }).label, "");
  assert.equal(setViewChoice({ ...form, column: "状态码", label: "已取消" }, { base: "客户" }).column, "");
});

test("the request is the plain definition", () => {
  assert.deepEqual(viewBody({ ...blankView([{ name: "订单" }]), name: " 有效订单 ", column: "状态码", label: "已取消" }),
    { name: "有效订单", kind: "filter", base: "订单", column: "状态码", op: "is_not", label: "已取消" });
  assert.deepEqual(viewBody({ ...blankView([]), name: "最新快照", kind: "latest", base: "库存快照", key: "产品编号", order: "快照月份" }),
    { name: "最新快照", kind: "latest", base: "库存快照", key: ["产品编号"], order: "快照月份" });
});

test("a view shows its rows and who confirmed it, or why it cannot be used; only the ones a person named can be taken back", () => {
  const view = { name: "有效订单", sql_name: "有效订单__ab", sql: "SELECT 1", kind: "filter", rows: 144, state: "confirmed", confirmed_by: "王工", from: "你定义的", definition: { kind: "filter" } };
  assert.deepEqual([viewLine(view).rows, viewLine(view).state, viewLine(view).named, viewLine(view).usable], ["144 行", "已确认（王工）", true, true]);
  assert.equal(viewLine({ ...view, source: "订单" }).from, "视图，建在表 订单 上：你定义的");   // a view and a table can share a name
  assert.equal(viewLine(view).sql, 'CREATE VIEW "有效订单__ab" AS\nSELECT 1');
  const gone = viewLine({ ...view, rows: null, state: "unavailable", why: "「已取消」现在不是已确认的含义" });
  assert.deepEqual([gone.rows, gone.state, gone.usable], ["", "不可用：「已取消」现在不是已确认的含义", false]);
  assert.equal(viewLine({ ...view, kind: "labels", definition: null }).named, false);
});
