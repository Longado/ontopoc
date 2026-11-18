import React from "react";
import { t } from "../i18n/index.js";
import { MoreMenu } from "./MoreMenu.jsx";

/** The head of a page: a breadcrumb line, the title with its state chip, the main actions on the right, and "⋯ More" for the rest.
 * Props: `crumbs` ([{label, href}]; the last may have no href: where you are), `title` (the page's h1; the shell moves focus to it), `status` (a node, usually <StatusChip/>),
 * `actions` (a node: the buttons, main one last), `more` ([{label, onClick, danger}]: a danger item asks to confirm; delete goes here), `sub` (one grey line under the title). */
export function PageHeader({ crumbs = [], title, status, actions, more, sub }) {
  return (
    <header className="ph">
      {crumbs.length > 0 && (
        <nav className="crumbs" aria-label={t("ui.crumbs.aria")}>
          {crumbs.map((c, i) => (
            <span key={`${c.label}${i}`}>
              {i > 0 && <span className="crumb-sep" aria-hidden="true">/</span>}
              {c.href ? <a href={c.href}>{c.label}</a> : <span aria-current="page">{c.label}</span>}
            </span>
          ))}
        </nav>
      )}
      <div className="ph-row">
        <div className="ph-title">
          <h1 tabIndex={-1}>{title}</h1>
          {status}
        </div>
        {(actions || more?.length > 0) && (
          <div className="ph-actions">
            {actions}
            <MoreMenu items={more} />
          </div>
        )}
      </div>
      {sub && <p className="ph-sub">{sub}</p>}
    </header>
  );
}
