import React, { useEffect, useState } from "react";
import { SourceValue } from "./SourceValue.jsx";
import { ChartResult, GroupColumns, GroupShape, NotOfficial, Standing } from "./ChartView.jsx";
import { exploreChart, exploreTable, getExploreMeta } from "./api.js";
import { CHART_KINDS, OPS, chartMissing, chartSpec, emptyFilter, fnOptions, opsFor, pivotQuery, queryFromParam, queryOf, queryToParam, searchWord } from "./explorerModel.js";
import { t } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { codeCell, outsideNote } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { useSettled } from "./useSettled.js";

function FilterRow({ filter, fields, onChange, onRemove }) {
  const field = fields.find((f) => f.key === filter.field);
  const ops = opsFor(field);
  const pick = field?.options && (filter.op === "eq" || filter.op === "ne");
  return (
    <div className="inline wide filter-row">
      <Select label={t("objects.filter.field")} value={filter.field} onChange={(v) => onChange({ field: v, op: "eq", value: "" })}>
        {fields.map((f) => <option key={f.key} value={f.key}>{f.name}{f.derived ? t("objects.filter.derived") : ""}</option>)}
      </Select>
      <Select label={t("objects.filter.compare")} value={filter.op} onChange={(v) => onChange({ ...filter, op: v })}>
        {ops.map((o) => <option key={o} value={o}>{OPS[o]}</option>)}
      </Select>
      {filter.op !== "empty" && filter.op !== "filled" && (pick ? (
        <Select label={t("objects.filter.value")} value={filter.value} onChange={(v) => onChange({ ...filter, value: v })}>
          <option value="">{t("objects.filter.pick")}</option>
          {field.options.map((o) => <option key={o.value} value={o.value}>{o.label ? `${o.value} ${o.label}` : o.value}</option>)}
        </Select>
      ) : <input type="text" aria-label={t("objects.filter.value")} value={filter.value} onChange={(e) => onChange({ ...filter, value: e.target.value })} />)}
      <button className="plain" onClick={onRemove}>{t("objects.filter.remove")}</button>
    </div>
  );
}

function ChartControls({ chart, setChart, fields, reach, aggregations }) {
  const numeric = fields.filter((f) => f.numeric);
  const needsNumber = chart.kind === "histogram" || chart.kind === "table";
  const measure = fields.find((f) => f.key === chart.measure);
  const fns = fnOptions(measure, aggregations);
  const set = (patch) => setChart({ ...chart, ...patch });
  const choose = (kind) => set({ kind, group: kind === "histogram" || kind === "number" ? "" : chart.group, measure: kind === "histogram" || kind === "table" ? (numeric.find((f) => f.key === chart.measure)?.key ?? numeric[0]?.key ?? "") : chart.measure, fn: kind === "pie" && !["count", "sum"].includes(chart.fn) ? "count" : chart.fn });
  return (
    <div className="chart-controls">
      <div className="seg" role="group" aria-label={t("objects.chartCtl.kind")}>
        {CHART_KINDS.map(([k, label]) => <button key={k} className={chart.kind === k ? "on" : ""} aria-pressed={chart.kind === k} onClick={() => choose(k)}>{label}</button>)}
      </div>
      {(chart.kind === "bar" || chart.kind === "pie" || chart.kind === "table") && (
        <label className="field"><span className="caption">{t("objects.chartCtl.groupBy")}</span>
          <Select label={t("objects.chartCtl.group")} value={chart.group} onChange={(v) => set({ group: v })}>
            <option value="">{chart.kind === "table" ? t("objects.chartCtl.noGroup") : t("objects.chartCtl.pickColumn")}</option>
            <GroupColumns fields={fields} reach={reach} current={chart.group} />
          </Select>
        </label>
      )}
      {(chart.kind === "bar" || chart.kind === "pie" || chart.kind === "table") && chart.group && <GroupShape top={chart.top} order={chart.order} onChange={set} />}
      <label className="field"><span className="caption">{t("objects.chartCtl.measureBy")}</span>
        <Select label={t("objects.chartCtl.measure")} value={chart.measure} onChange={(v) => set({ measure: v, fn: fnOptions(fields.find((f) => f.key === v), aggregations).includes(chart.fn) ? chart.fn : "count" })}>
          {!needsNumber && <option value="">{t("objects.chartCtl.rows")}</option>}
          {(needsNumber ? numeric : fields).map((f) => <option key={f.key} value={f.key}>{f.name}{f.derived ? t("objects.filter.derived") : ""}</option>)}
        </Select>
      </label>
      {(chart.kind === "number" || chart.kind === "bar" || chart.kind === "pie") && (
        <label className="field"><span className="caption">{t("objects.chartCtl.howTo")}</span>
          <Select label={t("objects.chartCtl.fn")} value={chart.fn} onChange={(v) => set({ fn: v })}>
            {fns.filter((fn) => chart.kind !== "pie" || fn === "count" || fn === "sum").map((fn) => <option key={fn} value={fn}>{aggregations[fn]}</option>)}
          </Select>
        </label>
      )}
      {chart.kind === "histogram" && (
        <label className="field"><span className="caption">{t("objects.chartCtl.bins")}</span>
          <input type="text" inputMode="numeric" aria-label={t("objects.chartCtl.binsAria")} value={chart.bins} onChange={(e) => set({ bins: Number(e.target.value.replace(/\D/g, "")) || "" })} />
        </label>
      )}
    </div>
  );
}

function TableView({ id, result, page, setPage }) {
  return (
    <>
      <p className="muted small" style={{ marginBottom: 8 }}>
        {t(result.rows_limited ? "objects.table.fromLimited" : "objects.table.from", { dataset: result.dataset, version: result.dataset_version, total: result.total, count: result.total, from: result.total ? (result.page - 1) * result.limit + 1 : 0, to: Math.min(result.page * result.limit, result.total) })}
      </p>
      {result.total === 0 && <p className="muted" style={{ marginBottom: 8 }}>{t("objects.table.noMatch")}</p>}
      <div className="table-wrap tall">
        <table>
          <thead>
            <tr>
              {result.columns.map((c) => <th key={c.column} title={c.says}>{c.derived ? <><a href={hrefFor({ page: "type", id, tab: "derived" })}>{c.name}</a> <span className={c.confirmed ? "small" : "muted small"}>{c.confirmed ? t("objects.table.derived") : t("objects.table.derivedUnconfirmed")}</span></> : c.name}</th>)}
              <th />
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, r) => (
              <tr key={result.numbers[r]} className="click" onClick={(e) => { if (!e.target.closest("a,button")) window.location.assign(hrefFor({ page: "object", id, n: result.numbers[r] })); }}>
                {row.map((v, i) => {
                  const e = result.enums[result.columns[i].column];
                  if (!e) return <td key={i} className="cell" title={v ?? (result.outside?.[r]?.includes(i) ? outsideNote() : undefined)}>{v == null ? <span className="faint">—</span> : <SourceValue value={v} />}</td>;
                  const cell = codeCell(v, e);
                  return <td key={i}><SourceValue value={cell.value} />{cell.note && <span className="muted small"> {cell.note}</span>}</td>;
                })}
                <td className="keep"><a href={hrefFor({ page: "object", id, n: result.numbers[r] })}>{t("objects.table.open")}</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.outside?.some((cells) => cells.length > 0) && <p className="muted small">{t("objects.table.outsideKey", { note: outsideNote() })}</p>}
      {result.pages > 1 && (
        <nav className="pager" aria-label={t("objects.table.pagerAria")}>
          {result.page > 1 ? <button className="plain" onClick={() => setPage(result.page - 1)}>{t("objects.table.prev")}</button> : <span className="faint">{t("objects.table.prev")}</span>}
          <span>{result.page} / {result.pages}</span>
          {result.page < result.pages ? <button className="plain" onClick={() => setPage(result.page + 1)}>{t("objects.table.next")}</button> : <span className="faint">{t("objects.table.next")}</span>}
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
  const [typed, setTyped] = useState(searchWord(first));   // what is in the box; `search` follows it a moment after the last key
  const [search, setSearch] = useState(searchWord(first));
  const [mode, setMode] = useState("table");
  const [page, setPage] = useState(route.pageNo ?? 1);
  const [chart, setChart] = useState({ kind: "bar", group: "", measure: "", fn: "count", bins: 10, top: "", order: "" });
  const m = meta.data;
  useEffect(() => {
    if (typed === search) return undefined;
    const wait = setTimeout(() => {
      setPage(1);
      setSearch(typed);
    }, 300);
    return () => clearTimeout(wait);
  }, [typed, search]);
  const query = queryOf({ type: id, view, filters, pivot, search });
  const missing = chartMissing(chart);
  const table = useSettled(() => exploreTable(query, page), JSON.stringify([query, page, mode === "table"]));
  const drawn = useSettled(() => (mode === "chart" && !missing ? exploreChart(query, chartSpec(chart)) : Promise.resolve(null)), JSON.stringify([query, chart, mode, missing]));
  if (meta.status === "error") return <p className="error">{meta.error}</p>;
  if (!m) return <p className="muted">{t("common.loading")}</p>;
  const via = pivot && m.relations.find((r) => r.id === pivot.relation && r.other === pivot.source.type);
  const change = (patch) => {
    setPage(1);
    patch();
  };
  const result = mode === "table" ? table : drawn;
  return (
    <>
      <div className="explore-bar">
        <div className="seg" role="group" aria-label={t("objects.bar.view")}>
          <button className={mode === "table" ? "on" : ""} aria-pressed={mode === "table"} onClick={() => setMode("table")}>{t("objects.bar.table")}</button>
          <button className={mode === "chart" ? "on" : ""} aria-pressed={mode === "chart"} onClick={() => setMode("chart")}>{t("objects.bar.chart")}</button>
        </div>
        <input type="search" className="explore-search" aria-label={t("objects.bar.searchAria")} placeholder={t("objects.bar.searchPlaceholder")} value={typed} maxLength={100} onChange={(e) => setTyped(e.target.value)} />
        <Select label={t("objects.bar.viewLabel")} value={view} onChange={(v) => change(() => setView(v))}>
          <option value="">{t("objects.bar.allRows")}</option>
          {m.views.map((v) => <option key={v.id} value={v.id}>{v.name}{v.state === "confirmed" ? "" : t("objects.bar.unconfirmed")}</option>)}
        </Select>
        <button className="secondary" disabled={filters.length >= 8} onClick={() => change(() => setFilters([...filters, emptyFilter(m.fields)]))}>{t("objects.bar.addFilter")}</button>
      </div>
      {pivot && (
        <p className="pivot-note">
          {t("objects.pivot.note", { type: m.type.name, via: via ? t("objects.pivot.via", { name: via.name, other: via.other_name }) : "" })}{" "}
          <button className="plain" onClick={() => change(() => setPivot(null))}>{t("objects.pivot.all", { type: m.type.name })}</button>
        </p>
      )}
      {filters.map((f, i) => (
        <FilterRow key={i} filter={f} fields={m.fields} onChange={(next) => change(() => setFilters(filters.map((x, j) => (j === i ? next : x))))} onRemove={() => change(() => setFilters(filters.filter((_, j) => j !== i)))} />
      ))}
      {mode === "chart" && <ChartControls chart={chart} setChart={setChart} fields={m.fields} reach={m.reach} aggregations={m.aggregations} />}
      {mode === "chart" && missing && <p className="muted">{missing}</p>}
      {result.status === "error" && <p className="error">{result.error}</p>}
      {result.data && mode === "table" && (
        <>
          <NotOfficial standing={result.data.standing} />
          <Standing standing={result.data.standing} />
          <TableView id={id} result={result.data} page={page} setPage={setPage} />
        </>
      )}
      {result.data && mode === "chart" && !missing && <ChartResult result={result.data} />}
      {!result.data && result.status !== "error" && !(mode === "chart" && missing) && <p className="muted">{t("common.loading")}</p>}
      {m.relations.length > 0 && !pivot && (   // a pivot goes across once: from a set that is already linked, look at all of it first
        <p className="goto">
          {t("objects.goto")}{" "}
          {m.relations.map((r) => (
            <a key={`${r.id}-${r.side}`} href={hrefFor({ page: "type", id: r.other, tab: "objects", pageNo: 1, q: queryToParam(pivotQuery(query, r)) })}>{t("objects.gotoLink", { other: r.other_name, name: r.name, unconfirmed: r.confirmed ? "" : t("objects.gotoUnconfirmed") })}</a>
          ))}
        </p>
      )}
    </>
  );
}
