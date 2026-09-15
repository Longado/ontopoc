import { useEffect, useState } from "react";

import { RecallWorkspace } from "./RecallWorkspace.jsx";
import { PublicRecallReview } from "./PublicRecallReview.jsx";
import { OntologyStudio } from "./OntologyStudio.jsx";

const copy = {
  zh: { nav: "工作台导航", landing: "产品首页", lang: "EN", more: "更多示例",
        tabs: { studio: "上传建本体", public: "汽车召回范围研判", recall: "食品召回事件 95876" },
        hints: { studio: "数据表 → 本体 → 评测", public: "NHTSA 公开数据", recall: "openFDA · 需本机服务" } },
  en: { nav: "Workbench", landing: "Product home", lang: "中文", more: "More examples",
        tabs: { studio: "Upload to ontology", public: "Vehicle recall scope", recall: "Food recall event 95876" },
        hints: { studio: "table → ontology → evaluation", public: "NHTSA public data", recall: "openFDA · local service" } },
};

export function StandaloneDemo() {
  const [language, setLanguage] = useState("zh");
  const [scenario, setScenario] = useState("studio");
  const [recallBusy, setRecallBusy] = useState(false);
  const t = copy[language];
  const entry = (key) => <button key={key} type="button" disabled={recallBusy}
    aria-current={scenario === key ? "page" : undefined} onClick={() => setScenario(key)}>
    <i aria-hidden="true" /><span>{t.tabs[key]}<small>{t.hints[key]}</small></span>
  </button>;

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  return <main className="app-shell">
    <aside className="app-side">
      <a className="app-brand" href="/landing" aria-label="OntoPoc product home">
        <img src="/assets/ontopoc-logo.png" alt="OntoPoc" />
      </a>
      <nav className="app-nav" aria-label={t.nav}>
        {entry("studio")}
        <details className="app-more" open={scenario !== "studio" || undefined}>
          <summary>{t.more}</summary>
          {entry("public")}
          {entry("recall")}
        </details>
        <a href="/landing"><i aria-hidden="true" /><span>{t.landing}</span></a>
      </nav>
      <button type="button" className="app-lang" onClick={() => setLanguage(language === "zh" ? "en" : "zh")}>{t.lang}</button>
    </aside>
    <section className="app-main" aria-label={t.tabs[scenario]}>
      {scenario === "studio" ? <OntologyStudio /> : scenario === "public" ? <PublicRecallReview language={language} /> : <RecallWorkspace language={language} onBusyChange={setRecallBusy} />}
    </section>
  </main>;
}
