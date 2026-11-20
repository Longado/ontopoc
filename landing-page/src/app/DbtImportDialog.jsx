import React, { useEffect, useRef, useState } from "react";
import { importDbt } from "./api.js";
import { fileProblem, importSections, importSummary } from "./dbtImportModel.js";
import { t } from "./i18n/index.js";

/** Reads a dbt manifest.json: a preview of what would be proposed and skipped (nothing written), then Apply. The service decides everything; nothing is confirmed. */
export function DbtImportDialog({ onClose, onDone }) {
  const ref = useRef(null);
  const [text, setText] = useState(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");   // "preview" or "apply" while the service works
  useEffect(() => ref.current.showModal(), []);
  const close = () => {
    if (busy) return;   // an apply under way finishes on the service; closing now would hide what it proposed
    ref.current.close();
    onClose();
  };
  const pick = async (file) => {
    setResult(null);
    setText(null);
    setError(fileProblem(file));
    if (file && !fileProblem(file)) setText(await file.text());
  };
  const run = async (apply) => {
    setBusy(apply ? "apply" : "preview");
    setError("");
    try {
      setResult(await importDbt(text, apply));
      if (apply) onDone();
    } catch (e) {
      setError(e.message);
    }
    setBusy("");
  };
  const summary = result && importSummary(result);
  const m = result?.manifest;
  return (
    <dialog ref={ref} className="upload dbt-import" onCancel={(e) => { e.preventDefault(); close(); }}>
      <div className="dialog-body">
        <h2>{t("types.dbt.title")}</h2>
        {!result?.applied && (
          <>
            <p>{t("types.dbt.intro")}</p>
            <label className="field">
              <span className="caption">{t("types.dbt.file")}</span>
              <input type="file" accept=".json,application/json" disabled={!!busy} onChange={(e) => pick(e.target.files?.[0])} />
            </label>
            <p className="hint">{t("types.dbt.reads")}</p>
            <p className="hint">{t("types.dbt.slow")}</p>
          </>
        )}
        {result && (
          <>
            <p className="muted small">{t("types.dbt.manifestLine", { dbt: m.dbt_version ?? "?", version: m.schema_version, models: m.models, tests: m.tests })}</p>
            {m.note && <p className="warn">{m.note}</p>}
            <p className="dbt-headline">{summary.headline}</p>
            {importSections(result).map((s) => (
              <section key={s.id} className="dbt-section">
                <h3>{s.title}</h3>
                <ul className="results">
                  {s.items.map((item, i) => <li key={i}>{item.href && result.applied ? <a href={item.href} onClick={close}>{item.text}</a> : item.text}</li>)}
                </ul>
                {s.more && <p className="muted small">{s.more}</p>}
              </section>
            ))}
          </>
        )}
      </div>
      <div className="actions">
        {error ? <span className="error" role="alert">{error}</span> : <span></span>}
        {result?.applied ? (
          <button className="primary" onClick={close}>{t("common.close")}</button>
        ) : (
          <>
            <button className="plain" onClick={close} disabled={!!busy}>{t("common.cancel")}</button>
            {summary?.canApply ? (
              <button className="primary" onClick={() => run(true)} disabled={!!busy}>{busy === "apply" ? t("types.dbt.applying") : t("types.dbt.apply")}</button>
            ) : (
              <button className="primary" onClick={() => run(false)} disabled={!text || !!busy || !!result}>{busy === "preview" ? t("types.dbt.reading") : t("types.dbt.preview")}</button>
            )}
          </>
        )}
      </div>
    </dialog>
  );
}
