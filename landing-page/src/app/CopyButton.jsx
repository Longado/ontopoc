import React, { useState } from "react";

/** Copies text to the clipboard. Works on a page served over plain http on a company network too, where navigator.clipboard is missing: it falls back to a hidden text box. */
export async function copyText(text) {
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("readonly", "");
  box.style.cssText = "position:fixed;top:-1000px;opacity:0";
  document.body.appendChild(box);
  box.select();
  const ok = document.execCommand("copy");
  box.remove();
  if (!ok) throw new Error("复制没有成功，请手动选中文字复制");
}

/** A button that copies `text` and says so for two seconds. `label` is its name, `done` what it says after. */
export function CopyButton({ text, label = "复制", done = "已复制", className = "secondary" }) {
  const [state, setState] = useState("idle");   // idle | done | failed
  const go = async () => {
    try {
      await copyText(typeof text === "function" ? text() : text);
      setState("done");
    } catch {
      setState("failed");
    }
    setTimeout(() => setState("idle"), 2000);
  };
  return <button type="button" className={className} onClick={go} aria-live="polite">{state === "done" ? done : state === "failed" ? "复制失败，请手动复制" : label}</button>;
}
