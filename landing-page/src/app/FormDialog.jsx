import React, { useEffect, useRef, useState } from "react";

/** A small modal with a form, closed by 取消 or Escape. */
export function FormDialog({ title, onClose, children, submitLabel, onSubmit, valid }) {
  const ref = useRef(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  useEffect(() => ref.current.showModal(), []);
  const close = () => {
    ref.current.close();
    onClose();
  };
  const submit = async () => {
    setSending(true);
    setError("");
    try {
      await onSubmit();
      close();
    } catch (e) {
      setError(e.message);
      setSending(false);
    }
  };
  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); close(); }}>
      <div className="dialog-body">
        <h2>{title}</h2>
        {children}
      </div>
      <div className="actions">
        {error ? <span className="error" role="alert">{error}</span> : <span></span>}
        <button className="plain" onClick={close}>取消</button>
        <button className="primary" onClick={submit} disabled={!valid || sending}>{sending ? "提交中" : submitLabel}</button>
      </div>
    </dialog>
  );
}
