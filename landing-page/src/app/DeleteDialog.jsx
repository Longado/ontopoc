import React, { useEffect, useRef, useState } from "react";
import { deleteDataset } from "./api.js";

const WHO_KEY = "ontopoc.who";

/** Asks before removing a dataset with all its versions; when something reads it, says what, and removes nothing. */
export function DeleteDialog({ name, page, onClose }) {
  const ref = useRef(null);
  const [who, setWho] = useState(() => window.localStorage.getItem(WHO_KEY) ?? "");
  const [error, setError] = useState("");
  const [readers, setReaders] = useState([]);
  const [sending, setSending] = useState(false);
  useEffect(() => ref.current.showModal(), []);
  const close = () => {
    ref.current.close();
    onClose();
  };
  const send = async () => {
    setSending(true);
    setError("");
    try {
      await deleteDataset(name, who);
      window.localStorage.setItem(WHO_KEY, who.trim());
      window.location.hash = "#/datasets";
    } catch (e) {
      setError(e.message);
      setReaders(e.readers ?? []);
      setSending(false);
    }
  };
  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); close(); }}>
      <div className="dialog-body">
        <h2>删除“{name}”</h2>
        <p>它的 {page.versions.length} 个版本和全部 {page.rows} 行都会删掉，不能恢复。任务里会留一条“删除”的记录。</p>
        <label className="field">
          <span className="caption">你的名字</span>
          <input type="text" value={who} placeholder="记在删除记录上" onChange={(e) => setWho(e.target.value)} />
        </label>
        {readers.length > 0 && <ul className="readers error">{readers.map((r, i) => <li key={i}>{r.kind}「{r.name}」</li>)}</ul>}
      </div>
      <div className="actions">
        {error ? <span className="error">{readers.length ? "有东西在读它，先处理它们，再删。" : error}</span> : <span></span>}
        <button className="plain" onClick={close}>取消</button>
        <button className="primary" onClick={send} disabled={sending || readers.length > 0}>{sending ? "删除中" : "删除"}</button>
      </div>
    </dialog>
  );
}
