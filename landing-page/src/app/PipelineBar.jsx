import React from "react";
import { hrefFor } from "./routeModel.js";
import { PipelineState } from "./PipelinesPage.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

const VIEWS = [["edit", "编辑"], ["runs", "运行记录"], ["history", "历史"], ["confirm", "确认"]];

/** The head over every pipeline screen: the breadcrumb (数据 / 管道 / name), the title with its one state chip, the other screens of this pipeline, and on the right the actions of the screen
 * (`actions`, the main one last) and the "⋯" menu (`more`). */
export function PipelineBar({ detail, view, actions, more }) {
  const here = view === "run" ? "runs" : view;
  return (
    <div className="pl-bar">
      <PageHeader crumbs={[{ label: "数据" }, { label: "管道", href: hrefFor({ page: "pipelines" }) }, { label: detail.name }]} title={detail.name} status={<PipelineState item={detail} />} actions={actions} more={more} />
      <nav className="pl-bar-views" aria-label="这条管道的页面">
        {VIEWS.filter(([k]) => k !== "confirm" || detail.state !== "confirmed").map(([k, label]) => (
          <a key={k} href={hrefFor({ page: "pipeline", name: detail.name, view: k })} className={here === k ? "active" : ""} aria-current={here === k ? "page" : undefined}>{label}</a>
        ))}
      </nav>
    </div>
  );
}
