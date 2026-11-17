import React, { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon.jsx";

/** Pops a small menu and closes it on a click elsewhere or Esc. Used by MoreMenu and the avatar menu. Returns [open, setOpen, ref]. */
export function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => !ref.current?.contains(e.target) && setOpen(false);
    const key = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  return [open, setOpen, ref];
}

/** The "⋯" menu for the less common actions. Props: `items` ([{label, onClick, danger}]; a `danger` item asks "确定？" with 确认 and 取消 before it runs, and `confirmText` can
 * say what will happen), `label` (the button's accessible name, default "更多"). */
export function MoreMenu({ items, label = "更多" }) {
  const [open, setOpen, ref] = usePopover();
  const [asking, setAsking] = useState(null);
  const close = () => {
    setOpen(false);
    setAsking(null);
  };
  useEffect(() => {
    if (!open) setAsking(null);
  }, [open]);
  if (!items?.length) return null;
  return (
    <span className="menu-wrap" ref={ref}>
      <button className="secondary icon-button" aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="more" /></button>
      {open && (
        <div className="menu" role="menu">
          {asking ? (
            <div className="menu-ask">
              <p>{asking.confirmText ?? `确定要“${asking.label}”吗？`}</p>
              <div className="menu-ask-buttons">
                <button className="secondary" onClick={() => setAsking(null)}>取消</button>
                <button className="danger" onClick={() => { close(); asking.onClick?.(); }}>确认</button>
              </div>
            </div>
          ) : items.map((item) => (
            <button key={item.label} role="menuitem" className={item.danger ? "menu-item danger-text" : "menu-item"} onClick={() => (item.danger ? setAsking(item) : (close(), item.onClick?.()))}>{item.label}</button>
          ))}
        </div>
      )}
    </span>
  );
}
