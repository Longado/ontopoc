import React from "react";
import { GROUP_ORDERS, GROUP_TOPS, NOT_OFFICIAL, barRows, formatNumber, greyText, histogramBars, leftOutLines, pieSlices } from "./explorerModel.js";
import { useT } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { codeCell } from "./typeModel.js";

const short = (text, n = 16) => (text.length > n ? `${text.slice(0, n)}…` : text);
// one accent in five steps (a pie reads from one hue, no rainbow); grey is the muted ink in the same steps
const SLICE_OPACITY = [1, 0.78, 0.56, 0.38, 0.22];
const sliceFill = (i, grey) => ({ fill: grey ? "var(--muted)" : "var(--accent)", fillOpacity: SLICE_OPACITY[i % SLICE_OPACITY.length] });

/** How many groups a bar, a pie or a statistics table keeps and in which order: two choices next to the group's own. */
export function GroupShape({ top, order, onChange }) {
  const t = useT();
  return (
    <>
      <label className="field"><span className="caption">{t("boards.chart.show")}</span>
        <Select label={t("boards.chart.showTop")} value={top ?? ""} onChange={(v) => onChange({ top: v })}>
          {GROUP_TOPS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </Select>
      </label>
      <label className="field"><span className="caption">{t("boards.chart.sort")}</span>
        <Select label={t("boards.chart.sort")} value={order ?? ""} onChange={(v) => onChange({ order: v })}>
          {GROUP_ORDERS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </Select>
      </label>
    </>
  );
}

/** The columns a group can be taken from: the type's own, its derived ones, and the properties of the type at the one end of a confirmed many-to-one relation. */
export function GroupColumns({ fields, reach, current = "" }) {
  const t = useT();
  const known = fields.some((f) => f.key === current) || (reach ?? []).some((r) => r.key === current);
  return (
    <>
      {fields.map((f) => <option key={f.key} value={f.key}>{f.name}{f.derived ? t("boards.chart.derived") : ""}</option>)}
      {(reach ?? []).map((r) => <option key={r.key} value={r.key}>{t("boards.chart.via", { name: r.name, relation: r.relation_name })}</option>)}
      {current && !known && <option value={current}>{current.startsWith("via:") ? t("boards.chart.viaUnconfirmed") : current}{t("boards.chart.unavailable")}</option>}
    </>
  );
}

/** Said in words beside a grey result, so a forwarded screenshot is not read as an official number; nothing when it stands on confirmed definitions. */
export function NotOfficial({ standing }) {
  return standing && !standing.confirmed ? <p className="not-official">{NOT_OFFICIAL}</p> : null;
}

/** What a result stands on, one line for each definition (the caliber), and, when any is not confirmed, why the result is grey. */
export function Standing({ standing }) {
  const t = useT();
  if (!standing) return null;
  const why = greyText(standing);
  return (
    <div className="standing">
      {standing.lines.length > 0 && (
        <ul className="caliber">
          {standing.lines.map((l) => <li key={l.id} className={l.confirmed ? "" : "grey"}>{l.line}</li>)}
        </ul>
      )}
      {why && <p className="grey-why">{t("boards.chart.grey", { why })}</p>}
    </div>
  );
}

function Bars({ groups, grey }) {
  const t = useT();
  const rows = barRows(groups);
  const labelWidth = 150;
  const barWidth = 250;
  const row = 30;
  const top = 4;
  const height = rows.length * row + top + 22;
  const biggest = Math.max(0, ...rows.map((r) => Math.abs(r.value)));
  const ticks = biggest ? [0, 0.5, 1] : [0];
  const axisY = rows.length * row + top;
  return (
    <svg className="chart-svg" viewBox={`0 0 ${labelWidth + barWidth + 70} ${height}`} role="img" aria-label={t("boards.chart.bar")}>
      {ticks.map((f) => (
        <g key={f}>
          <line className="grid" x1={labelWidth + f * barWidth} x2={labelWidth + f * barWidth} y1={top} y2={axisY} />
          <text x={labelWidth + f * barWidth} y={axisY + 15} textAnchor={f === 1 ? "end" : f === 0 ? "start" : "middle"} className="axis">{formatNumber(biggest * f)}</text>
        </g>
      ))}
      <line className="axis-line" x1={labelWidth} x2={labelWidth} y1={top} y2={axisY} />
      {rows.map((r, i) => (
        <g key={i} transform={`translate(0 ${i * row + top})`}>
          <text x={labelWidth - 10} y="19" textAnchor="end"><title>{r.label}</title>{short(r.label)}</text>
          <rect x={labelWidth} y="6" rx="3" width={Math.max(r.fraction * barWidth, r.value ? 2 : 0)} height="18" className={grey ? "fill-grey" : "fill-accent"} />
          <text x={labelWidth + r.fraction * barWidth + 8} y="19" className="value">{formatNumber(r.value)}</text>
        </g>
      ))}
    </svg>
  );
}

function Pie({ groups, grey }) {
  const t = useT();
  const slices = pieSlices(groups);
  return (
    <div className="pie">
      <svg viewBox="0 0 160 160" width="160" height="160" role="img" aria-label={t("boards.chart.pie")}>
        {slices.map((s, i) => s.path && <path key={i} d={s.path} {...sliceFill(i, grey)} className="slice" strokeWidth="1.5"><title>{`${s.label}: ${formatNumber(s.value)}`}</title></path>)}
      </svg>
      <ul className="legend">
        {slices.map((s, i) => (
          <li key={i}>
            <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><rect width="10" height="10" rx="2" {...sliceFill(i, grey)} /></svg>
            <span>{s.label}</span>
            <span className="num">{formatNumber(s.value)}</span>
            <span className="muted num">{(s.share * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Histogram({ result, grey }) {
  const t = useT();
  const bars = histogramBars(result.bins);
  const left = 34;
  const width = 390;
  const gap = 2;
  const plotTop = 8;
  const plotHeight = 140;
  const base = plotTop + plotHeight;
  const each = bars.length ? width / bars.length : width;
  const peak = Math.max(0, ...result.bins.map((b) => b.count));
  return (
    <>
      <svg className="chart-svg" viewBox="0 0 440 190" role="img" aria-label={t("boards.chart.histogram")}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line className="grid" x1={left} x2={left + width} y1={base - f * plotHeight} y2={base - f * plotHeight} />
            <text x={left - 6} y={base - f * plotHeight + 4} textAnchor="end" className="axis">{formatNumber(Math.round(peak * f))}</text>
          </g>
        ))}
        {bars.map((b, i) => (
          <rect key={i} x={left + i * each + gap / 2} y={base - b.fraction * plotHeight} rx="2" width={Math.max(each - gap, 1)} height={b.fraction * plotHeight} className={grey ? "fill-grey" : "fill-accent"}>
            <title>{t("boards.chart.bin", { from: formatNumber(b.from), to: formatNumber(b.to), count: b.count })}</title>
          </rect>
        ))}
        <line className="axis-line" x1={left} x2={left + width} y1={base} y2={base} />
        {bars.length > 0 && <text x={left} y={base + 16} className="axis">{formatNumber(bars[0].from)}</text>}
        {bars.length > 0 && <text x={left + width} y={base + 16} textAnchor="end" className="axis">{formatNumber(bars[bars.length - 1].to)}</text>}
      </svg>
      <p className="muted small">{t("boards.chart.values", { count: result.values })}{result.missing ? t("boards.chart.missing", { count: result.missing }) : t("boards.chart.noMissing")}</p>
    </>
  );
}

function StatTable({ result }) {
  const t = useT();
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>{result.group ?? ""}</th><th className="num">{t("boards.chart.rows")}</th>{result.columns.map((c) => <th key={c.fn} className="num">{c.name}</th>)}</tr></thead>
        <tbody>
          {result.table.map((r, i) => <tr key={i}><td>{r.label}</td><td className="num">{r.rows}</td>{r.values.map((v, j) => <td key={j} className="num">{formatNumber(v)}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

/** The first rows of a type as a board's table; each row opens its own page. */
function Rows({ result }) {
  const t = useT();
  const type = result.query.type;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{result.columns.map((c) => <th key={c.column}>{c.name}</th>)}</tr></thead>
        <tbody>
          {result.rows.map((row, r) => (
            <tr key={r}>
              {row.map((v, i) => {
                const e = result.enums[result.columns[i].column];
                const cell = e ? codeCell(v, e) : { value: v ?? "", note: "" };
                return <td key={i}>{i === 0 ? <a href={hrefFor({ page: "object", id: type, n: result.numbers[r] })}>{v ?? "—"}</a> : <>{cell.value}{cell.note && <span className="muted small"> {cell.note}</span>}</>}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small table-note">{t("boards.chart.rowsShown", { total: result.total, shown: result.rows.length })}</p>
    </div>
  );
}

/** One chart result in the shape its kind says, in colour when everything it stands on is confirmed and in grey, with the reason, when not. */
export function ChartResult({ result, withStanding = true }) {
  const t = useT();
  const grey = !result.standing.confirmed;
  const kind = result.chart?.kind ?? "rows";
  return (
    <div className={`chart${grey ? " is-grey" : ""}`}>
      <NotOfficial standing={result.standing} />
      {kind === "number" && (
        <p className="metric">{formatNumber(result.value)}{result.rows_limited && <span className="muted small"> {t("boards.chart.yourRows")}</span>}</p>
      )}
      {kind === "bar" && (result.groups.length ? <Bars groups={result.groups} grey={grey} /> : <p className="muted">{t("boards.chart.noRows")}</p>)}
      {kind === "pie" && (result.groups.length ? <Pie groups={result.groups} grey={grey} /> : <p className="muted">{t("boards.chart.noRows")}</p>)}
      {kind === "histogram" && (result.bins.length ? <Histogram result={result} grey={grey} /> : <p className="muted">{t("boards.chart.noNumbers")}</p>)}
      {kind === "table" && <StatTable result={result} />}
      {kind === "rows" && <Rows result={result} />}
      {(kind === "bar" || kind === "pie" || kind === "table") && leftOutLines(result).map((line) => <p key={line} className="muted small">{line}</p>)}
      {kind !== "rows" && <p className="muted small">{t("boards.chart.computed", { count: result.rows })}</p>}
      {withStanding && <Standing standing={result.standing} />}
    </div>
  );
}
