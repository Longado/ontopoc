import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { buildSync } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { parseRoute } from "./routeModel.js";
import { queryFromParam, queryOf } from "./explorerModel.js";

// Render the real JSX with the same React instance as the server renderer.
const built = buildSync({
  entryPoints: [fileURLToPath(new URL("./ChartView.jsx", import.meta.url))],
  platform: "node", format: "cjs", bundle: true, write: false, external: ["react"],
  define: { "import.meta.env.DEV": "false" },
});
const component = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), component, component.exports);
const { ChartResult } = component.exports;
const query = {
  type: "case", view: "reviewed", search: "inventory", rows: Array.from({ length: 18 }, (_, i) => i + 1),
  filters: [{ field: "industry", op: "eq", value: "Food & drink" }],
  pivot: { source: { type: "source", rows: [4, 7] }, relation: "documents", side: "from" },
};
const columns = [{ column: "id", name: "ID", key: true }, { column: "name", name: "Name" }, { column: "source", name: "Source" }];
const row = ["case-10", "Observed case", "https://example.com/report.pdf#page=2\nhttps://example.com/video?t=60"];

function links(total, rows) {
  const result = { query, chart: { kind: "rows" }, columns, enums: {}, total, rows, numbers: rows.map((_, n) => n + 1), standing: { confirmed: true } };
  const html = renderToStaticMarkup(React.createElement(ChartResult, { result, withStanding: false }));
  return [...html.matchAll(/<a\b[^>]* href="([^"]+)"/g)].map(([, href]) => href.replaceAll("&amp;", "&"));
}

test("a truncated board table links to the full query including the selected rows, while each citation keeps its own link", () => {
  const hrefs = links(13, Array(10).fill(row));
  const collection = hrefs.map(parseRoute).find((route) => route.page === "type" && route.tab === "objects");
  assert.ok(collection, "open all matching objects from a truncated board table");
  const first = queryFromParam(collection.q);
  assert.deepEqual(first, query);
  assert.deepEqual(queryOf(first), query);
  assert.ok(hrefs.includes("https://example.com/report.pdf#page=2"));
  assert.ok(hrefs.includes("https://example.com/video?t=60"));
});

test("a complete or empty preview has no extra collection link", () => {
  for (const [total, rows] of [[1, [row]], [0, []]]) {
    const routes = links(total, rows).map(parseRoute);
    assert.equal(routes.some((route) => route.page === "type" && route.tab === "objects"), false);
  }
});
