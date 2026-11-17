import assert from "node:assert/strict";
import test from "node:test";
import { filterDatasets, originLink, readerLinks, sortDatasets } from "./datasetModel.js";

const list = [
  { name: "订单", rows: 160, columns: 8, version: 2, updated_at: "2026-11-15T10:00:00", origin: "upload" },
  { name: "客户", rows: 30, columns: 5, version: 1, updated_at: "2026-11-16T09:00:00", origin: "source:erp/public.customer" },
  { name: "工单关联订单", rows: 90, columns: 4, version: 3, updated_at: "2026-11-14T09:00:00", origin: "pipeline:工单关联订单@run3" },
];

test("search matches the name or the source, ignoring case", () => {
  assert.deepEqual(filterDatasets(list, "客").map((d) => d.name), ["客户"]);
  assert.deepEqual(filterDatasets(list, "ERP").map((d) => d.name), ["客户"]);
  assert.equal(filterDatasets(list, "  ").length, 3);
  assert.equal(filterDatasets(list, "没有").length, 0);
});

test("sorting by rows or updated time, both ways, without changing the list", () => {
  assert.deepEqual(sortDatasets(list, "rows", "desc").map((d) => d.rows), [160, 90, 30]);
  assert.deepEqual(sortDatasets(list, "updated_at", "desc").map((d) => d.name), ["客户", "订单", "工单关联订单"]);
  assert.deepEqual(sortDatasets(list, "name", "asc").map((d) => d.name), [...list.map((d) => d.name)].sort((a, b) => a.localeCompare(b, "zh")));
  assert.equal(list[0].name, "订单");
});

test("an origin becomes a label and, where there is a page, a link", () => {
  assert.deepEqual(originLink("upload"), { kind: "upload", label: "上传", href: null });
  assert.deepEqual(originLink("source:erp/public.customer"), { kind: "source", label: "数据源 erp（表 public.customer）", href: "#/sources/erp" });
  assert.deepEqual(originLink("pipeline:工单关联订单@run3"), { kind: "pipeline", label: "管道 工单关联订单（第 3 次运行）", href: "#/pipelines/%E5%B7%A5%E5%8D%95%E5%85%B3%E8%81%94%E8%AE%A2%E5%8D%95" });
  assert.deepEqual(originLink("pipeline"), { kind: "pipeline", label: "管道（你没有权限看）", href: null });
  assert.equal(originLink("something").kind, "other");
});

test("readers link to their page: pipelines by name, types by the id found from their name", () => {
  const links = readerLinks([{ kind: "管道", name: "p1" }, { kind: "对象类型", name: "订单" }, { kind: "对象类型", name: "未知" }], { 订单: "order" });
  assert.deepEqual(links, [
    { kind: "管道", name: "p1", href: "#/pipelines/p1" },
    { kind: "对象类型", name: "订单", href: "#/types/order/props" },
    { kind: "对象类型", name: "未知", href: null },
  ]);
});
