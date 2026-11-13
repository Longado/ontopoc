import React, { useEffect, useRef, useState } from "react";
import { fileToBase64, getDataset, getDatasets, uploadDatasets } from "./api.js";
import { Select } from "./Select.jsx";
import { ACCEPT, firstChoice, sizeText, uploadPayload, uploadProblem, withKeyColumn, withKind, withTarget, resultLine } from "./uploadModel.js";

const WAYS = [["new", "新数据集"], ["update_by_key", "按主键更新"], ["overwrite", "覆盖"]];
const WHO_KEY = "ontopoc.who";

function FileChoice({ file, choice, names, columns, onChange, onRemove }) {
  const taken = choice.kind === "new" && names.includes(choice.name.trim());
  return (
    <section className="file">
      <div className="file-head">
        <strong>{file.name}</strong>
        <span className="muted">{sizeText(file.size)}</span>
        <button className="plain" onClick={onRemove}>移除</button>
      </div>
      <div className="ways" role="radiogroup" aria-label={`${file.name} 的处理方式`}>
        {WAYS.map(([kind, label]) => (
          <label key={kind}>
            <input type="radio" name={`way-${file.name}`} checked={choice.kind === kind} onChange={() => onChange(withKind(choice, kind))} />
            {label}
          </label>
        ))}
      </div>
      {choice.kind === "new" && (
        <label className="field">
          <span className="caption">数据集名称</span>
          <input type="text" value={choice.name} onChange={(e) => onChange({ ...choice, name: e.target.value })} aria-invalid={taken} />
        </label>
      )}
      {(choice.kind === "update_by_key" || choice.kind === "overwrite") && (
        <label className="field">
          <span className="caption">更新哪个数据集</span>
          <Select label="目标数据集" value={choice.target ?? ""} onChange={(v) => onChange(withTarget(choice, v || null))}>
            <option value="">请选择</option>
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
          </Select>
        </label>
      )}
      {choice.kind === "update_by_key" && choice.target && (
        <fieldset className="keys">
          <legend>用哪几列对上现有的行（主键）</legend>
          {!columns && <span className="muted">读取列名</span>}
          {columns?.map((c) => (
            <label key={c.name}>
              <input type="checkbox" checked={choice.keyColumns.includes(c.name)} onChange={(e) => onChange(withKeyColumn(choice, c.name, e.target.checked))} />
              {c.name}{c.possible_key && <span className="faint"> 唯一</span>}
            </label>
          ))}
          <p className="hint">对上的行改成新文件里的值，新的主键追加在后面，不会删除任何行。</p>
        </fieldset>
      )}
      {choice.kind === "overwrite" && choice.target && <p className="hint">整表换成新文件，写成新的一版，旧版本还在版本页。</p>}
    </section>
  );
}

export function UploadDialog({ presetTarget, onClose, onDone }) {
  const ref = useRef(null);
  const input = useRef(null);
  const [who, setWho] = useState(() => window.localStorage.getItem(WHO_KEY) ?? "");
  const [names, setNames] = useState([]);
  const [files, setFiles] = useState([]);
  const [choices, setChoices] = useState([]);
  const [columnsOf, setColumnsOf] = useState({});
  const [phase, setPhase] = useState("pick");   // pick, sending, done
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
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

  const add = (picked) => {
    const fresh = [...picked];
    setFiles((old) => [...old, ...fresh]);
    setChoices((old) => [...old, ...fresh.map((f) => firstChoice(f.name, names, presetTarget))]);
    setError("");
  };
  const remove = (i) => {
    setFiles(files.filter((_, j) => j !== i));
    setChoices(choices.filter((_, j) => j !== i));
  };
  const problem = loaded ? uploadProblem(files, choices, names) : "";
  const close = () => {
    ref.current.close();
    if (phase === "done") onDone();
    onClose();
  };

  const send = async () => {
    setPhase("sending");
    setError("");
    try {
      const contents = await Promise.all(files.map(fileToBase64));
      const saved = await uploadDatasets(uploadPayload(who, files, contents, choices));
      window.localStorage.setItem(WHO_KEY, who.trim());
      setResults(saved);
      setPhase("done");
    } catch (e) {
      setError(e.message);
      setPhase("pick");
    }
  };

  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); close(); }}
      onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (phase === "pick" && loaded) add(e.dataTransfer.files); }}>
      <div className="dialog-body">
      <h2>{presetTarget ? `上传新版本：${presetTarget}` : "上传数据集"}</h2>
      {phase !== "done" && (
        <>
          <label className="field">
            <span className="caption">你的名字</span>
            <input type="text" value={who} placeholder="记在每个版本上" onChange={(e) => setWho(e.target.value)} />
          </label>
          <div className="pick">
            <button className="secondary" onClick={() => input.current.click()} disabled={phase === "sending" || !loaded}>选择文件</button>
            <span className="muted">.xlsx 或 .csv，可以一次选几个，也可以拖进来</span>
            <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          </div>
          {files.map((f, i) => (
            <FileChoice key={`${f.name}-${i}`} file={f} choice={choices[i]} names={names} columns={columnsOf[choices[i].target]}
              onChange={(c) => setChoices(choices.map((x, j) => (j === i ? c : x)))} onRemove={() => remove(i)} />
          ))}
          {error && <p className="error">{error}</p>}
        </>
      )}
      {phase === "done" && <ul className="results">{results.map((r) => <li key={r.name}>{resultLine(r)}</li>)}</ul>}
      </div>
      {phase !== "done" ? (
        <div className="actions">
          <span className="muted">{files.length ? problem : ""}</span>
          <button className="plain" onClick={close}>取消</button>
          <button className="primary" onClick={send} disabled={!files.length || !!problem || phase === "sending"}>{phase === "sending" ? "上传中" : "上传"}</button>
        </div>
      ) : (
        <div className="actions"><span></span><button className="primary" onClick={close}>完成</button></div>
      )}
    </dialog>
  );
}
