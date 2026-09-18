import { useCallback, useEffect, useState } from "react";

import { RecallWorkspace } from "./RecallWorkspace.jsx";
import { PublicRecallReview } from "./PublicRecallReview.jsx";
import { OntologyStudio } from "./OntologyStudio.jsx";
import { groupRuns, runLabel } from "./runLibraryModel.js";
import { localTime } from "./ontologyStudioModel.js";

const copy = {
  zh: { nav: "工作台导航", landing: "产品首页", lang: "EN", more: "更多示例", create: "新建", library: "运行记录",
        empty: "还没有运行记录。传一份文件，结果会一直留在这里。", offline: "建模服务没连上，看不到运行记录。",
        tabs: { public: "汽车召回范围研判", recall: "食品召回事件 95876" },
        hints: { public: "NHTSA 公开数据", recall: "openFDA · 需本机服务" } },
  en: { nav: "Workbench", landing: "Product home", lang: "中文", more: "More examples", create: "New", library: "Runs",
        empty: "No runs yet. Upload a file and its result stays here.", offline: "The modelling service is not reachable, so runs cannot be listed.",
        tabs: { public: "Vehicle recall scope", recall: "Food recall event 95876" },
        hints: { public: "NHTSA public data", recall: "openFDA · local service" } },
};

export function StandaloneDemo() {
  const [language, setLanguage] = useState("zh");
  const [scenario, setScenario] = useState("studio");
  const [recallBusy, setRecallBusy] = useState(false);
  const [runs, setRuns] = useState(null);   // null: not loaded, "offline": service not reachable
  const [current, setCurrent] = useState(null);
  const [request, setRequest] = useState(null);   // what the studio should do next: start new work, or open a saved run
  const t = copy[language];

  const refresh = useCallback(() => {
    fetch("/api/ontology/runs", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((body) => setRuns(body.runs)).catch(() => setRuns("offline"));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { document.documentElement.lang = language === "zh" ? "zh-CN" : "en"; }, [language]);

  const ask = (next) => { setScenario("studio"); setRequest({ ...next, nonce: Date.now() }); };
  const entry = (key) => <button key={key} type="button" disabled={recallBusy}
    aria-current={scenario === key ? "page" : undefined} onClick={() => setScenario(key)}>
    <i aria-hidden="true" /><span>{t.tabs[key]}<small>{t.hints[key]}</small></span>
  </button>;

  return <main className="app-shell">
    <aside className="app-side">
      <a className="app-brand" href="/landing" aria-label="OntoPoc product home">
        <img src="/assets/ontopoc-logo-light.png" alt="OntoPoc" />
      </a>
      <button type="button" className="app-new" onClick={() => ask({ kind: "new" })}><span aria-hidden="true">＋</span>{t.create}</button>
      <nav className="app-library" aria-label={t.library}>
        <p className="app-label">{t.library}</p>
        {runs === "offline" && <p className="app-empty">{t.offline}</p>}
        {Array.isArray(runs) && !runs.length && <p className="app-empty">{t.empty}</p>}
        {Array.isArray(runs) && groupRuns(runs).map((folder, i) => <details key={folder.file} className="app-folder" open={i < 3 || folder.runs.some((r) => r.saved_as === current) || undefined}>
          <summary title={folder.file}>{folder.label}<small>{folder.runs.length}</small></summary>
          {folder.runs.map((r) => <button key={r.saved_as} type="button" title={r.purpose || ""}
            aria-current={scenario === "studio" && r.saved_as === current ? "page" : undefined}
            onClick={() => ask({ kind: "open", saved_as: r.saved_as })}><span>{runLabel(r)}</span><small>{localTime(r.started_at)}</small></button>)}
        </details>)}
      </nav>
      <nav className="app-nav" aria-label={t.nav}>
        <details className="app-more" open={scenario !== "studio" || undefined}>
          <summary>{t.more}</summary>
          {entry("public")}
          {entry("recall")}
        </details>
        <a href="/landing"><i aria-hidden="true" /><span>{t.landing}</span></a>
      </nav>
      <button type="button" className="app-lang" onClick={() => setLanguage(language === "zh" ? "en" : "zh")}>{t.lang}</button>
    </aside>
    <section className="app-main" aria-label={scenario === "studio" ? "OntoPoc" : t.tabs[scenario]}>
      {scenario === "studio" ? <OntologyStudio request={request} onRunsChanged={refresh} onCurrent={setCurrent} />
        : scenario === "public" ? <PublicRecallReview language={language} /> : <RecallWorkspace language={language} onBusyChange={setRecallBusy} />}
    </section>
  </main>;
}
