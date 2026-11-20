import React, { useEffect, useRef, useState } from "react";
import { fileToBase64, getDataset, getDatasets, previewUpload, uploadDatasets } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { t, useT } from "./i18n/index.js";
import { ImpactList } from "./ImpactList.jsx";
import { impactMatters } from "./impactModel.js";
import { Select } from "./Select.jsx";
import { ACCEPT, afterUpload, updateWays, waysFor, changesExisting, firstChoice, movedLines, sizeText, uploadPayload, uploadProblem, withKeyColumn, withKind, withTarget, resultLine } from "./uploadModel.js";

const WHO_KEY = "ontopoc.who";

function FileChoice({ file, choice, names, columns, refused, onChange, onRemove }) {
  const ways = waysFor(names);
  const taken = choice.kind === "new" && names.includes(choice.name.trim());
  return (
    <section className={`file${refused ? " refused" : ""}`}>
      <div className="file-head">
        <strong>{file.name}</strong>
        <span className="muted">{sizeText(file.size)}</span>
        <button className="plain" onClick={onRemove}>{t("data.upl.remove")}</button>
      </div>
      <div className="ways" role="radiogroup" aria-label={t("data.upl.waysAria", { file: file.name })}>
        {ways.primary.map((w) => (
          <label key={w.kind} className="way">
            <input type="radio" name={`way-${file.name}`} checked={choice.kind === w.kind} onChange={() => onChange(withKind(choice, w.kind))} />
            <span><strong>{w.label}</strong><span className="muted small block">{w.consequence}</span></span>
          </label>
        ))}
        {ways.folded.length > 0 && (
          <details className="way-fold" open={updateWays(choice).open}>
            <summary>{t("data.upl.updateExisting")}</summary>
            {ways.folded.map((w) => (
              <label key={w.kind} className="way">
                <input type="radio" name={`way-${file.name}`} checked={choice.kind === w.kind} onChange={() => onChange(withKind(choice, w.kind))} />
                <span><strong>{w.label}</strong><span className="muted small block">{w.consequence}</span></span>
              </label>
            ))}
          </details>
        )}
      </div>
      {choice.kind === "new" && (
        <label className="field">
          <span className="caption">{t("data.upl.name")}</span>
          <input type="text" value={choice.name} onChange={(e) => onChange({ ...choice, name: e.target.value })} aria-invalid={taken} />
        </label>
      )}
      {(choice.kind === "update_by_key" || choice.kind === "overwrite") && (
        <label className="field">
          <span className="caption">{t("data.upl.target")}</span>
          <Select label={t("data.upl.targetAria")} value={choice.target ?? ""} onChange={(v) => onChange(withTarget(choice, v || null))}>
            <option value="">{t("data.upl.choose")}</option>
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
          </Select>
        </label>
      )}
      {choice.kind === "update_by_key" && choice.target && (
        <fieldset className="keys">
          <legend>{t("data.upl.keysLegend")}</legend>
          {!columns && <span className="muted">{t("data.upl.readingColumns")}</span>}
          {columns?.map((c) => (
            <label key={c.name}>
              <input type="checkbox" checked={choice.keyColumns.includes(c.name)} onChange={(e) => onChange(withKeyColumn(choice, c.name, e.target.checked))} />
              {c.name}{c.possible_key && <span className="faint"> {t("data.upl.unique")}</span>}
            </label>
          ))}
          <p className="hint">{t("data.upl.keysHint")}</p>
        </fieldset>
      )}
      {choice.kind === "overwrite" && choice.target && <p className="hint">{t("data.upl.overwriteHint")}</p>}
      {refused && <p className="error refusal">{refused}</p>}
    </section>
  );
}

export function UploadDialog({ presetTarget, onClose, onDone }) {
  useT();
  const ref = useRef(null);
  const input = useRef(null);
  const signedIn = useAuth().auth;   // signed in: the service signs with the account's name; the name box is only for a service run without sign-in
  const [who, setWho] = useState(() => window.localStorage.getItem(WHO_KEY) ?? "");
  const [names, setNames] = useState([]);
  const [files, setFiles] = useState([]);
  const [choices, setChoices] = useState([]);
  const [columnsOf, setColumnsOf] = useState({});
  const [phase, setPhase] = useState("pick");   // pick, sending, ask (what the upload would send back, waiting for a yes), done
  const [moved, setMoved] = useState([]);
  const [boards, setBoards] = useState(null);   // the board cards the upload would move (change_preview), shown with what it sends back
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
  const [refused, setRefused] = useState({});   // the service's problem with each file, by its position
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    ref.current.showModal();
    getDatasets().then((list) => setNames(list.map((d) => d.name)), (e) => setError(e.message)).finally(() => setLoaded(true));
  }, []);

  // the key-column choices come from the target dataset's own columns
  const wanted = [...new Set(choices.filter((c) => c.kind === "update_by_key" && c.target).map((c) => c.target))];
  useEffect(() => {
    for (const target of wanted.filter((t) => !(t in columnsOf))) {
      getDataset(target).then((d) => setColumnsOf((m) => ({ ...m, [target]: d.columns })), () => setColumnsOf((m) => ({ ...m, [target]: [] })));
      setColumnsOf((m) => ({ ...m, [target]: undefined }));
    }
  }, [wanted.join("\u0000")]);

  const settle = () => {
    setError("");
    setRefused({});
  };
  const add = (picked) => {
    const fresh = [...picked];
    setFiles((old) => [...old, ...fresh]);
    setChoices((old) => [...old, ...fresh.map((f) => firstChoice(f.name, names, presetTarget))]);
    settle();
  };
  const remove = (i) => {
    setFiles(files.filter((_, j) => j !== i));
    setChoices(choices.filter((_, j) => j !== i));
    settle();
  };
  useEffect(() => {
    ref.current?.querySelector(".file.refused")?.scrollIntoView({ block: "nearest" });   // the refused file may be below the fold
  }, [refused]);
  const problem = loaded ? uploadProblem(files, choices, names) : "";
  const close = () => {
    ref.current.close();
    onClose();
  };

  const send = async (asked = false) => {
    setPhase("sending");
    setError("");
    try {
      const contents = await Promise.all(files.map(fileToBase64));
      const payload = uploadPayload(who, files, contents, choices);
      if (!asked && changesExisting(payload)) {
        const found = await previewUpload(payload);
        if (found.moved.length || impactMatters(found.boards)) {
          setMoved(found.moved);
          setBoards(found.boards ?? null);
          setPhase("ask");
          return;
        }
      }
      const saved = await uploadDatasets(payload);
      window.localStorage.setItem(WHO_KEY, who.trim());
      setResults(saved);
      setPhase("done");
      onDone();   // the list behind the dialog is up to date before the person has pressed anything
    } catch (e) {
      setError(e.message);
      setRefused(e.files ?? {});
      setPhase("pick");
    }
  };

  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); close(); }}
      onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (phase === "pick" && loaded) add(e.dataTransfer.files); }}>
      <div className="dialog-body">
      <h2>{presetTarget ? t("data.upl.titleVersion", { name: presetTarget }) : t("data.upl.title")}</h2>
      {phase === "ask" && (
        <>
          {boards && <ImpactList impact={boards} upload />}
          {moved.length > 0 && (
            <>
              <p><strong>{t("data.upl.askTitle", { count: moved.length })}</strong>{t("data.upl.askText")}</p>
              <ul className="results">
                {movedLines(moved).map((m) => <li key={m.key}>{m.what}<span className="muted small block">{m.reason}</span></li>)}
              </ul>
            </>
          )}
        </>
      )}
      {(phase === "pick" || phase === "sending") && (
        <>
          {!signedIn && (
            <label className="field">
              <span className="caption">{t("data.upl.who")}</span>
              <input type="text" value={who} placeholder={t("data.upl.whoHint")} onChange={(e) => setWho(e.target.value)} />
            </label>
          )}
          <div className="pick">
            <button className="secondary" onClick={() => input.current.click()} disabled={phase === "sending" || !loaded}>{t("data.upl.chooseFiles")}</button>
            <span className="muted">{t("data.upl.pickHint")}</span>
            <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          </div>
          {files.map((f, i) => (
            <FileChoice key={`${f.name}-${i}`} file={f} choice={choices[i]} names={names} columns={columnsOf[choices[i].target]}
              refused={refused[i]} onChange={(c) => { setChoices(choices.map((x, j) => (j === i ? c : x))); settle(); }} onRemove={() => remove(i)} />
          ))}
        </>
      )}
      {phase === "done" && <ul className="results">{results.map((r) => <li key={r.name}>{resultLine(r)}{r.recheck_error && <span className="error"> {t("data.upl.recheck", { error: r.recheck_error })}</span>}
        {r.overwrites_action_rows?.length > 0 && <span className="warn block"> {t("data.upl.overwroteActions", { rows: r.overwrites_action_rows.map((o) => (o.removed ? t("data.upl.rowGone", { key: o.key }) : t("data.upl.rowChanged", { key: o.key, columns: o.columns.join(t("data.listSep")), action: o.action, approver: o.approved_by }))).join(t("data.semi")) })}</span>}</li>)}</ul>}
      </div>
      {phase === "ask" ? (
        <div className="actions">
          <span className="muted">{t(moved.length ? "data.upl.askFoot" : "data.upl.askFootBoards")}</span>
          <button className="plain" onClick={() => setPhase("pick")}>{t("data.upl.back")}</button>
          <button className="primary" onClick={() => send(true)}>{t("data.upl.continue")}</button>
        </div>
      ) : phase !== "done" ? (
        <div className="actions">
          {error ? <span className="error">{error}</span> : <span className="muted">{files.length ? problem : ""}</span>}
          <button className="plain" onClick={close}>{t("common.cancel")}</button>
          <button className="primary" onClick={() => send()} disabled={!files.length || !!problem || phase === "sending"}>{phase === "sending" ? t("data.upl.sending") : t("data.upl.submit")}</button>
        </div>
      ) : (
        <div className="actions">
          <span className="muted">{t("data.upl.next")}</span>
          <button className="plain" onClick={close}>{t("data.upl.done")}</button>
          {afterUpload(results).map((a, i, all) => <a key={a.label} className={`button${i === all.length - 1 ? " primary" : " secondary"}`} href={a.href} onClick={close}>{a.label}</a>)}
        </div>
      )}
    </dialog>
  );
}
