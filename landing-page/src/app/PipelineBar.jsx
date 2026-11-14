import React from "react";
import { hrefFor } from "./routeModel.js";
import { PipelineState } from "./PipelinesPage.jsx";

const VIEWS = [["edit", "编辑"], ["runs", "运行记录"], ["history", "历史"], ["confirm", "确认"]];

/** The bar over every pipeline screen: where it is, its state, the other screens, and (on the right) the actions of the screen. */
export function PipelineBar({ detail, view, children }) {
  const here = view === "run" ? "runs" : view;
  return (
    <header className="pl-bar">
      <div className="pl-bar-title">
        <a className="back" href={hrefFor({ page: "pipelines" })}>管道</a>
        <h1 tabIndex={-1}>{detail.name}</h1>
        <PipelineState item={detail} />
      </div>
      <nav className="pl-bar-views" aria-label="这条管道的页面">
        {VIEWS.filter(([k]) => k !== "confirm" || detail.state !== "confirmed").map(([k, label]) => (
          <a key={k} href={hrefFor({ page: "pipeline", name: detail.name, view: k })} className={here === k ? "active" : ""} aria-current={here === k ? "page" : undefined}>{label}</a>
        ))}
      </nav>
      <div className="pl-bar-actions">{children}</div>
    </header>
  );
}
