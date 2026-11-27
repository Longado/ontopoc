import React, { useState } from "react";
import { guessDateFormat, previewNode } from "./api.js";
import { AiBox } from "./AiBox.jsx";
import { ExpressionEditor } from "./ExpressionEditor.jsx";
import { typeLabel } from "./format.js";
import { AGG_LABEL, CAST_LABEL, CLEAN_LABEL, CMP_LABEL, UNMAPPED_LABEL, aggAutoName, extractProblems, retargetAgg } from "./pipelineModel.js";
import { t } from "./i18n/index.js";
import { Select } from "./Select.jsx";

const NUMBERISH = ["integer", "decimal", "date", "datetime", "month"];
const NO_VALUE = ["is_null", "not_null"];

function ColSelect({ cols, value, onChange, label, blank = t("steps.ops.pickCol"), only }) {
  return (
    <Select label={label} value={value ?? ""} onChange={onChange}>
      <option value="">{blank}</option>
      {cols.filter((c) => !only || only(c)).map((c) => <option key={c.name} value={c.name}>{c.name} ({typeLabel(c.type)})</option>)}
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

export function FilterForm({ op, cols, onChange, where, lead = t("steps.ops.f.lead"), tail = t("steps.ops.f.tail") }) {
  const group = op.where.any ? "any" : "all";
  const rows = op.where[group] ?? [];
  const setRows = (next, g = group) => onChange({ ...op, where: { [g]: next } });
  const setRow = (i, row) => setRows(rows.map((r, k) => (k === i ? row : r)));
  return (
    <div className="op-form">
      {where && <AiBox where={where} kind="filter" onApply={(d) => onChange({ ...op, where: d.where })} />}
      <div className="inline">
        <span>{lead}</span>
        <Select label={t("steps.ops.f.relation")} value={group} onChange={(g) => setRows(rows, g)}>
          <option value="all">{t("steps.ops.f.all")}</option>
          <option value="any">{t("steps.ops.f.any")}</option>
        </Select>
        <span>{tail}</span>
      </div>
      {rows.map((row, i) => {
        if (row.all || row.any) return <Row key={i}><span className="muted">{t("steps.ops.f.nested")}</span><button className="plain" onClick={() => setRows(rows.filter((_, k) => k !== i))}>{t("steps.ops.delete")}</button></Row>;
        const col = cols.find((c) => c.name === row.column);
        const byMeaning = row.meaning !== undefined;
        const meanings = col?.meanings ? Object.keys(col.meanings) : [];
        return (
          <Row key={i}>
            <ColSelect cols={cols} value={row.column} label={t("steps.ops.f.col")} onChange={(column) => setRow(i, { column, cmp: "eq", value: "" })} />
            <Select label={t("steps.ops.f.cmp")} value={row.cmp} onChange={(cmp) => setRow(i, { column: row.column, cmp, ...(byMeaning ? { meaning: row.meaning } : cmp === "in" ? { values: [] } : cmp === "between" ? { low: "", high: "" } : NO_VALUE.includes(cmp) ? {} : { value: "" }) })}>
              {Object.entries(CMP_LABEL).filter(([k]) => !byMeaning || ["eq", "ne"].includes(k)).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
            {byMeaning ? (
              <Select label={t("steps.ops.f.meaning")} value={row.meaning} onChange={(meaning) => setRow(i, { ...row, meaning })}>
                <option value="">{t("steps.ops.f.pickMeaning")}</option>
                {meanings.map((m) => <option key={m} value={m}>{m}</option>)}
              </Select>
            ) : row.cmp === "between" ? (
              <>
                <input type="text" aria-label={t("steps.ops.f.low")} value={row.low ?? ""} onChange={(e) => setRow(i, { ...row, low: e.target.value })} />
                <span>{t("steps.ops.f.to")}</span>
                <input type="text" aria-label={t("steps.ops.f.high")} value={row.high ?? ""} onChange={(e) => setRow(i, { ...row, high: e.target.value })} />
              </>
            ) : row.cmp === "in" ? (
              <input type="text" aria-label={t("steps.ops.f.list")} placeholder={t("steps.ops.f.listPh")} value={(row.values ?? []).join(", ")}
                onChange={(e) => setRow(i, { ...row, values: e.target.value.split(/[,\uff0c]\s*/) })} onBlur={() => setRow(i, { ...row, values: (row.values ?? []).filter(Boolean) })} />
            ) : NO_VALUE.includes(row.cmp) ? null : (
              <input type="text" aria-label={t("steps.ops.f.value")} placeholder={t("steps.ops.f.valuePh")} className={row.column && !row.value && row.value !== 0 ? "todo-input" : undefined} value={row.value ?? ""} onChange={(e) => setRow(i, { ...row, value: e.target.value })} />
            )}
            {meanings.length > 0 && ["eq", "ne"].includes(row.cmp) && (
              <label className="check"><input type="checkbox" checked={byMeaning} onChange={(e) => setRow(i, e.target.checked ? { column: row.column, cmp: row.cmp, meaning: "" } : { column: row.column, cmp: row.cmp, value: "" })} />{t("steps.ops.f.byMeaning")}</label>
            )}
            <button className="plain" onClick={() => setRows(rows.filter((_, k) => k !== i))} disabled={rows.length === 1}>{t("steps.ops.delete")}</button>
          </Row>
        );
      })}
      <button className="plain" onClick={() => setRows([...rows, { column: "", cmp: "eq", value: "" }])}>{t("steps.ops.f.add")}</button>
      {cols.some((c) => c.code) && <p className="hint">{t("steps.ops.f.hint")}</p>}
    </div>
  );
}

function FillNullForm({ op, cols, onChange, where }) {
  const kind = op.with?.column !== undefined ? "column" : op.with?.expression !== undefined ? "expression" : "constant";
  const setKind = (k) => onChange({ ...op, with: k === "constant" ? { constant: "" } : k === "column" ? { column: "" } : { expression: "" } });
  return (
    <div className="op-form">
      <ColChecks cols={cols} value={op.columns} onChange={(columns) => onChange({ ...op, columns })} legend={t("steps.ops.n.cols")} />
      <div className="inline">
        <span>{t("steps.ops.n.with")}</span>
        <Select label={t("steps.ops.n.withWhat")} value={kind} onChange={setKind}>
          <option value="constant">{t("steps.ops.n.constant")}</option>
          <option value="column">{t("steps.ops.n.column")}</option>
          <option value="expression">{t("steps.ops.n.expression")}</option>
        </Select>
        {kind === "constant" && <input type="text" aria-label={t("steps.ops.n.fixed")} value={op.with.constant ?? ""} onChange={(e) => onChange({ ...op, with: { constant: e.target.value } })} />}
        {kind === "column" && <ColSelect cols={cols} value={op.with.column} label={t("steps.ops.n.other")} onChange={(column) => onChange({ ...op, with: { column } })} />}
      </div>
      {kind === "expression" && <ExpressionEditor cols={cols} where={where} value={op.with.expression ?? ""} onChange={(expression) => onChange({ ...op, with: { expression } })} />}
      <label className="check"><input type="checkbox" checked={!!op.empty_as_null} onChange={(e) => onChange({ ...op, empty_as_null: e.target.checked })} />{t("steps.ops.n.emptyString")}</label>
    </div>
  );
}

function TextCleanForm({ op, cols, onChange }) {
  const setStep = (i, step) => onChange({ ...op, steps: op.steps.map((s, k) => (k === i ? step : s)) });
  return (
    <div className="op-form">
      <ColChecks cols={cols} only={(c) => c.type === "text" || c.type === "month"} value={op.columns} onChange={(columns) => onChange({ ...op, columns })} legend={t("steps.ops.c.cols")} />
      {op.steps.map((step, i) => (
        <Row key={i}>
          <Select label={t("steps.ops.c.action")} value={step.do} onChange={(d) => setStep(i, d === "replace" ? { do: d, find: "", with: "" } : { do: d })}>
            {Object.entries(CLEAN_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          {step.do === "replace" && (
            <>
              <input type="text" aria-label={t("steps.ops.c.find")} placeholder={t("steps.ops.c.find")} value={step.find ?? ""} onChange={(e) => setStep(i, { ...step, find: e.target.value })} />
              <input type="text" aria-label={t("steps.ops.c.with")} placeholder={t("steps.ops.c.withPh")} value={step.with ?? ""} onChange={(e) => setStep(i, { ...step, with: e.target.value })} />            </>
          )}
          <button className="plain" disabled={op.steps.length === 1} onClick={() => onChange({ ...op, steps: op.steps.filter((_, k) => k !== i) })}>{t("steps.ops.delete")}</button>
        </Row>
      ))}
      <button className="plain" onClick={() => onChange({ ...op, steps: [...op.steps, { do: "trim" }] })}>{t("steps.ops.c.add")}</button>
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
      <button className="plain" onClick={look} disabled={!op.column}>{t("steps.ops.g.look")}</button>
      {error && <span className="error"> {error}</span>}
      {guess && (
        <ul className="plain-list">
          {guess.map((g) => (
            <li key={g.format}><button className="plain" onClick={() => onPick(g.format)}>{g.format}</button>{t("steps.ops.g.parsed", { parsed: g.parsed, of: g.of })}{g.failed.length > 0 && <span className="muted">{t("steps.ops.g.failed", { values: g.failed.slice(0, 2).join(", ") })}</span>}</li>
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
        <ColSelect cols={cols} value={op.column} label={t("steps.ops.k.col")} onChange={(column) => onChange({ ...op, column })} />
        <span>{t("steps.ops.k.to")}</span>
        <Select label={t("steps.ops.k.type")} value={op.to} onChange={(to) => onChange({ op: "cast", column: op.column, to, ...(op.as ? { as: op.as } : {}), ...(op.on_failure ? { on_failure: op.on_failure } : {}) })}>
          {Object.entries(CAST_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </Row>
      <label className="field">
        <span className="caption">{t("steps.ops.k.as")}</span>
        <input type="text" value={op.as ?? ""} onChange={(e) => onChange({ ...op, as: e.target.value || undefined })} placeholder={op.column} />
      </label>
      {numeric && <label className="check"><input type="checkbox" checked={!!op.thousands} onChange={(e) => onChange({ ...op, thousands: e.target.checked || undefined })} />{t("steps.ops.k.thousands")}</label>}
      {dated && (
        <label className="field">
          <span className="caption">{t("steps.ops.k.format")}</span>
          <input type="text" value={op.format ?? ""} placeholder="YYYY-MM-DD" onChange={(e) => onChange({ ...op, format: e.target.value || undefined })} />
          <FormatGuess where={where} op={op} onPick={(format) => onChange({ ...op, format })} />
        </label>
      )}
      <label className="check"><input type="checkbox" checked={op.on_failure === "stop"} onChange={(e) => onChange({ ...op, on_failure: e.target.checked ? "stop" : undefined })} />{t("steps.ops.k.stop")}</label>
    </div>
  );
}

function CalcForm({ op, cols, onChange, where }) {
  return (
    <div className="op-form">
      <AiBox where={where} kind="calc" onApply={(d) => onChange({ ...op, name: op.name || d.name, expression: d.expression })} />
      <Row>
        <label className="field"><span className="caption">{t("steps.ops.a.name")}</span><input type="text" value={op.name} onChange={(e) => onChange({ ...op, name: e.target.value })} /></label>
        <label className="check"><input type="checkbox" checked={!!op.replace} disabled={!cols.some((c) => c.name === op.name)} onChange={(e) => onChange({ ...op, replace: e.target.checked || undefined })} />{t("steps.ops.a.replace")}</label>
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
      <ColChecks cols={cols} value={op.group_by} onChange={(group_by) => onChange({ ...op, group_by })} legend={t("steps.ops.g2.groupBy")} />
      {op.aggregations.map((agg, i) => {
        const fns = allowed(agg.column);
        const col = cols.find((c) => c.name === agg.column);
        return (
          <Row key={i}>
            <Select label={t("steps.ops.g2.which")} value={agg.column ?? ""} onChange={(column) => {
              const next = allowed(column || null);
              setAgg(i, retargetAgg(agg, { fn: next.includes(agg.fn) ? agg.fn : next[0], column }));
            }}>
              <option value="">{t("steps.ops.g2.wholeRow")}</option>
              {cols.map((c) => <option key={c.name} value={c.name}>{c.name} ({typeLabel(c.type)})</option>)}
            </Select>
            <Select label={t("steps.ops.g2.fn")} value={agg.fn} onChange={(fn) => setAgg(i, retargetAgg(agg, { fn }))}>
              {fns.map((f) => <option key={f} value={f}>{AGG_LABEL[f]}</option>)}
            </Select>
            <input type="text" aria-label={t("steps.ops.g2.as")} placeholder={aggAutoName(agg)} value={agg.as ?? ""} onChange={(e) => setAgg(i, { ...agg, as: e.target.value || undefined })} />
            <button className="plain" disabled={op.aggregations.length === 1} onClick={() => onChange({ ...op, aggregations: op.aggregations.filter((_, k) => k !== i) })}>{t("steps.ops.delete")}</button>
            {col?.code && <span className="muted small">{t("steps.ops.g2.codeOnly")}</span>}
          </Row>
        );
      })}
      <button className="plain" onClick={() => onChange({ ...op, aggregations: [...op.aggregations, { fn: "count", as: aggAutoName({ fn: "count" }) }] })}>{t("steps.ops.g2.add")}</button>
      <p className="hint">{t("steps.ops.g2.hint")}</p>
    </div>
  );
}

function DedupeForm({ op, cols, onChange }) {
  return (
    <div className="op-form">
      <ColChecks cols={cols} value={op.keys} onChange={(keys) => onChange({ ...op, keys })} legend={t("steps.ops.d.keys")} />
      {op.keys.length > 0 && (
        <Row>
          <span>{t("steps.ops.d.keep")}</span>
          <Select label={t("steps.ops.d.keepWhich")} value={op.keep} onChange={(keep) => onChange({ ...op, keep })}>
            <option value="first">{t("steps.ops.d.first")}</option>
            <option value="last">{t("steps.ops.d.last")}</option>
          </Select>
          <span>{t("steps.ops.d.by")}</span>
          <ColSelect cols={cols} value={op.order_by} label={t("steps.ops.d.orderBy")} blank={t("steps.ops.d.orderPh")} onChange={(order_by) => onChange({ ...op, order_by })} />
        </Row>
      )}
      {op.keys.length > 0 && op.order_by && !NUMBERISH.includes(cols.find((c) => c.name === op.order_by)?.type) && <p className="hint">{t("steps.ops.d.hint")}</p>}
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
        <ColSelect cols={[...cols].sort((a, b) => Number(!!b.code) - Number(!!a.code))} value={op.column} label={t("steps.ops.l.col")} onChange={(column) => onChange({ ...op, column })} />
        <span>{t("steps.ops.l.into")}</span>
        <input type="text" aria-label={t("steps.ops.l.asLabel")} placeholder={op.column || t("steps.ops.l.asPh")} value={op.as ?? ""} onChange={(e) => onChange({ ...op, as: e.target.value || undefined })} />
      </Row>
      <label className="check"><input type="checkbox" checked={!!op.from_meaning} disabled={!col?.meanings} onChange={(e) => onChange({ ...op, from_meaning: e.target.checked || undefined })} />{t("steps.ops.l.fromMeaning")}{col && !col.meanings ? t("steps.ops.l.noMeaning") : ""}</label>
      {mapping.map((m, i) => (
        <Row key={i}>
          <input type="text" aria-label={t("steps.ops.l.code")} placeholder={t("steps.ops.l.code")} value={m.value ?? ""} onChange={(e) => setMapping(mapping.map((x, k) => (k === i ? { ...x, value: e.target.value } : x)))} />
          <span>{t("steps.ops.l.is")}</span>
          <input type="text" aria-label={t("steps.ops.f.meaning")} placeholder={t("steps.ops.f.meaning")} value={m.label ?? ""} onChange={(e) => setMapping(mapping.map((x, k) => (k === i ? { ...x, label: e.target.value } : x)))} />
          <button className="plain" onClick={() => setMapping(mapping.filter((_, k) => k !== i))}>{t("steps.ops.delete")}</button>
        </Row>
      ))}
      <button className="plain" onClick={() => setMapping([...mapping, { value: "", label: "" }])}>{t("steps.ops.l.addMap")}</button>
      <Row>
        <span>{t("steps.ops.l.unmapped")}</span>
        <Select label={t("steps.ops.l.unmappedWhat")} value={op.unmapped ?? "null"} onChange={(unmapped) => onChange({ ...op, unmapped, ...(unmapped === "other" ? { other: op.other ?? "" } : {}) })}>
          {Object.entries(UNMAPPED_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        {op.unmapped === "other" && <input type="text" aria-label={t("steps.ops.l.otherText")} value={op.other ?? ""} onChange={(e) => onChange({ ...op, other: e.target.value })} />}
      </Row>
    </div>
  );
}

/** Split a text column on a separator taken as written and put one part into a new column. The rows it would give are in the preview below the form, as for the other
 * operators; the rows without the separator are counted there and in the run. */
function ExtractForm({ op, cols, onChange }) {
  const problems = extractProblems(op);
  const last = op.part === "last";
  return (
    <div className="op-form">
      <Row>
        <ColSelect cols={cols} only={(c) => c.type === "text"} value={op.column} label={t("steps.ops.x.col")} onChange={(column) => onChange({ ...op, column })} />
        <label className="field"><span className="caption">{t("steps.ops.x.separator")}</span>
          <input type="text" maxLength={10} value={op.separator ?? ""} placeholder={t("steps.ops.x.separatorPh")} onChange={(e) => onChange({ ...op, separator: e.target.value })} /></label>
      </Row>
      <Row>
        <Select label={t("steps.ops.x.part")} value={last ? "last" : "n"} onChange={(v) => onChange({ ...op, part: v === "last" ? "last" : 1 })}>
          <option value="n">{t("steps.ops.x.nth")}</option>
          <option value="last">{t("steps.ops.x.last")}</option>
        </Select>
        {!last && <input type="number" min={1} max={100} step={1} aria-label={t("steps.ops.x.partN")} value={op.part ?? ""} onChange={(e) => onChange({ ...op, part: e.target.value === "" ? "" : Number(e.target.value) })} />}
        <label className="field"><span className="caption">{t("steps.ops.x.as")}</span>
          <input type="text" value={op.as ?? ""} onChange={(e) => onChange({ ...op, as: e.target.value })} /></label>
      </Row>
      {problems.map((p) => <p key={p} className="error">{p}</p>)}
      <p className="hint">{t("steps.ops.x.hint")}</p>
    </div>
  );
}

const FORMS = { filter: FilterForm, fill_null: FillNullForm, text_clean: TextCleanForm, cast: CastForm, calc: CalcForm, aggregate: AggregateForm, dedupe: DedupeForm, label: LabelForm, extract: ExtractForm };

/** The form of one operator, over the columns it reads. `where` = {name, spec (the whole draft), stepId, index (of this operator), from (the step the transform reads)}. */
export function OperatorForm({ op, cols, onChange, where }) {
  const Form = FORMS[op.op];
  return Form ? <Form op={op} cols={cols} onChange={onChange} where={where} /> : <p className="muted">{t("steps.ops.noEdit")}</p>;
}
