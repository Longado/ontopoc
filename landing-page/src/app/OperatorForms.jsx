import React, { useState } from "react";
import { guessDateFormat, previewNode } from "./api.js";
import { ExpressionEditor } from "./ExpressionEditor.jsx";
import { typeLabel } from "./format.js";
import { AGG_LABEL, CAST_LABEL, CLEAN_LABEL, CMP_LABEL, UNMAPPED_LABEL, aggDefaultName } from "./pipelineModel.js";
import { Select } from "./Select.jsx";

const ORDERABLE = ["integer", "decimal", "date", "datetime", "month"];
const NO_VALUE = ["is_null", "not_null"];

function ColSelect({ cols, value, onChange, label, blank = "选一列", only }) {
  return (
    <Select label={label} value={value ?? ""} onChange={onChange}>
      <option value="">{blank}</option>
      {cols.filter((c) => !only || only(c)).map((c) => <option key={c.name} value={c.name}>{c.name}（{typeLabel(c.type)}）</option>)}
    </Select>
  );
}

function ColChecks({ cols, value, onChange, legend, only }) {
  const toggle = (name, on) => onChange(on ? [...value, name] : value.filter((n) => n !== name));
  return (
    <fieldset className="keys">
      <legend>{legend}</legend>
      {cols.filter((c) => !only || only(c)).map((c) => (
        <label key={c.name}><input type="checkbox" checked={value.includes(c.name)} onChange={(e) => toggle(c.name, e.target.checked)} />{c.name}</label>
      ))}
    </fieldset>
  );
}

const Row = ({ children }) => <div className="inline wide op-row">{children}</div>;

function FilterForm({ op, cols, onChange }) {
  const group = op.where.any ? "any" : "all";
  const rows = op.where[group] ?? [];
  const setRows = (next, g = group) => onChange({ ...op, where: { [g]: next } });
  const setRow = (i, row) => setRows(rows.map((r, k) => (k === i ? row : r)));
  return (
    <div className="op-form">
      <div className="inline">
        <span>留下</span>
        <Select label="条件之间的关系" value={group} onChange={(g) => setRows(rows, g)}>
          <option value="all">全部满足</option>
          <option value="any">任一满足</option>
        </Select>
        <span>这些条件的行</span>
      </div>
      {rows.map((row, i) => {
        if (row.all || row.any) return <Row key={i}><span className="muted">一组嵌套的条件，这里不能编辑</span><button className="plain" onClick={() => setRows(rows.filter((_, k) => k !== i))}>删除</button></Row>;
        const col = cols.find((c) => c.name === row.column);
        const byMeaning = row.meaning !== undefined;
        const meanings = col?.meanings ? Object.keys(col.meanings) : [];
        return (
          <Row key={i}>
            <ColSelect cols={cols} value={row.column} label="条件的列" onChange={(column) => setRow(i, { column, cmp: "eq", value: "" })} />
            <Select label="比较" value={row.cmp} onChange={(cmp) => setRow(i, { column: row.column, cmp, ...(byMeaning ? { meaning: row.meaning } : cmp === "in" ? { values: [] } : cmp === "between" ? { low: "", high: "" } : NO_VALUE.includes(cmp) ? {} : { value: "" }) })}>
              {Object.entries(CMP_LABEL).filter(([k]) => !byMeaning || ["eq", "ne"].includes(k)).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
            {byMeaning ? (
              <Select label="含义" value={row.meaning} onChange={(meaning) => setRow(i, { ...row, meaning })}>
                <option value="">选一个含义</option>
                {meanings.map((m) => <option key={m} value={m}>{m}</option>)}
              </Select>
            ) : row.cmp === "between" ? (
              <>
                <input type="text" aria-label="下限" value={row.low ?? ""} onChange={(e) => setRow(i, { ...row, low: e.target.value })} />
                <span>到</span>
                <input type="text" aria-label="上限" value={row.high ?? ""} onChange={(e) => setRow(i, { ...row, high: e.target.value })} />
              </>
            ) : row.cmp === "in" ? (
              <input type="text" aria-label="一组值，用逗号隔开" placeholder="用逗号隔开" value={(row.values ?? []).join(", ")}
                onChange={(e) => setRow(i, { ...row, values: e.target.value.split(/[,，]\s*/) })} onBlur={() => setRow(i, { ...row, values: (row.values ?? []).filter(Boolean) })} />
            ) : NO_VALUE.includes(row.cmp) ? null : (
              <input type="text" aria-label="值" value={row.value ?? ""} onChange={(e) => setRow(i, { ...row, value: e.target.value })} />
            )}
            {meanings.length > 0 && ["eq", "ne"].includes(row.cmp) && (
              <label className="check"><input type="checkbox" checked={byMeaning} onChange={(e) => setRow(i, e.target.checked ? { column: row.column, cmp: row.cmp, meaning: "" } : { column: row.column, cmp: row.cmp, value: "" })} />按含义选</label>
            )}
            <button className="plain" onClick={() => setRows(rows.filter((_, k) => k !== i))} disabled={rows.length === 1}>删除</button>
          </Row>
        );
      })}
      <button className="plain" onClick={() => setRows([...rows, { column: "", cmp: "eq", value: "" }])}>加一个条件</button>
      {cols.some((c) => c.code) && <p className="hint">代码列可以勾“按含义选”，用已确认的含义，不用记代码值。条件为假和条件为空的行分开数。</p>}
    </div>
  );
}

function FillNullForm({ op, cols, onChange, where }) {
  const kind = op.with?.column !== undefined ? "column" : op.with?.expression !== undefined ? "expression" : "constant";
  const setKind = (k) => onChange({ ...op, with: k === "constant" ? { constant: "" } : k === "column" ? { column: "" } : { expression: "" } });
  return (
    <div className="op-form">
      <ColChecks cols={cols} value={op.columns} onChange={(columns) => onChange({ ...op, columns })} legend="换哪几列的空值" />
      <div className="inline">
        <span>换成</span>
        <Select label="换成什么" value={kind} onChange={setKind}>
          <option value="constant">一个固定的值</option>
          <option value="column">另一列的值</option>
          <option value="expression">表达式的结果</option>
        </Select>
        {kind === "constant" && <input type="text" aria-label="固定的值" value={op.with.constant ?? ""} onChange={(e) => onChange({ ...op, with: { constant: e.target.value } })} />}
        {kind === "column" && <ColSelect cols={cols} value={op.with.column} label="另一列" onChange={(column) => onChange({ ...op, with: { column } })} />}
      </div>
      {kind === "expression" && <ExpressionEditor cols={cols} where={where} value={op.with.expression ?? ""} onChange={(expression) => onChange({ ...op, with: { expression } })} />}
      <label className="check"><input type="checkbox" checked={!!op.empty_as_null} onChange={(e) => onChange({ ...op, empty_as_null: e.target.checked })} />空字符串也算空值</label>
    </div>
  );
}

function TextCleanForm({ op, cols, onChange }) {
  const setStep = (i, step) => onChange({ ...op, steps: op.steps.map((s, k) => (k === i ? step : s)) });
  return (
    <div className="op-form">
      <ColChecks cols={cols} only={(c) => c.type === "text" || c.type === "month"} value={op.columns} onChange={(columns) => onChange({ ...op, columns })} legend="清理哪几列（只有文本列）" />
      {op.steps.map((step, i) => (
        <Row key={i}>
          <Select label="清理动作" value={step.do} onChange={(d) => setStep(i, d === "replace" ? { do: d, find: "", with: "" } : { do: d })}>
            {Object.entries(CLEAN_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          {step.do === "replace" && (
            <>
              <input type="text" aria-label="要找的文字" placeholder="要找的文字" value={step.find ?? ""} onChange={(e) => setStep(i, { ...step, find: e.target.value })} />
              <input type="text" aria-label="换成" placeholder="换成（可以空）" value={step.with ?? ""} onChange={(e) => setStep(i, { ...step, with: e.target.value })} />            </>
          )}
          <button className="plain" disabled={op.steps.length === 1} onClick={() => onChange({ ...op, steps: op.steps.filter((_, k) => k !== i) })}>删除</button>
        </Row>
      ))}
      <button className="plain" onClick={() => onChange({ ...op, steps: [...op.steps, { do: "trim" }] })}>加一个动作</button>
    </div>
  );
}

/** Looks at the first rows of the column as it is before this operator and lists the date formats that read them, best first. */
function FormatGuess({ where, op, onPick }) {
  const [guess, setGuess] = useState(null);
  const [error, setError] = useState("");
  const look = async () => {
    setError("");
    try {
      const before = where.index > 0 ? await previewNode(where.name, where.spec, where.stepId, where.index - 1) : await previewNode(where.name, where.spec, where.from);
      const at = before.columns.findIndex((c) => c.name === op.column);
      setGuess((await guessDateFormat(before.rows.map((r) => r[at]).filter((v) => typeof v === "string" && v.trim()).slice(0, 100))).formats);
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <div>
      <button className="plain" onClick={look} disabled={!op.column}>看看是什么格式</button>
      {error && <span className="error"> {error}</span>}
      {guess && (
        <ul className="plain-list">
          {guess.map((g) => (
            <li key={g.format}><button className="plain" onClick={() => onPick(g.format)}>{g.format}</button> 读出 {g.parsed} / {g.of}{g.failed.length > 0 && <span className="muted">，读不出的如 {g.failed.slice(0, 2).join("、")}</span>}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CastForm({ op, cols, onChange, where }) {
  const dated = op.to === "date" || op.to === "datetime";
  const numeric = op.to === "decimal" || op.to === "integer";
  return (
    <div className="op-form">
      <Row>
        <ColSelect cols={cols} value={op.column} label="要转的列" onChange={(column) => onChange({ ...op, column })} />
        <span>转成</span>
        <Select label="目标类型" value={op.to} onChange={(to) => onChange({ op: "cast", column: op.column, to, ...(op.as ? { as: op.as } : {}), ...(op.on_failure ? { on_failure: op.on_failure } : {}) })}>
          {Object.entries(CAST_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </Row>
      <label className="field">
        <span className="caption">结果放进哪一列（不写就替换原来的列）</span>
        <input type="text" value={op.as ?? ""} onChange={(e) => onChange({ ...op, as: e.target.value || undefined })} placeholder={op.column} />
      </label>
      {numeric && <label className="check"><input type="checkbox" checked={!!op.thousands} onChange={(e) => onChange({ ...op, thousands: e.target.checked || undefined })} />数字里有千分位逗号（2,500）</label>}
      {dated && (
        <label className="field">
          <span className="caption">日期的格式（不写就按 2026-05-03 这样读）</span>
          <input type="text" value={op.format ?? ""} placeholder="YYYY-MM-DD" onChange={(e) => onChange({ ...op, format: e.target.value || undefined })} />
          <FormatGuess where={where} op={op} onPick={(format) => onChange({ ...op, format })} />
        </label>
      )}
      <label className="check"><input type="checkbox" checked={op.on_failure === "stop"} onChange={(e) => onChange({ ...op, on_failure: e.target.checked ? "stop" : undefined })} />有转不了的值就停下，不继续运行</label>
    </div>
  );
}

function CalcForm({ op, cols, onChange, where }) {
  return (
    <div className="op-form">
      <Row>
        <label className="field"><span className="caption">新列的名字</span><input type="text" value={op.name} onChange={(e) => onChange({ ...op, name: e.target.value })} /></label>
        <label className="check"><input type="checkbox" checked={!!op.replace} disabled={!cols.some((c) => c.name === op.name)} onChange={(e) => onChange({ ...op, replace: e.target.checked || undefined })} />替换同名的列</label>
      </Row>
      <ExpressionEditor cols={cols} where={where} value={op.expression} onChange={(expression) => onChange({ ...op, expression })} />
    </div>
  );
}

function AggregateForm({ op, cols, onChange }) {
  const setAgg = (i, agg) => onChange({ ...op, aggregations: op.aggregations.map((a, k) => (k === i ? agg : a)) });
  const allowed = (column) => (column ? cols.find((c) => c.name === column)?.aggregations ?? [] : ["count"]);
  return (
    <div className="op-form">
      <ColChecks cols={cols} value={op.group_by} onChange={(group_by) => onChange({ ...op, group_by })} legend="按哪几列分组（不选就全部算成一组）" />
      {op.aggregations.map((agg, i) => {
        const fns = allowed(agg.column);
        const col = cols.find((c) => c.name === agg.column);
        return (
          <Row key={i}>
            <Select label="统计哪一列" value={agg.column ?? ""} onChange={(column) => {
              const next = allowed(column || null);
              setAgg(i, { fn: next.includes(agg.fn) ? agg.fn : next[0], ...(column ? { column } : {}), ...(agg.as ? { as: agg.as } : {}) });
            }}>
              <option value="">（整行）</option>
              {cols.map((c) => <option key={c.name} value={c.name}>{c.name}（{typeLabel(c.type)}）</option>)}
            </Select>
            <Select label="统计方式" value={agg.fn} onChange={(fn) => setAgg(i, { ...agg, fn })}>
              {fns.map((f) => <option key={f} value={f}>{AGG_LABEL[f]}</option>)}
            </Select>
            <input type="text" aria-label="结果列的名字" placeholder={aggDefaultName(agg)} value={agg.as ?? ""} onChange={(e) => setAgg(i, { ...agg, as: e.target.value || undefined })} />
            <button className="plain" disabled={op.aggregations.length === 1} onClick={() => onChange({ ...op, aggregations: op.aggregations.filter((_, k) => k !== i) })}>删除</button>
            {col?.code && <span className="muted small">代码列，只能计数</span>}
          </Row>
        );
      })}
      <button className="plain" onClick={() => onChange({ ...op, aggregations: [...op.aggregations, { fn: "count" }] })}>加一个统计</button>
      <p className="hint">空值不计入；中位数和 P25、P75 是精确值，不是估计。</p>
    </div>
  );
}

function DedupeForm({ op, cols, onChange }) {
  return (
    <div className="op-form">
      <ColChecks cols={cols} value={op.keys} onChange={(keys) => onChange({ ...op, keys })} legend="按哪几列排重（不选就整行一样才算重复）" />
      {op.keys.length > 0 && (
        <Row>
          <span>留</span>
          <Select label="留哪一条" value={op.keep} onChange={(keep) => onChange({ ...op, keep })}>
            <option value="first">最早的一条</option>
            <option value="last">最晚的一条</option>
          </Select>
          <span>按</span>
          <ColSelect cols={cols} only={(c) => ORDERABLE.includes(c.type)} value={op.order_by} label="按哪一列排先后" blank="选排先后的列" onChange={(order_by) => onChange({ ...op, order_by })} />
        </Row>
      )}
    </div>
  );
}

function LabelForm({ op, cols, onChange }) {
  const col = cols.find((c) => c.name === op.column);
  const mapping = op.mapping ?? [];
  const setMapping = (next) => onChange({ ...op, mapping: next });
  return (
    <div className="op-form">
      <Row>
        <ColSelect cols={[...cols].sort((a, b) => Number(!!b.code) - Number(!!a.code))} value={op.column} label="要换含义的列" onChange={(column) => onChange({ ...op, column })} />
        <span>结果放进</span>
        <input type="text" aria-label="结果的列名" placeholder={op.column || "原来的列"} value={op.as ?? ""} onChange={(e) => onChange({ ...op, as: e.target.value || undefined })} />
      </Row>
      <label className="check"><input type="checkbox" checked={!!op.from_meaning} disabled={!col?.meanings} onChange={(e) => onChange({ ...op, from_meaning: e.target.checked || undefined })} />读这一列已确认的含义{col && !col.meanings ? "（这一列还没有已确认的含义）" : ""}</label>
      {mapping.map((m, i) => (
        <Row key={i}>
          <input type="text" aria-label="代码" placeholder="代码" value={m.value ?? ""} onChange={(e) => setMapping(mapping.map((x, k) => (k === i ? { ...x, value: e.target.value } : x)))} />
          <span>是</span>
          <input type="text" aria-label="含义" placeholder="含义" value={m.label ?? ""} onChange={(e) => setMapping(mapping.map((x, k) => (k === i ? { ...x, label: e.target.value } : x)))} />
          <button className="plain" onClick={() => setMapping(mapping.filter((_, k) => k !== i))}>删除</button>
        </Row>
      ))}
      <button className="plain" onClick={() => setMapping([...mapping, { value: "", label: "" }])}>自己写一条对照</button>
      <Row>
        <span>对不上的代码</span>
        <Select label="对不上的代码怎么办" value={op.unmapped ?? "null"} onChange={(unmapped) => onChange({ ...op, unmapped, ...(unmapped === "other" ? { other: op.other ?? "" } : {}) })}>
          {Object.entries(UNMAPPED_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        {op.unmapped === "other" && <input type="text" aria-label="写成什么文字" value={op.other ?? ""} onChange={(e) => onChange({ ...op, other: e.target.value })} />}
      </Row>
    </div>
  );
}

const FORMS = { filter: FilterForm, fill_null: FillNullForm, text_clean: TextCleanForm, cast: CastForm, calc: CalcForm, aggregate: AggregateForm, dedupe: DedupeForm, label: LabelForm };

/** The form of one operator, over the columns it reads. `where` = {name, spec (the whole draft), stepId, index (of this operator), from (the step the transform reads)}. */
export function OperatorForm({ op, cols, onChange, where }) {
  const Form = FORMS[op.op];
  return Form ? <Form op={op} cols={cols} onChange={onChange} where={where} /> : <p className="muted">这个操作这里还不能编辑</p>;
}
