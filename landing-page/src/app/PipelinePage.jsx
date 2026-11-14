import React from "react";
import { getPipeline } from "./api.js";
import { PipelineBar } from "./PipelineBar.jsx";
import { PipelineConfirm } from "./PipelineConfirm.jsx";
import { PipelineEditor } from "./PipelineEditor.jsx";
import { PipelineHistory, PipelineRun, PipelineRuns } from "./PipelineViews.jsx";
import { hrefFor } from "./routeModel.js";
import { useLoad } from "./useLoad.js";

/** One pipeline: the editing page, its runs, one run, its history, or the screen where a second person confirms it. */
export function PipelinePage({ route }) {
  const [state, reload] = useLoad(() => getPipeline(route.name), [route.name]);
  const detail = state.data;
  if (!detail) {
    return (
      <main className="page">
        <a className="back" href={hrefFor({ page: "pipelines" })}>管道</a>
        {state.status === "loading" && <p className="muted">加载中</p>}
        {state.status === "error" && <p className="error">{state.missing ? "没有这条管道" : state.error} <button className="plain" onClick={reload}>重试</button></p>}
      </main>
    );
  }
  if (route.view === "edit") return <main className="pl-main"><PipelineEditor detail={detail} reload={reload} /></main>;
  return (
    <main className="pl-main">
      <div className="pl">
        <PipelineBar detail={detail} view={route.view} />
        {route.view === "runs" && <PipelineRuns detail={detail} />}
        {route.view === "run" && <PipelineRun detail={detail} id={route.run} />}
        {route.view === "history" && <PipelineHistory detail={detail} />}
        {route.view === "confirm" && <PipelineConfirm detail={detail} reload={reload} />}
      </div>
    </main>
  );
}
