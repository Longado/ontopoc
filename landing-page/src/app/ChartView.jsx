import React from "react";
import { barRows, formatNumber, greyText, histogramBars, pieSlices, sliceColor } from "./explorerModel.js";
import { hrefFor } from "./routeModel.js";
import { codeCell } from "./typeModel.js";

const short = (text, n = 10) => (text.length > n ? `${text.slice(0, n)}…` : text);

/** What a result stands on, one line for each definition (the caliber), and, when any is not confirmed, why the result is grey. */
export function Standing({ standing }) {
  if (!standing) return null;
  const why = greyText(standing);
  return (
    <div className="standing">
      {standing.lines.length > 0 && (
        <ul className="caliber">
          {standing.lines.map((l) => <li key={l.id} className={l.confirmed ? "" : "grey"}>{l.line}</li>)}
        </ul>
      )}
      {why && <p className="grey-why">灰色：{why}</p>}
    </div>
  );
}

function Bars({ groups, grey }) {
  const rows = barRows(groups);
  const labelWidth = 150;
  const barWidth = 220;
  const height = rows.length * 28 + 4;
  return (
    <svg className="chart-svg" viewBox={`0 0 440 ${height}`} role="img" aria-label="柱状图">
      {rows.map((r, i) => (
        <g key={i} transform={`translate(0 ${i * 28 + 2})`}>
          <text x={labelWidth - 8} y="16" textAnchor="end"><title>{r.label}</title>{short(r.label)}</text>
          <rect x={labelWidth} y="3" width={Math.max(r.fraction * barWidth, r.value ? 1 : 0)} height="18" className={grey ? "fill-grey" : "fill-accent"} />
          <text x={labelWidth + r.fraction * barWidth + 8} y="16" className="value">{formatNumber(r.value)}</text>
        </g>
      ))}
    </svg>
  );
}

function Pie({ groups, grey }) {
  const slices = pieSlices(groups);
  return (
    <div className="pie">
      <svg viewBox="0 0 160 160" width="160" height="160" role="img" aria-label="饼图">
        {slices.map((s, i) => s.path && <path key={i} d={s.path} fill={sliceColor(i, grey)} stroke="#fff" strokeWidth="1"><title>{`${s.label}：${formatNumber(s.value)}`}</title></path>)}
      </svg>
      <ul className="legend">
        {slices.map((s, i) => (
          <li key={i}>
            <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><rect width="10" height="10" fill={sliceColor(i, grey)} /></svg>
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
  const bars = histogramBars(result.bins);
  const width = 400;
  const gap = 2;
  const each = bars.length ? width / bars.length : width;
  return (
    <>
      <svg className="chart-svg" viewBox="0 0 440 190" role="img" aria-label="直方图">
        {bars.map((b, i) => (
          <rect key={i} x={20 + i * each + gap / 2} y={150 - b.fraction * 140} width={Math.max(each - gap, 1)} height={b.fraction * 140} className={grey ? "fill-grey" : "fill-accent"}>
            <title>{`${formatNumber(b.from)} 到 ${formatNumber(b.to)}：${b.count} 个`}</title>
          </rect>
        ))}
        {bars.length > 0 && <text x="20" y="172" className="axis">{formatNumber(bars[0].from)}</text>}
        {bars.length > 0 && <text x="420" y="172" textAnchor="end" className="axis">{formatNumber(bars[bars.length - 1].to)}</text>}
      </svg>
      <p className="muted small">{result.values} 个有值，{result.missing ? `${result.missing} 个没有值或读不成数字，没有画进去` : "没有缺值"}</p>
    </>
  );
}

function StatTable({ result }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>{result.group ?? ""}</th><th className="num">行数</th>{result.columns.map((c) => <th key={c.fn} className="num">{c.name}</th>)}</tr></thead>
        <tbody>
          {result.table.map((r, i) => <tr key={i}><td>{r.label}</td><td className="num">{r.rows}</td>{r.values.map((v, j) => <td key={j} className="num">{formatNumber(v)}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

/** The first rows of a type as a board's table; each row opens its own page. */
function Rows({ result }) {
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
      <p className="muted small">共 {result.total} 行，显示前 {result.rows.length} 行</p>
    </div>
  );
}

/** One chart result in the shape its kind says, in colour when everything it stands on is confirmed and in grey, with the reason, when not. */
export function ChartResult({ result, withStanding = true }) {
  const grey = !result.standing.confirmed;
  const kind = result.chart?.kind ?? "rows";
  return (
    <div className={`chart${grey ? " is-grey" : ""}`}>
      {kind === "number" && (
        <p className="metric">{formatNumber(result.value)}{result.rows_limited && <span className="muted small"> 你能看到的行</span>}</p>
      )}
      {kind === "bar" && (result.groups.length ? <Bars groups={result.groups} grey={grey} /> : <p className="muted">没有可画的行</p>)}
      {kind === "pie" && (result.groups.length ? <Pie groups={result.groups} grey={grey} /> : <p className="muted">没有可画的行</p>)}
      {kind === "histogram" && (result.bins.length ? <Histogram result={result} grey={grey} /> : <p className="muted">没有可画的数字</p>)}
      {kind === "table" && <StatTable result={result} />}
      {kind === "rows" && <Rows result={result} />}
      {(kind === "bar" || kind === "pie" || kind === "table") && result.groups_hidden > 0 && (
        <p className="muted small">还有 {result.groups_hidden} 组没有画出来{result.rows_hidden ? `（${result.rows_hidden} 行）` : ""}</p>
      )}
      {kind !== "rows" && <p className="muted small">算的是 {result.rows} 行</p>}
      {withStanding && <Standing standing={result.standing} />}
    </div>
  );
}
