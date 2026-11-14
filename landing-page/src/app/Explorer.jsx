import React, { useState } from "react";
import { ChartResult, Standing } from "./ChartView.jsx";
import { exploreChart, exploreTable, getExploreMeta } from "./api.js";
import { CHART_KINDS, OPS, chartMissing, chartSpec, emptyFilter, fnOptions, opsFor, pivotQuery, queryFromParam, queryOf, queryToParam } from "./explorerModel.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { codeCell } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { useSettled } from "./useSettled.js";

function FilterRow({ filter, fields, onChange, onRemove }) {
  const field = fields.find((f) => f.key === filter.field);
  const ops = opsFor(field);
  const pick = field?.options && (filter.op === "eq" || filter.op === "ne");
  return (
    <div className="inline wide filter-row">
      <Select label="字段" value={filter.field} onChange={(v) => onChange({ field: v, op: "eq", value: "" })}>
        {fields.map((f) => <option key={f.key} value={f.key}>{f.name}{f.derived ? "（派生）" : ""}</option>)}
      </Select>
      <Select label="比较" value={filter.op} onChange={(v) => onChange({ ...filter, op: v })}>
        {ops.map((o) => <option key={o} value={o}>{OPS[o]}</option>)}
      </Select>
      {filter.op !== "empty" && filter.op !== "filled" && (pick ? (
        <Select label="取值" value={filter.value} onChange={(v) => onChange({ ...filter, value: v })}>
          <option value="">选一个</option>
          {field.options.map((o) => <option key={o.value} value={o.value}>{o.label ? `${o.value} ${o.label}` : o.value}</option>)}
        </Select>
      ) : <input type="text" aria-label="取值" value={filter.value} onChange={(e) => onChange({ ...filter, value: e.target.value })} />)}
      <button className="plain" onClick={onRemove}>去掉</button>
    </div>
  );
}

function ChartControls({ chart, setChart, fields, aggregations }) {
  const numeric = fields.filter((f) => f.numeric);
  const needsNumber = chart.kind === "histogram" || chart.kind === "table";
  const measure = fields.find((f) => f.key === chart.measure);
  const fns = fnOptions(measure, aggregations);
  const set = (patch) => setChart({ ...chart, ...patch });
  const choose = (kind) => set({ kind, group: kind === "histogram" || kind === "number" ? "" : chart.group, measure: kind === "histogram" || kind === "table" ? (numeric.find((f) => f.key === chart.measure)?.key ?? numeric[0]?.key ?? "") : chart.measure, fn: kind === "pie" && !["count", "sum"].includes(chart.fn) ? "count" : chart.fn });
  return (
    <div className="chart-controls">
      <div className="seg" role="group" aria-label="图的种类">
        {CHART_KINDS.map(([k, label]) => <button key={k} className={chart.kind === k ? "on" : ""} aria-pressed={chart.kind === k} onClick={() => choose(k)}>{label}</button>)}
      </div>
      {(chart.kind === "bar" || chart.kind === "pie" || chart.kind === "table") && (
        <label className="field"><span className="caption">按哪一列分组</span>
          <Select label="分组" value={chart.group} onChange={(v) => set({ group: v })}>
            <option value="">{chart.kind === "table" ? "不分组" : "选一列"}</option>
            {fields.map((f) => <option key={f.key} value={f.key}>{f.name}{f.derived ? "（派生）" : ""}</option>)}
          </Select>
        </label>
      )}
      <label className="field"><span className="caption">量哪一列</span>
        <Select label="度量" value={chart.measure} onChange={(v) => set({ measure: v, fn: fnOptions(fields.find((f) => f.key === v), aggregations).includes(chart.fn) ? chart.fn : "count" })}>
          {!needsNumber && <option value="">行数</option>}
          {(needsNumber ? numeric : fields).map((f) => <option key={f.key} value={f.key}>{f.name}{f.derived ? "（派生）" : ""}</option>)}
        </Select>
      </label>
      {(chart.kind === "number" || chart.kind === "bar" || chart.kind === "pie") && (
        <label className="field"><span className="caption">怎么统计</span>
          <Select label="统计方式" value={chart.fn} onChange={(v) => set({ fn: v })}>
            {fns.filter((fn) => chart.kind !== "pie" || fn === "count" || fn === "sum").map((fn) => <option key={fn} value={fn}>{aggregations[fn]}</option>)}
          </Select>
        </label>
      )}
      {chart.kind === "histogram" && (
        <label className="field"><span className="caption">分几段</span>
          <input type="text" inputMode="numeric" aria-label="分段数" value={chart.bins} onChange={(e) => set({ bins: Number(e.target.value.replace(/\D/g, "")) || "" })} />
        </label>
      )}
    </div>
  );
}

function TableView({ id, result, page, setPage }) {
  return (
    <>
      <p className="muted small" style={{ marginBottom: 8 }}>
        来自 {result.dataset} 第 {result.dataset_version} 版，{result.rows_limited ? "你能看到的 " : "共 "}{result.total} 行，第 {result.total ? (result.page - 1) * result.limit + 1 : 0}–{Math.min(result.page * result.limit, result.total)} 行
      </p>
      <div className="table-wrap tall">
        <table>
          <thead>
            <tr>
              {result.columns.map((c) => <th key={c.column} title={c.says}>{c.derived ? <><a href={hrefFor({ page: "type", id, tab: "derived" })}>{c.name}</a> <span className={c.confirmed ? "small" : "muted small"}>{c.confirmed ? "派生" : "派生，未确认"}</span></> : c.name}</th>)}
              <th />
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, r) => (
              <tr key={result.numbers[r]}>
                {row.map((v, i) => {
                  const e = result.enums[result.columns[i].column];
                  if (!e) return <td key={i} className="cell" title={v ?? undefined}>{v ?? <span className="faint">—</span>}</td>;
                  const cell = codeCell(v, e);
                  return <td key={i}>{cell.value}{cell.note && <span className="muted small"> {cell.note}</span>}</td>;
                })}
                <td className="keep"><a href={hrefFor({ page: "object", id, n: result.numbers[r] })}>打开</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.pages > 1 && (
        <nav className="pager" aria-label="对象分页">
          {result.page > 1 ? <button className="plain" onClick={() => setPage(result.page - 1)}>上一页</button> : <span className="faint">上一页</span>}
          <span>{result.page} / {result.pages}</span>
          {result.page < result.pages ? <button className="plain" onClick={() => setPage(result.page + 1)}>下一页</button> : <span className="faint">下一页</span>}
        </nav>
      )}
    </>
  );
}

/** The objects tab: the instances with filters and views, a chart of them, and the way across to the objects they link to. */
export function Explorer({ id, route }) {
  const first = queryFromParam(route.q);
  const [meta] = useLoad(() => getExploreMeta(id), [id]);
  const [view, setView] = useState(first?.view ?? "");
  const [filters, setFilters] = useState(first?.filters ?? []);
  const [pivot, setPivot] = useState(first?.pivot ?? null);
  const [mode, setMode] = useState("table");
  const [page, setPage] = useState(route.pageNo ?? 1);
  const [chart, setChart] = useState({ kind: "bar", group: "", measure: "", fn: "count", bins: 10 });
  const m = meta.data;
  const query = queryOf({ type: id, view, filters, pivot });
  const missing = chartMissing(chart);
  const table = useSettled(() => exploreTable(query, page), JSON.stringify([query, page, mode === "table"]));
  const drawn = useSettled(() => (mode === "chart" && !missing ? exploreChart(query, chartSpec(chart)) : Promise.resolve(null)), JSON.stringify([query, chart, mode, missing]));
  if (meta.status === "error") return <p className="error">{meta.error}</p>;
  if (!m) return <p className="muted">加载中</p>;
  const via = pivot && m.relations.find((r) => r.id === pivot.relation && r.other === pivot.source.type);
  const change = (patch) => {
    setPage(1);
    patch();
  };
  const result = mode === "table" ? table : drawn;
  return (
    <>
      <div className="explore-bar">
        <div className="seg" role="group" aria-label="看法">
          <button className={mode === "table" ? "on" : ""} aria-pressed={mode === "table"} onClick={() => setMode("table")}>表格</button>
          <button className={mode === "chart" ? "on" : ""} aria-pressed={mode === "chart"} onClick={() => setMode("chart")}>图表</button>
        </div>
        <Select label="视图" value={view} onChange={(v) => change(() => setView(v))}>
          <option value="">全部行</option>
          {m.views.map((v) => <option key={v.id} value={v.id}>{v.name}{v.state === "confirmed" ? "" : "（未确认）"}</option>)}
        </Select>
        <button className="secondary" disabled={filters.length >= 8} onClick={() => change(() => setFilters([...filters, emptyFilter(m.fields)]))}>加条件</button>
      </div>
      {pivot && (
        <p className="pivot-note">
          这是{via ? `经过「${via.name}」与「${via.other_name}」` : ""}关联的{m.type.name}。
          <button className="plain" onClick={() => change(() => setPivot(null))}>看全部{m.type.name}</button>
        </p>
      )}
      {filters.map((f, i) => (
        <FilterRow key={i} filter={f} fields={m.fields} onChange={(next) => change(() => setFilters(filters.map((x, j) => (j === i ? next : x))))} onRemove={() => change(() => setFilters(filters.filter((_, j) => j !== i)))} />
      ))}
      {mode === "chart" && <ChartControls chart={chart} setChart={setChart} fields={m.fields} aggregations={m.aggregations} />}
      {mode === "chart" && missing && <p className="muted">{missing}</p>}
      {result.status === "error" && <p className="error">{result.error}</p>}
      {result.data && mode === "table" && (
        <>
          <Standing standing={result.data.standing} />
          <TableView id={id} result={result.data} page={page} setPage={setPage} />
        </>
      )}
      {result.data && mode === "chart" && !missing && <ChartResult result={result.data} />}
      {!result.data && result.status !== "error" && !(mode === "chart" && missing) && <p className="muted">加载中</p>}
      {m.relations.length > 0 && !pivot && (   // a pivot goes across once: from a set that is already linked, look at all of it first
        <p className="goto">
          转到关联的：
          {m.relations.map((r) => (
            <a key={`${r.id}-${r.side}`} href={hrefFor({ page: "type", id: r.other, tab: "objects", pageNo: 1, q: queryToParam(pivotQuery(query, r)) })}>{r.other_name}（{r.name}）{r.confirmed ? "" : "，关系未确认"}</a>
          ))}
        </p>
      )}
    </>
  );
}
