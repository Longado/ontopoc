import React from "react";
import { t } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { PipelineState } from "./PipelinesPage.jsx";
import { MoreMenu } from "./ui/MoreMenu.jsx";

const VIEWS = ["edit", "runs", "history", "confirm"];

/** The head over every pipeline screen, kept to two thin rows so that the canvas gets the height: the breadcrumb, the name with its one state chip and `meta` (the saved / unsaved note),
 * the actions of the screen on the right (`actions`, the main one last) and the "..." menu (`more`); then the other screens of this pipeline as tabs. */
export function PipelineBar({ detail, view, meta, actions, more }) {
  const here = view === "run" ? "runs" : view;
  return (
    <div className="pl-bar">
      <header className="pl-head">
        <nav className="pl-crumbs" aria-label={t("ui.crumbs.aria")}>
          <span>{t("pipeline.bar.data")}</span>
          <span className="crumb-sep" aria-hidden="true">/</span>
          <a href={hrefFor({ page: "pipelines" })}>{t("pipeline.bar.pipelines")}</a>
          <span className="crumb-sep" aria-hidden="true">/</span>
        </nav>
        <h1 className="pl-title" tabIndex={-1} title={detail.name}>{detail.name}</h1>
        <PipelineState item={detail} />
        {meta}
        <div className="pl-head-actions">
          {actions}
          <MoreMenu items={more} />
        </div>
      </header>
      <nav className="pl-bar-views" aria-label={t("pipeline.bar.viewsAria")}>
        {VIEWS.filter((k) => k !== "confirm" || detail.state !== "confirmed").map((k) => (
          <a key={k} href={hrefFor({ page: "pipeline", name: detail.name, view: k })} className={here === k ? "active" : ""} aria-current={here === k ? "page" : undefined}>{t(`pipeline.bar.view.${k}`)}</a>
        ))}
      </nav>
    </div>
  );
}
