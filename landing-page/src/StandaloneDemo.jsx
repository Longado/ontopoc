import { useCallback, useEffect, useState } from "react";

import { RecallWorkspace } from "./RecallWorkspace.jsx";
import { PublicRecallReview } from "./PublicRecallReview.jsx";
import { OntologyStudio } from "./OntologyStudio.jsx";
import { folderLabel, groupRuns, runLabel } from "./runLibraryModel.js";
import { localTime } from "./ontologyStudioModel.js";
import { sectionsFor } from "./workspaceModel.js";

const copy = {
  zh: { nav: "工作台导航", landing: "产品首页", lang: "EN", more: "更多示例", create: "新建", library: "运行记录", modules: "模块", space: "空间", pick: "选一次运行", tools: "工具",
        empty: "还没有运行记录。传一份文件，结果会一直留在这里。", offline: "建模服务没连上，看不到运行记录。",
        tabs: { public: "汽车召回范围研判", recall: "食品召回事件 95876" },
        hints: { public: "NHTSA 公开数据", recall: "openFDA · 需本机服务" } },
  en: { nav: "Workbench", landing: "Product home", lang: "中文", more: "More examples", create: "New", library: "Runs", modules: "Modules", space: "Space", pick: "Pick a run", tools: "Tools",
        empty: "No runs yet. Upload a file and its result stays here.", offline: "The modelling service is not reachable, so runs cannot be listed.",
        tabs: { public: "Vehicle recall scope", recall: "Food recall event 95876" },
        hints: { public: "NHTSA public data", recall: "openFDA · local service" } },
};

const ICONS = {   // one stroke each, drawn on a 24 grid, like the platform's own sidebar
  data: <><path d="M12 15V4" /><path d="m7 9 5-5 5 5" /><path d="M5 15v4a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4" /></>,
  objects: <><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5z" /><path d="M13 4h5.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H13z" /></>,
  graph: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="8" r="2.5" /><circle cx="10" cy="18" r="2.5" /><path d="m8.3 7 7.4 1M7 8.3l2 7.4M16.5 10l-5 6" /></>,
  qa: <><path d="M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12z" /><path d="M9 12h.01M12 12h.01M15 12h.01" /></>,
  check: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4v2h6V4" /><path d="m9 13 2 2 4-4" /></>,
};

export function StandaloneDemo() {
  const [language, setLanguage] = useState("zh");
  const [scenario, setScenario] = useState("studio");
  const [recallBusy, setRecallBusy] = useState(false);
  const [runs, setRuns] = useState(null);   // null: not loaded, "offline": service not reachable
  const [open, setOpen] = useState(null);   // the run shown in the studio: the workspace the modules act on
  const [section, setSection] = useState(null);
  const [nav, setNav] = useState(0);   // bumped on every sidebar click, so the module opens at its start page
  const current = open?.saved_as || null;
  const [request, setRequest] = useState(null);   // what the studio should do next: start new work, or open a saved run
  const t = copy[language];

  const refresh = useCallback(() => {
    fetch("/api/ontology/runs", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((body) => setRuns(body.runs)).catch(() => setRuns("offline"));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { document.documentElement.lang = language === "zh" ? "zh-CN" : "en"; }, [language]);

  const ask = (next) => { setScenario("studio"); setRequest({ ...next, nonce: Date.now() }); };
  const go = (key) => { setScenario("studio"); setSection(key); setNav((n) => n + 1); };
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
      <nav className="app-modules" aria-label={t.modules}>
        <p className="app-label">{t.tools}</p>
        {sectionsFor(open).map(([key, label]) => <button key={key} type="button" aria-current={scenario === "studio" && section === key ? "page" : undefined} onClick={() => go(key)}>
          <svg aria-hidden="true" viewBox="0 0 24 24" className="app-ico">{ICONS[key]}</svg>{label}</button>)}
        {!open && <p className="app-empty">打开一次运行，或者新建一次，这里就会列出它的数据、本体、关系、问答和体检。</p>}
      </nav>
      <nav className="app-nav" aria-label={t.nav}>
        <details className="app-more" open={scenario !== "studio" || undefined}>
          <summary>{t.more}</summary>
          {entry("public")}
          {entry("recall")}
        </details>
        <a href="/landing"><i aria-hidden="true" /><span>{t.landing}</span></a>
      </nav>
      <details className="app-space" open={!open || undefined}>
        <summary><span className="app-label">{t.space}</span><b title={open?.file.name}>{open ? folderLabel(open.file.name) : t.pick}</b>{open?.purpose && <small>{open.purpose}</small>}</summary>
        <div className="app-library" role="navigation" aria-label={t.library}>
          {runs === "offline" && <p className="app-empty">{t.offline}</p>}
          {Array.isArray(runs) && !runs.length && <p className="app-empty">{t.empty}</p>}
          {Array.isArray(runs) && groupRuns(runs).map((folder, i) => <details key={folder.file} className="app-folder" open={i < 3 || folder.runs.some((r) => r.saved_as === current) || undefined}>
            <summary title={folder.file}>{folder.label}<small>{folder.runs.length}</small></summary>
            {folder.runs.map((r) => <button key={r.saved_as} type="button" title={r.purpose || ""}
              aria-current={scenario === "studio" && r.saved_as === current ? "page" : undefined}
              onClick={(e) => { e.currentTarget.closest("details.app-space").open = false; ask({ kind: "open", saved_as: r.saved_as }); }}><span>{runLabel(r)}</span><small>{localTime(r.started_at)}</small></button>)}
          </details>)}
        </div>
      </details>
      <button type="button" className="app-lang" onClick={() => setLanguage(language === "zh" ? "en" : "zh")}>{t.lang}</button>
    </aside>
    <section className="app-main" aria-label={scenario === "studio" ? "OntoPoc" : t.tabs[scenario]}>
      {scenario === "studio" ? <OntologyStudio request={request} section={section} nav={nav} onSection={setSection} onRunsChanged={refresh} onCurrent={setOpen} />
        : scenario === "public" ? <PublicRecallReview language={language} /> : <RecallWorkspace language={language} onBusyChange={setRecallBusy} />}
    </section>
  </main>;
}
