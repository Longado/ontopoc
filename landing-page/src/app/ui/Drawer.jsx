import React, { useEffect, useRef } from "react";
import { t } from "../i18n/index.js";
import { Icon } from "./Icon.jsx";

/** A panel that slides in from the right over a dimmed page; Esc, the × and a click on the dim close it. Props: `open`, `title`, `onClose`, `children` (the body), `width` (px, default 480),
 * `footer` (a node pinned at the bottom: the save and cancel buttons). Focus moves into the panel when it opens and back to where it was when it closes. */
export function Drawer({ open, title, onClose, children, width = 480, footer }) {
  const panel = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const before = document.activeElement;
    panel.current?.focus();
    const key = (e) => e.key === "Escape" && onClose?.();
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      before?.focus?.();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="ui-drawer-root">
      <div className="ui-overlay" onClick={onClose} />
      <aside className="ui-drawer" role="dialog" aria-modal="true" aria-label={title} style={{ width: `min(${width}px, 100vw)` }} ref={panel} tabIndex={-1}>
        <div className="ui-drawer-head">
          <h2>{title}</h2>
          <button className="plain icon-button" aria-label={t("ui.drawer.close")} onClick={onClose}><Icon name="close" /></button>
        </div>
        <div className="ui-drawer-body">{children}</div>
        {footer && <div className="ui-drawer-foot">{footer}</div>}
      </aside>
    </div>
  );
}
