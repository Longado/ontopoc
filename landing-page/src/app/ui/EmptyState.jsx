import React from "react";
import { Icon } from "./Icon.jsx";

/** What a page shows when there is nothing yet: an icon, one sentence, one main button. Props: `icon` (an Icon name), `title`, `text`, `action` ({label, href} or {label, onClick}; optional). */
export function EmptyState({ icon = "info", title, text, action }) {
  return (
    <div className="empty">
      <span className="empty-icon"><Icon name={icon} size={24} /></span>
      <p className="empty-title">{title}</p>
      {text && <p className="empty-text">{text}</p>}
      {action && (action.href
        ? <a className="button primary" href={action.href}>{action.label}</a>
        : <button className="primary" onClick={action.onClick}>{action.label}</button>)}
    </div>
  );
}
